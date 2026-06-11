"""
Python Q&A Assistant — FastAPI Backend
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy imports after env loaded
from models.schemas import (
    AskRequest,
    AskResponse,
    SourceDoc,
    StreamRequest,
    HealthResponse,
)
from agents.qa_agent import run_agent, llm_stream
from tts.synthesizer import synthesize
from rag.embeddings import embed_query, _get_model
from rag.retriever import retrieve_similar, get_sources_for_question

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:5173")

VERSION = "1.0.0"
LLM_MODEL = "gpt-4o"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up embedding model + async Supabase client on startup."""
    logger.info("Warming up embedding model...")
    await asyncio.get_event_loop().run_in_executor(None, _get_model)
    logger.info("Connecting async Supabase client...")
    from rag.retriever import get_async_client
    await get_async_client()
    logger.info("All systems ready.")
    yield
    logger.info("Shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Python Q&A Assistant",
    description="RAG-powered Python programming Q&A with LangGraph + Supabase pgvector",
    version=VERSION,
    lifespan=lifespan,
)

# CORS
origins = ["*"] if ENVIRONMENT == "development" else [ALLOWED_ORIGIN]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    return {
        "status": "ok",
        "version": VERSION,
        "model": LLM_MODEL,
        "embedding_model": EMBEDDING_MODEL,
    }


# ── POST /ask ─────────────────────────────────────────────────────────────────
@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    t_req = time.perf_counter()
    logger.info(f"[/ask] incoming  q={request.question!r:.60}")

    # Run LangGraph agent (timing logged inside run_agent)
    state = await run_agent(request.question)

    # Build source list
    sources = [
        SourceDoc(
            content=s.get("content", ""),
            score=s.get("score", s.get("similarity", 0.0)),
            row_number=s.get("row_number"),
        )
        for s in state.get("sources", [])
    ]

    # TTS (optional)
    audio_b64 = None
    if request.voice:
        t_tts = time.perf_counter()
        audio_b64 = await synthesize(state["answer"])
        logger.info(f"[TIMER] /ask TTS synthesize             → {(time.perf_counter()-t_tts)*1000:>7.1f} ms")

    total_ms = (time.perf_counter() - t_req) * 1000
    logger.info(
        f"[TIMER] /ask TOTAL REQUEST              → {total_ms:>7.1f} ms  "
        f"voice={request.voice} grounded={state['grounded']}"
    )

    return AskResponse(
        answer=state["answer"],
        sources=sources,
        grounded=state["grounded"],
        audio_base64=audio_b64,
    )


# ── POST /ask/stream ──────────────────────────────────────────────────────────
@app.post("/ask/stream")
async def ask_stream(request: StreamRequest):
    """SSE streaming endpoint — streams gpt-4o tokens in real time."""

    async def event_generator():
        from langchain_core.messages import SystemMessage, HumanMessage

        # First embed & retrieve
        try:
            embedding = await embed_query(request.question)
            docs = await retrieve_similar(embedding, top_k=5)
            context = "\n\n---\n\n".join(
                [d.get("content", "")[:600] for d in docs]
            )
        except Exception:
            context = ""

        system = (
            "You are a Python programming expert helping data science learners. "
            "Answer concisely using the provided Stack Overflow context. "
            "Include code examples with proper markdown formatting."
        )

        user_prompt = (
            f"Context:\n{context}\n\nQuestion: {request.question}"
            if context
            else f"Question (no context found): {request.question}"
        )

        yield "data: [START]\n\n"

        try:
            async for chunk in llm_stream.astream([
                SystemMessage(content=system),
                HumanMessage(content=user_prompt),
            ]):
                token = chunk.content
                if token:
                    data = json.dumps({"token": token})
                    yield f"data: {data}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── GET /sources ──────────────────────────────────────────────────────────────
@app.get("/sources")
async def get_sources(
    question: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
):
    """Return top matching documents for a query without generating an answer."""
    embedding = await embed_query(question)
    docs = await get_sources_for_question(embedding, limit=limit)

    return {
        "question": question,
        "results": [
            {
                "content": d.get("content", "")[:300],
                "score": d.get("similarity", 0.0),
                "row_number": d.get("row_number"),
            }
            for d in docs
        ],
    }
