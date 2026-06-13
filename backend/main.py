"""
Python Q&A Assistant — FastAPI Backend
Retrieval: Pinecone vector database
Auth:       Supabase Auth (JWT Bearer token)
Chat history: Supabase (chat_sessions + chat_messages tables, RLS-enforced)
Memory:     Last MEMORY_WINDOW messages injected into LLM context
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Depends, Header
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
    ChatSession,
    ChatMessage,
    CreateSessionRequest,
    CreateSessionResponse,
    SummarizeResponse,
    LoginRequest,
    SignupRequest,
    AuthResponse,
    UserInfo,
)
from agents.qa_agent import run_agent, llm_stream

from rag.embeddings import embed_query, _get_model
from rag.retriever import retrieve_similar, get_sources_for_question
from chat.sessions import (
    create_session,
    add_message,
    get_sessions,
    get_messages,
    generate_summary,
    delete_session,
    get_supabase,
    get_conversation_memory,
)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:5173")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

VERSION = "3.0.0"
LLM_MODEL = "gpt-4o"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up embedding model, Pinecone index, and Supabase client on startup."""
    logger.info("Warming up embedding model...")
    await asyncio.get_event_loop().run_in_executor(None, _get_model)

    logger.info("Connecting to Pinecone...")
    from rag.retriever import get_async_client
    await get_async_client()

    logger.info("Connecting Supabase service client...")
    await get_supabase()

    logger.info("All systems ready.")
    yield
    logger.info("Shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Python Q&A Assistant",
    description="RAG-powered Python programming Q&A — Pinecone embeddings + Supabase Auth + chat history",
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


# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_user_jwt(
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Extract and validate the Bearer JWT from the Authorization header.
    Returns the raw JWT string for use with Supabase user-scoped client.
    Raises 401 if missing or malformed.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Use: 'Bearer <token>'",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty Bearer token")
    return token


async def get_optional_jwt(
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """Same as get_current_user_jwt but returns None instead of raising if missing."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip() or None


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    return {
        "status": "ok",
        "version": VERSION,
        "model": LLM_MODEL,
        "embedding_model": EMBEDDING_MODEL,
    }


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@app.post("/auth/signup", response_model=AuthResponse, status_code=201)
async def signup(request: SignupRequest):
    """Register a new user via Supabase Auth (uses service key — full auth API access)."""
    from supabase import acreate_client
    try:
        client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        res = await client.auth.sign_up({
            "email": request.email,
            "password": request.password,
        })
        if not res.user:
            raise HTTPException(status_code=400, detail="Signup failed — check your email and password.")
        session = res.session
        return AuthResponse(
            access_token=session.access_token if session else "",
            refresh_token=session.refresh_token if session else None,
            user=UserInfo(
                id=str(res.user.id),
                email=res.user.email or "",
                created_at=str(res.user.created_at) if res.user.created_at else None,
            ),
            message="Account created! Check your email to confirm your address.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[signup] error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Sign in an existing user and return JWT tokens."""
    from supabase import acreate_client
    try:
        client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        res = await client.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })
        if not res.user or not res.session:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        return AuthResponse(
            access_token=res.session.access_token,
            refresh_token=res.session.refresh_token,
            user=UserInfo(
                id=str(res.user.id),
                email=res.user.email or "",
                created_at=str(res.user.created_at) if res.user.created_at else None,
            ),
            message="Logged in successfully.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[login] error: {e}")
        raise HTTPException(status_code=401, detail="Invalid email or password.")


@app.post("/auth/logout", status_code=204)
async def logout(user_jwt: str = Depends(get_current_user_jwt)):
    """
    Logout endpoint. JWT auth is stateless — there is no server-side session to
    invalidate. The Supabase JS client on the frontend clears localStorage and
    revokes the refresh token. Nothing to do server-side.
    """
    # Frontend handles the actual sign-out via supabase.auth.signOut()
    pass


@app.get("/auth/me", response_model=UserInfo)
async def get_me(user_jwt: str = Depends(get_current_user_jwt)):
    """Return the current authenticated user's info decoded from the JWT (no network call)."""
    from base64 import b64decode as _b64decode
    try:
        # Decode JWT payload with base64 (no signature verification needed —
        # PostgREST re-validates the JWT against Supabase's public key for RLS)
        parts = user_jwt.split(".")
        if len(parts) < 2:
            raise HTTPException(status_code=401, detail="Malformed token.")
        payload_b64 = parts[1].replace("-", "+").replace("_", "/")
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(_b64decode(payload_b64).decode())
        user_id = payload.get("sub", "")
        email = payload.get("email", "") or payload.get("user_metadata", {}).get("email", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing sub claim.")
        return UserInfo(id=user_id, email=email, created_at=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_me] error: {e}")
        raise HTTPException(status_code=401, detail="Token expired or invalid.")


# ── POST /ask ─────────────────────────────────────────────────────────────────
@app.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    user_jwt: str = Depends(get_current_user_jwt),
):
    t_req = time.perf_counter()

    logger.info(
        f"[/ask] incoming q={request.question!r:.60} "
        f"session_id={request.session_id}"
    )

    # Load conversation memory
    memory = []
    session_id = request.session_id

    if session_id:
        try:
            memory = await get_conversation_memory(
                session_id,
                user_jwt,
            )

            logger.info(
                f"[/ask] loaded {len(memory)} memory messages"
            )

        except Exception as e:
            logger.warning(
                f"[/ask] memory fetch failed: {e}"
            )

    # Run LangGraph agent
    state = await run_agent(
        request.question,
        memory=memory,
    )

    # Build sources
    sources = [
        SourceDoc(
            content=s.get("content", ""),
            score=s.get(
                "score",
                s.get("similarity", 0.0),
            ),
            row_number=s.get("row_number"),
        )
        for s in state.get("sources", [])
    ]

    # Save messages
    if session_id:
        try:
            existing = await get_messages(
                session_id,
                user_jwt,
            )

            is_first = len(existing) == 0

            await add_message(
                session_id=session_id,
                role="user",
                content=request.question,
                user_jwt=user_jwt,
                first_user_message=is_first,
            )

            await add_message(
                session_id=session_id,
                role="assistant",
                content=state["answer"],
                user_jwt=user_jwt,
                sources=[s.model_dump() for s in sources],
                grounded=state["grounded"],
            )

        except Exception as e:
            logger.warning(
                f"[/ask] failed to save messages: {e}"
            )

    total_ms = (
        time.perf_counter() - t_req
    ) * 1000

    logger.info(
        f"[TIMER] /ask TOTAL REQUEST → "
        f"{total_ms:>7.1f} ms "
        f"grounded={state['grounded']}"
    )

    return AskResponse(
        answer=state["answer"],
        sources=sources,
        grounded=state["grounded"],
        session_id=session_id,
    )


# ── POST /ask/stream ──────────────────────────────────────────────────────────
# @app.post("/ask/stream")
# async def ask_stream(
#     request: StreamRequest,
#     user_jwt: str = Depends(get_current_user_jwt),
# ):
#     """SSE streaming endpoint — streams gpt-4o tokens in real time."""

#     async def event_generator():
#         from langchain_core.messages import SystemMessage, HumanMessage

#         logger.info(f"[stream] START: question={request.question!r}, session_id={request.session_id!r}")
#         # Fetch memory for this session
#         memory = []
#         if request.session_id:
#             try:
#                 memory = await get_conversation_memory(request.session_id, user_jwt)
#                 logger.info(f"[stream] Fetched {len(memory)} messages from memory.")
#                 for i, m in enumerate(memory):
#                     logger.info(f"[stream]   Memory msg {i}: role={type(m).__name__}, content={m.content[:100]!r}")
#             except Exception as e:
#                 logger.warning(f"[stream] memory fetch failed (continuing): {e}")
#         else:
#             logger.info("[stream] No session_id provided in request.")

#         # Embed & retrieve from Pinecone
#         try:
#             embedding = await embed_query(request.question)
#             docs = await retrieve_similar(embedding, top_k=5)

#             logger.info("=" * 80)
#             logger.info(f"Retrieved docs: {len(docs)}")

#             for d in docs:
#                 logger.info(
#                     f"score={d.get('similarity')} "
#                     f"content={d.get('content','')[:200]}"
#                 )

#             logger.info("=" * 80)
#             context = "\n\n---\n\n".join(
#                 [d.get("content", "")[:600] for d in docs]
#             )
#         except Exception:
#             context = ""
#             docs = []

#         system = (
#             "You are a Python programming expert helping data science learners. "
#             "Answer concisely using the provided Stack Overflow context. "
#             "Include code examples with proper markdown formatting. "
#             "Use the conversation history to understand follow-up questions."
#         )

#         user_prompt = (
#             f"Context:\n{context}\n\nQuestion: {request.question}"
#             if context
#             else f"Question (no context found): {request.question}"
#         )

#         # Build messages with memory
#         messages = [
#             SystemMessage(content=system),
#             *memory,
#             HumanMessage(content=user_prompt),
#         ]
#         logger.info(f"[stream] Total messages sent to LLM: {len(messages)}. Prompt length: {len(user_prompt)}")

#         yield "data: [START]\n\n"

#         full_answer = ""
#         try:
#             async for chunk in llm_stream.astream(messages):
#                 token = chunk.content
#                 if token:
#                     full_answer += token
#                     data = json.dumps({"token": token})
#                     yield f"data: {data}\n\n"
#         except Exception as e:
#             yield f"data: {json.dumps({'error': str(e)})}\n\n"

#         # Persist to chat session after stream completes
#         if request.session_id and full_answer:
#             try:
#                 existing = await get_messages(request.session_id, user_jwt)
#                 is_first = len(existing) == 0
#                 await add_message(
#                     request.session_id, "user", request.question, user_jwt,
#                     first_user_message=is_first,
#                 )
#                 sources_meta = [
#                     {"content": d.get("content", "")[:200], "score": d.get("similarity", 0.0)}
#                     for d in docs
#                 ]
#                 await add_message(
#                     request.session_id, "assistant", full_answer, user_jwt,
#                     sources=sources_meta,
#                     grounded=bool(docs),
#                 )
#             except Exception as e:
#                 logger.warning(f"Failed to persist streamed messages: {e}")

#         yield "data: [DONE]\n\n"

#     return StreamingResponse(
#         event_generator(),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "X-Accel-Buffering": "no",
#         },
#     )


# ── GET /sources ──────────────────────────────────────────────────────────────
@app.get("/sources")
async def get_sources_endpoint(
    question: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
    user_jwt: str = Depends(get_current_user_jwt),
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


# ── GET /sessions ─────────────────────────────────────────────────────────────
@app.get("/sessions", response_model=list[ChatSession])
async def list_sessions(user_jwt: str = Depends(get_current_user_jwt)):
    """List all chat sessions for the authenticated user."""
    sessions = await get_sessions(user_jwt)
    return sessions


# ── POST /sessions ────────────────────────────────────────────────────────────
@app.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def new_session(
    request: CreateSessionRequest = CreateSessionRequest(),
    user_jwt: str = Depends(get_current_user_jwt),
):
    """Create a new chat session for the authenticated user."""
    session = await create_session(user_jwt, title=request.title)
    return CreateSessionResponse(
        session_id=session["id"],
        title=session["title"],
        created_at=session["created_at"],
    )


# ── GET /sessions/{session_id}/messages ───────────────────────────────────────
@app.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def load_messages(
    session_id: str,
    user_jwt: str = Depends(get_current_user_jwt),
):
    """Load all messages for a chat session (must belong to the current user)."""
    msgs = await get_messages(session_id, user_jwt)
    if msgs is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return msgs


# ── POST /sessions/{session_id}/summarize ─────────────────────────────────────
@app.post("/sessions/{session_id}/summarize", response_model=SummarizeResponse)
async def summarize_session(
    session_id: str,
    user_jwt: str = Depends(get_current_user_jwt),
):
    """Generate and store an AI summary for the session."""
    summary = await generate_summary(session_id, user_jwt)
    return SummarizeResponse(session_id=session_id, summary=summary)


# ── DELETE /sessions/{session_id} ─────────────────────────────────────────────
@app.delete("/sessions/{session_id}", status_code=204)
async def remove_session(
    session_id: str,
    user_jwt: str = Depends(get_current_user_jwt),
):
    """Delete a session and all its messages (must belong to the current user)."""
    await delete_session(session_id, user_jwt)
