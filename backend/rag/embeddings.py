"""
Open-source embedding using FastEmbed (NO torch dependency).

Model: BAAI/bge-small-en-v1.5
- 384 dimensions
- Fast
- Production-ready
- Fully local (no API key)
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import List

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# ── Singleton model ─────────────────────────────────────────────
_model = None
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def _get_model():
    """
    Load FastEmbed model once (lazy init).
    Prevents repeated loading overhead.
    """
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        _model = TextEmbedding(model_name=MODEL_NAME)
        logger.info("FastEmbed model loaded successfully.")
    return _model


# ── Core embedding function ─────────────────────────────────────
def embed_texts_sync(texts: List[str]) -> List[List[float]]:
    """
    Synchronous batch embedding.

    Input:
        texts: list of strings

    Output:
        list of embedding vectors (float lists)
    """
    model = _get_model()

    # FastEmbed returns generator → convert to list
    embeddings = list(model.embed(texts))

    # Convert numpy arrays → Python lists for Pinecone compatibility
    return [emb.tolist() for emb in embeddings]


# ── Async wrapper (used by your ingestion pipeline) ─────────────
async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Async wrapper for CPU-bound embedding.
    Runs in thread pool executor.
    """
    loop = asyncio.get_event_loop()
    fn = functools.partial(embed_texts_sync, texts)
    return await loop.run_in_executor(None, fn)


# ── Single query embedding (async) ───────────────────────────────
async def embed_query(text: str) -> List[float]:
    """
    Embed a single query string (async).
    """
    results = await embed_texts([text])
    return results[0]


# ── Single query embedding (sync) ────────────────────────────────
def embed_query_sync(text: str) -> List[float]:
    """
    Sync embedding for ingestion or simple calls.
    """
    return embed_texts_sync([text])[0]