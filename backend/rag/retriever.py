"""
Pinecone vector database retriever.

Replaces Supabase pgvector for semantic search.
Embeddings are 384-dim (all-MiniLM-L6-v2).
"""

from __future__ import annotations

import logging
import os
from typing import List

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

logger = logging.getLogger(__name__)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "python-qa")

# Singleton Pinecone index — created once and reused
_index = None


def _get_index():
    """Lazily initialize and return the Pinecone index."""
    global _index
    if _index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY must be set in .env")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _index = pc.Index(PINECONE_INDEX_NAME)
        logger.info(f"Pinecone index '{PINECONE_INDEX_NAME}' connected.")
    return _index


async def retrieve_similar(
    query_embedding: List[float],
    top_k: int = 5,
    match_threshold: float = 0.3,
) -> List[dict]:
    """
    Query Pinecone for the top_k most similar vectors.
    Returns list of dicts with keys: id, row_number, content, similarity.
    """
    import asyncio, functools

    def _query():
        index = _get_index()
        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
        )
        docs = []
        for match in results.get("matches", []):
            score = match.get("score", 0.0)
            if score < match_threshold:
                continue
            meta = match.get("metadata", {})
            docs.append({
                "id": match.get("id"),
                "row_number": meta.get("row_number"),
                "content": meta.get("content", ""),
                "similarity": score,
            })
        return docs

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _query)
    except Exception as e:
        logger.error(f"Pinecone retrieval error: {e}")
        return []


async def get_sources_for_question(
    query_embedding: List[float],
    limit: int = 5,
) -> List[dict]:
    """Used by GET /sources endpoint — same as retrieve_similar."""
    return await retrieve_similar(query_embedding, top_k=limit)


# ── Kept for startup health check ─────────────────────────────────────────────
async def get_async_client():
    """
    Compatibility shim — main.py calls this on startup.
    Pinecone index is sync; we just verify connectivity here.
    """
    import asyncio, functools
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _get_index)
    logger.info("Pinecone index ready.")
