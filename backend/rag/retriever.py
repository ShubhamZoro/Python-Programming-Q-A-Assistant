"""
Supabase pgvector retriever — TRULY async.

Uses supabase AsyncClient so the event loop is never blocked.
Embeddings are 384-dim (all-MiniLM-L6-v2).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from dotenv import load_dotenv
from supabase import AsyncClient, acreate_client

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Async singleton — created once and reused
_async_client: AsyncClient | None = None


async def get_async_client() -> AsyncClient:
    """
    Return (or lazily create) the async Supabase client.
    Must be called inside an async context.
    """
    global _async_client
    if _async_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _async_client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Async Supabase client initialized")
    return _async_client


async def retrieve_similar(
    query_embedding: List[float],
    top_k: int = 5,
    match_threshold: float = 0.3,
) -> List[dict]:
    """
    Truly async query of Supabase match_documents RPC.
    Uses cosine similarity — returns list of dicts with keys:
      id, row_number, content, similarity
    Never blocks the FastAPI event loop.
    """
    client = await get_async_client()

    try:
        response = await (
            client.rpc(
                "match_documents",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": match_threshold,
                    "match_count": top_k,
                },
            )
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        return []


async def get_sources_for_question(
    query_embedding: List[float],
    limit: int = 5,
) -> List[dict]:
    """Used by GET /sources endpoint — same as retrieve_similar."""
    return await retrieve_similar(query_embedding, top_k=limit)
