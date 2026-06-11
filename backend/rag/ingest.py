"""
Data ingestion script — reads question_answer.json and upserts into Supabase.

Usage:
    python -m rag.ingest

Performance strategy:
- Embedding (CPU-bound):   sentence-transformers runs in the main thread
- Supabase upsert (I/O):   submitted to a ThreadPoolExecutor so the NEXT
                            batch can be embedded while the CURRENT batch
                            is uploading → ~2x throughput vs pure sequential

Pipeline per iteration:
  embed(batch_N)  ──►  upsert(batch_N) submitted to thread pool
                        while upsert runs in background,
                        embed(batch_N+1) runs on main thread in parallel
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client
from tqdm import tqdm

# Add parent to path so we can import rag modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.embeddings import embed_texts_sync

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
DATA_FILE = os.getenv("DATA_FILE_PATH", "../question_answer.json")
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT", "50000"))
BATCH_SIZE = 100

# Max concurrent Supabase upsert workers
# (embedding is CPU-bound on main thread; upserts are I/O-bound in threads)
MAX_UPLOAD_WORKERS = 4

# Python-related keywords for basic filtering
PYTHON_KEYWORDS = {
    "python", "pip", "django", "flask", "pandas", "numpy", "scipy",
    "matplotlib", "tensorflow", "pytorch", "scikit", "sklearn",
    "jupyter", "pydantic", "asyncio", "virtualenv", "conda",
    "list comprehension", "generator", "decorator", "lambda",
}


def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def is_python_related(text: str) -> bool:
    """Loose filter — keep records that mention at least one Python keyword."""
    lower = text.lower()
    return any(kw in lower for kw in PYTHON_KEYWORDS)


def get_existing_row_numbers(client: Client) -> set[int]:
    """
    Fetch all already-ingested row_numbers for idempotency.
    Uses pagination to handle >1000 existing rows (Supabase default limit).
    """
    existing = set()
    page = 0
    page_size = 1000
    try:
        while True:
            response = (
                client.table("documents")
                .select("row_number")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )
            rows = response.data or []
            if not rows:
                break
            existing.update(r["row_number"] for r in rows)
            if len(rows) < page_size:
                break
            page += 1
        logger.info(f"Found {len(existing):,} already-ingested records (paginated check)")
    except Exception as e:
        logger.warning(f"Could not fetch existing row numbers: {e}")
    return existing


def truncate_text(text: str, max_chars: int = 2000) -> str:
    """Truncate very long records to keep embedding quality high."""
    return text[:max_chars] if len(text) > max_chars else text


def _do_upsert(client: Client, records: List[dict]) -> tuple[int, int]:
    """
    Worker function executed in a thread pool.
    Returns (success_count, fail_count).
    """
    try:
        client.table("documents").upsert(records, on_conflict="row_number").execute()
        return len(records), 0
    except Exception as e:
        logger.error(f"Batch upsert failed ({len(records)} records): {e}")
        return 0, len(records)


def main():
    logger.info("=" * 60)
    logger.info("Python Q&A Assistant — Data Ingestion")
    logger.info("  Embedding:  sentence-transformers/all-MiniLM-L6-v2 (local)")
    logger.info("  Strategy:   Async upserts (embed + upload overlap)")
    logger.info("=" * 60)

    # ── Load data ────────────────────────────────────────────────
    data_path = Path(DATA_FILE)
    if not data_path.exists():
        data_path = Path(__file__).parent.parent.parent / "question_answer.json"
    if not data_path.exists():
        logger.error(f"Data file not found: {DATA_FILE}")
        sys.exit(1)

    logger.info(f"Loading data from: {data_path}")
    with open(data_path, "r", encoding="utf-8") as f:
        raw_data: List[str] = json.load(f)

    logger.info(f"Total records in file: {len(raw_data):,}")

    # ── Filter ───────────────────────────────────────────────────
    logger.info("Filtering Python-related records...")
    filtered = [
        (idx, text)
        for idx, text in enumerate(raw_data)
        if is_python_related(text)
    ]
    logger.info(f"Python-related records: {len(filtered):,}")

    if INGEST_LIMIT > 0:
        filtered = filtered[:INGEST_LIMIT]
        logger.info(f"Applying INGEST_LIMIT={INGEST_LIMIT}: {len(filtered):,} records")

    # ── Connect to Supabase ──────────────────────────────────────
    logger.info("Connecting to Supabase...")
    client = get_client()

    # ── Idempotency check ────────────────────────────────────────
    logger.info("Checking existing records (idempotency)...")
    existing = get_existing_row_numbers(client)

    to_ingest = [(idx, text) for idx, text in filtered if idx not in existing]
    logger.info(f"New records to ingest: {len(to_ingest):,}")

    if not to_ingest:
        logger.info("Nothing new to ingest. Done!")
        return

    # ── Embed & upsert in batches (overlapped) ───────────────────
    logger.info(f"Starting ingestion — batch_size={BATCH_SIZE}, upload_workers={MAX_UPLOAD_WORKERS}")
    logger.info("(Supabase upserts run in background threads while next batch is embedded)")

    total = len(to_ingest)
    success_count = 0
    fail_count = 0
    start_time = time.time()

    # ThreadPoolExecutor for async Supabase upserts
    pending_futures: list[Future] = []

    def collect_completed(futures: list[Future]) -> tuple[int, int]:
        """Drain any completed futures and accumulate counts."""
        ok, fail = 0, 0
        still_pending = []
        for f in futures:
            if f.done():
                s, fl = f.result()
                ok += s
                fail += fl
            else:
                still_pending.append(f)
        return ok, fail, still_pending

    with ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS) as executor:
        with tqdm(total=total, desc="Ingesting", unit="rec") as pbar:
            for batch_start in range(0, total, BATCH_SIZE):
                batch = to_ingest[batch_start : batch_start + BATCH_SIZE]
                indices = [idx for idx, _ in batch]
                texts = [truncate_text(text) for _, text in batch]

                # ── Step 1: Embed (CPU, blocks here) ──────────────
                try:
                    embeddings = embed_texts_sync(texts)
                except Exception as e:
                    logger.error(f"Embedding failed for batch at {batch_start}: {e}")
                    fail_count += len(batch)
                    pbar.update(len(batch))
                    continue

                # ── Step 2: Submit upsert to thread pool (non-blocking) ──
                records = [
                    {
                        "row_number": idx,
                        "content": text,
                        "embedding": emb,
                    }
                    for idx, text, emb in zip(indices, texts, embeddings)
                ]
                future = executor.submit(_do_upsert, client, records)
                pending_futures.append(future)

                # ── Step 3: Collect any completed upserts ──────────
                ok, fail, pending_futures = collect_completed(pending_futures)
                success_count += ok
                fail_count += fail

                pbar.update(len(batch))
                pbar.set_postfix(
                    ok=success_count,
                    fail=fail_count,
                    pending=len(pending_futures),
                )

                # Throttle if too many pending upserts (back-pressure)
                while len(pending_futures) >= MAX_UPLOAD_WORKERS * 2:
                    time.sleep(0.05)
                    ok, fail, pending_futures = collect_completed(pending_futures)
                    success_count += ok
                    fail_count += fail

            # ── Wait for all remaining upserts to finish ───────────
            logger.info(f"Waiting for {len(pending_futures)} pending upserts to complete...")
            for future in as_completed(pending_futures):
                ok, fail = future.result()
                success_count += ok
                fail_count += fail

    elapsed = time.time() - start_time
    rate = total / elapsed if elapsed > 0 else 0

    logger.info("=" * 60)
    logger.info(f"Ingestion complete in {elapsed:.1f}s  ({rate:.1f} rec/s)")
    logger.info(f"  ✓ Inserted: {success_count:,}")
    logger.info(f"  ✗ Failed:   {fail_count:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
