"""
Async Pinecone ingestion script.

Architecture:
  ┌─────────────────────────────────────────────────┐
  │  asyncio.Queue  ← producer fills with batches   │
  │       ↓                                         │
  │  N embed workers  (run CPU work in executor)    │
  │       ↓                                         │
  │  M upsert workers (async Pinecone upsert)       │
  └─────────────────────────────────────────────────┘

Producer  → embed_queue    (raw text batches)
Embedders → upsert_queue   (embedded vector batches)
Upserters → Pinecone index (async upsert via AsyncPinecone)

Why async?
- Embedding is CPU-bound  → run in ThreadPoolExecutor, N workers in parallel
- Pinecone upsert is I/O-bound → true async with AsyncPinecone, M concurrent calls
- Together they pipeline: while one batch is uploading, the next is being embedded.

Usage:
    cd backend
    python rag/pinecone_ingest.py

    # Custom workers / batch size:
    EMBED_WORKERS=4 UPSERT_WORKERS=8 BATCH_SIZE=200 python rag/pinecone_ingest.py

Environment variables (backend/.env):
    PINECONE_API_KEY        required
    PINECONE_INDEX_NAME     default: python-qa
    PINECONE_ENVIRONMENT    default: us-east-1
    DATA_FILE_PATH          default: ../question_answer.json
    INGEST_LIMIT            default: 0  (0 = all records)
    EMBEDDING_DIM           default: 384
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

# ── Bootstrap path ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pinecone import Pinecone, ServerlessSpec
from pinecone import AsyncPinecone              # async client
from tqdm.asyncio import tqdm as atqdm          # async-aware tqdm

from rag.embeddings import embed_texts_sync     # CPU-bound, runs in executor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
PINECONE_API_KEY  = os.getenv("PINECONE_API_KEY", "")
INDEX_NAME        = os.getenv("PINECONE_INDEX_NAME", "python-qa")
ENVIRONMENT       = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
DATA_FILE         = Path(os.getenv("DATA_FILE_PATH", "../question_answer.json")).resolve()
INGEST_LIMIT      = int(os.getenv("INGEST_LIMIT", "0"))
EMBEDDING_DIM     = int(os.getenv("EMBEDDING_DIM", "384"))

# Tunable concurrency — override via env vars
BATCH_SIZE        = int(os.getenv("BATCH_SIZE", "100"))   # records per batch
EMBED_WORKERS     = int(os.getenv("EMBED_WORKERS", "2"))   # parallel CPU embed threads
UPSERT_WORKERS    = int(os.getenv("UPSERT_WORKERS", "4"))  # parallel async upsert tasks
QUEUE_DEPTH       = UPSERT_WORKERS * 2                     # back-pressure buffer

# Checkpoint file — tracks how many rows were successfully upserted
# Stored next to the script so it survives restarts
CHECKPOINT_FILE   = Path(__file__).parent / ".ingest_checkpoint"

# ── Checkpoint helpers ────────────────────────────────────────────────────────

def load_checkpoint() -> int:
    """
    Return the row offset to resume from.
    0 means start from the beginning (no checkpoint or reset requested).
    """
    if "--reset" in sys.argv:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        logger.info("--reset: starting from row 0.")
        return 0
    if CHECKPOINT_FILE.exists():
        try:
            offset = int(CHECKPOINT_FILE.read_text().strip())
            logger.info(f"Resuming from row {offset:,} (checkpoint found).")
            return offset
        except ValueError:
            pass
    return 0


def save_checkpoint(upserted_so_far: int) -> None:
    """Persist the number of rows successfully upserted so far."""
    CHECKPOINT_FILE.write_text(str(upserted_so_far))


def clear_checkpoint() -> None:
    """Remove the checkpoint file after a successful full run."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


# ── Helpers ────────────────────────────────────────────────────────────────────

def ensure_index(pc: Pinecone) -> None:
    """Create the Pinecone index if it doesn't already exist (sync — runs once)."""
    existing = {idx["name"] for idx in pc.list_indexes()}
    if INDEX_NAME not in existing:
        logger.info(f"Creating index '{INDEX_NAME}' (dim={EMBEDDING_DIM}, cosine)…")
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=ENVIRONMENT),
        )
        logger.info("Index created successfully.")
    else:
        logger.info(f"Index '{INDEX_NAME}' already exists — skipping creation.")


def load_records() -> list[dict]:
    """Load question_answer.json from disk (sync, called once at startup)."""
    logger.info(f"Loading data from {DATA_FILE}…")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if INGEST_LIMIT > 0:
        data = data[:INGEST_LIMIT]
    logger.info(f"Loaded {len(data):,} records.")
    return data


def build_text(record, row_num: int) -> str:
    """
    Format one Q&A record into the text that gets embedded and stored.
    Handles both raw strings (e.g. question_answer.json = list of strings)
    and dict records with 'question'/'answer' keys.
    """
    if isinstance(record, str):
        return record   # already formatted as "Question: ...\n\nAnswer: ..."
    q = record.get("question", record.get("Question", ""))
    a = record.get("answer",   record.get("Answer",   ""))
    return f"Question: {q}\n\nAnswer: {a}"


def make_vectors(batch: list[dict], embeddings: List[List[float]], batch_start: int) -> list[dict]:
    """Zip a batch of records with their embeddings into Pinecone vector dicts."""
    vectors = []
    for i, (record, emb) in enumerate(zip(batch, embeddings)):
        row_num = batch_start + i
        text = build_text(record, row_num)
        vectors.append({
            "id": str(row_num),
            "values": emb,
            "metadata": {
                "row_number": row_num,
                "content": text[:2000],   # Pinecone metadata value limit
            },
        })
    return vectors


# ── Async pipeline workers ─────────────────────────────────────────────────────

async def embed_worker(
    worker_id: int,
    embed_queue: asyncio.Queue,
    upsert_queue: asyncio.Queue,
    executor: ThreadPoolExecutor,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Consume raw text batches from embed_queue.
    Run CPU-bound sentence-transformer encoding in the thread pool.
    Push embedded vectors to upsert_queue.
    """
    while True:
        item = await embed_queue.get()
        if item is None:                  # poison pill → shut down
            embed_queue.task_done()
            break

        batch_start, batch = item
        texts = [build_text(r, batch_start + i) for i, r in enumerate(batch)]

        try:
            # Off-load the CPU work so the event loop stays unblocked
            embeddings: List[List[float]] = await loop.run_in_executor(
                executor,
                embed_texts_sync,
                texts,
            )
            vectors = make_vectors(batch, embeddings, batch_start)
            await upsert_queue.put(vectors)
        except Exception as exc:
            logger.error(f"[embed_worker-{worker_id}] batch {batch_start}: {exc}")
        finally:
            embed_queue.task_done()


async def upsert_worker(
    worker_id: int,
    upsert_queue: asyncio.Queue,
    async_index,
    counter: list[int],          # mutable single-element list for shared counter
    pbar,
) -> None:
    """
    Consume embedded vector batches from upsert_queue.
    Call Pinecone async_index.upsert() concurrently.
    """
    while True:
        item = await upsert_queue.get()
        if item is None:                  # poison pill → shut down
            upsert_queue.task_done()
            break

        try:
            await async_index.upsert(vectors=item)
            counter[0] += len(item)
            pbar.update(len(item))
            # Save checkpoint after every successful upsert batch
            save_checkpoint(counter[0])
        except Exception as exc:
            logger.error(f"[upsert_worker-{worker_id}] upsert error: {exc}")
        finally:
            upsert_queue.task_done()


# ── Main async orchestrator ────────────────────────────────────────────────────

async def run_ingestion(records: list, resume_from: int = 0) -> int:
    """
    Pipeline:
      producer → embed_queue → embed_workers → upsert_queue → upsert_workers → Pinecone

    resume_from: row index to start from (skip already-upserted rows).
    """
    total = len(records)
    remaining = total - resume_from
    num_batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE

    if resume_from > 0:
        logger.info(
            f"Skipping first {resume_from:,} rows — resuming with "
            f"{remaining:,} remaining ({num_batches:,} batches)."
        )
    else:
        logger.info(
            f"Pipeline: {num_batches:,} batches × {BATCH_SIZE} records | "
            f"embed_workers={EMBED_WORKERS} upsert_workers={UPSERT_WORKERS}"
        )

    embed_queue:  asyncio.Queue = asyncio.Queue(maxsize=QUEUE_DEPTH)
    upsert_queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_DEPTH * 2)
    # Initialise counter at resume_from so checkpoints reflect total rows done
    counter = [resume_from]

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=EMBED_WORKERS, thread_name_prefix="embedder")

    # Async Pinecone client — true async I/O for upserts
    async_pc = AsyncPinecone(api_key=PINECONE_API_KEY)
    async_index = await async_pc.index(INDEX_NAME)   # coroutine — must be awaited

    t_start = time.perf_counter()

    with atqdm(
        total=total,
        initial=resume_from,          # progress bar starts at the resume point
        desc="Vectors upserted",
        unit="vec",
        smoothing=0.1,
    ) as pbar:

        # ── Spawn embed workers ──────────────────────────────────────────────
        embed_tasks = [
            asyncio.create_task(
                embed_worker(i, embed_queue, upsert_queue, executor, loop),
                name=f"embed-{i}",
            )
            for i in range(EMBED_WORKERS)
        ]

        # ── Spawn upsert workers ─────────────────────────────────────────────
        upsert_tasks = [
            asyncio.create_task(
                upsert_worker(i, upsert_queue, async_index, counter, pbar),
                name=f"upsert-{i}",
            )
            for i in range(UPSERT_WORKERS)
        ]

        # ── Producer: only enqueue batches from resume_from onwards ──────────
        for batch_start in range(resume_from, total, BATCH_SIZE):
            batch = records[batch_start: batch_start + BATCH_SIZE]
            await embed_queue.put((batch_start, batch))

        # ── Signal embed workers to stop (one poison pill per worker) ────────
        for _ in range(EMBED_WORKERS):
            await embed_queue.put(None)

        # ── Wait for all embeds to finish ────────────────────────────────────
        await asyncio.gather(*embed_tasks)

        # ── Signal upsert workers to stop ────────────────────────────────────
        for _ in range(UPSERT_WORKERS):
            await upsert_queue.put(None)

        # ── Wait for all upserts to finish ───────────────────────────────────
        await asyncio.gather(*upsert_tasks)

    executor.shutdown(wait=False)
    elapsed = time.perf_counter() - t_start
    newly_upserted = counter[0] - resume_from
    rate = newly_upserted / elapsed if elapsed > 0 else 0
    logger.info(
        f"✅ Ingestion complete: {newly_upserted:,} new vectors in {elapsed:.1f}s "
        f"({rate:.0f} vec/s) | total in index: ~{counter[0]:,}"
    )
    return counter[0]


async def main_async() -> None:
    if not PINECONE_API_KEY:
        logger.error("PINECONE_API_KEY is not set. Add it to backend/.env.")
        sys.exit(1)

    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "Usage: python rag/pinecone_ingest.py [--reset]\n"
            "  (no flag)  Resume from checkpoint if one exists, else start fresh.\n"
            "  --reset    Ignore checkpoint and restart from row 0.\n"
        )
        return

    # Index creation is a sync one-shot operation — do it before the async pipeline
    pc = Pinecone(api_key=PINECONE_API_KEY)
    ensure_index(pc)

    records = load_records()
    if not records:
        logger.warning("No records found — nothing to ingest.")
        return

    # ── Checkpoint: find out where we left off ────────────────────────────────
    resume_from = load_checkpoint()
    if resume_from >= len(records):
        logger.info(
            f"Checkpoint shows all {resume_from:,} rows already done. "
            f"Run with --reset to re-ingest from scratch."
        )
        return

    try:
        total_upserted = await run_ingestion(records, resume_from=resume_from)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning(
            f"Interrupted. Progress saved to checkpoint — "
            f"run again to resume from row {load_checkpoint():,}."
        )
        return

    # Full run completed — remove checkpoint so a fresh re-run starts from 0
    clear_checkpoint()
    logger.info("Checkpoint cleared — full ingestion finished.")

    # Final index stats (sync — fine to call at the end)
    index = pc.Index(INDEX_NAME)
    stats = index.describe_index_stats()
    logger.info(f"Index stats: total_vector_count={stats.total_vector_count:,}")


if __name__ == "__main__":
    asyncio.run(main_async())
