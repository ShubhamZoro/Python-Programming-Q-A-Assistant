"""
Open-source embedding using sentence-transformers.
Model: all-MiniLM-L6-v2 (384-dim, fast, good quality for semantic search)
No API key required — runs fully locally.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import List

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Singleton model — loaded once on first import
_model: SentenceTransformer | None = None
MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model() -> SentenceTransformer:
    """Load model lazily (once) to avoid cold-start on every call."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _model


def embed_texts_sync(texts: List[str]) -> List[List[float]]:
    """Synchronous batch embedding — returns list of float vectors."""
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Async wrapper — runs CPU-bound encoding in a thread pool."""
    loop = asyncio.get_event_loop()
    fn = functools.partial(embed_texts_sync, texts)
    return await loop.run_in_executor(None, fn)


async def embed_query(text: str) -> List[float]:
    """Embed a single query string asynchronously."""
    results = await embed_texts([text])
    return results[0]


def embed_query_sync(text: str) -> List[float]:
    """Synchronous single query embedding (for ingestion script)."""
    return embed_texts_sync([text])[0]
