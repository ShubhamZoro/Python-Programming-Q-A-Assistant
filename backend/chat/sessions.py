"""
Chat session service — Supabase async CRUD with user-based auth.

Tables (created via supabase_setup.sql):
  chat_sessions (id, user_id, title, summary, created_at, updated_at)
  chat_messages (id, session_id, user_id, role, content, sources, grounded, created_at)

Strategy:
  The backend uses the SERVICE_ROLE key to connect to Supabase (we already have it),
  but then overrides the PostgREST Authorization header with the user's JWT on every
  data request. PostgREST uses the Authorization JWT — not the apikey — to determine
  the database role and evaluate RLS policies. So auth.uid() = user_id is enforced
  at the database level without needing a separate ANON key.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from dotenv import load_dotenv
from supabase import AsyncClient, acreate_client

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
MEMORY_WINDOW = int(os.getenv("MEMORY_WINDOW", "10"))

# ── Singleton service-role client (used for health-check / startup only) ──────
_service_client: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    """Return (or lazily create) the service-role Supabase client.
    Used only for health-check / startup warm-up.
    """
    global _service_client
    if _service_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _service_client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Service-role Supabase async client initialized.")
    return _service_client


async def _get_user_client(user_jwt: str) -> AsyncClient:
    """
    Return a Supabase client whose PostgREST calls run under the user's identity.

    How it works:
      1. We create a client with the SERVICE_ROLE key (for the apikey header).
      2. We call client.postgrest.auth(user_jwt) which sets
         Authorization: Bearer <user_jwt> on every PostgREST request.
      3. PostgREST evaluates RLS using the Authorization JWT, not the apikey.
         So auth.uid() = the user's UUID and ownership policies apply normally.

    This avoids needing a separate ANON key while still enforcing row-level security.
    """
    client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    # Override PostgREST to use the user JWT → RLS is enforced
    client.postgrest.auth(user_jwt)
    return client

async def _get_user_id(user_jwt: str) -> str:
    """
    Extract the user UUID (sub claim) from a Supabase JWT.

    We decode the payload section manually with base64 — no signature
    verification needed here because:
      • The JWT was already checked for presence in get_current_user_jwt()
      • Supabase signed it; any tampering would be caught at the database level
        (PostgREST re-validates the JWT before executing RLS policies)
      • python-jose struggles with ES256 keys when verify_signature=False
    """
    import base64
    import json as _json

    try:
        parts = user_jwt.split(".")
        if len(parts) < 2:
            raise ValueError("JWT must have at least 2 parts")

        # JWT payload is base64url-encoded; add padding so Python can decode it
        payload_b64 = parts[1]
        # base64url → base64 standard (replace URL-safe chars)
        payload_b64 = payload_b64.replace("-", "+").replace("_", "/")
        # Pad to a multiple of 4
        padding = (4 - len(payload_b64) % 4) % 4
        payload_b64 += "=" * padding

        payload = _json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        uid = payload.get("sub", "")
        if not uid:
            raise ValueError("JWT has no 'sub' claim")
        return uid
    except Exception as e:
        logger.error(f"[_get_user_id] Failed to decode JWT payload: {e}")
        raise ValueError("Invalid or expired token") from e


# ── Session CRUD ──────────────────────────────────────────────────────────────

async def create_session(user_jwt: str, title: str = "New Chat") -> dict:
    """Create a new chat session scoped to the authenticated user."""
    user_id = await _get_user_id(user_jwt)
    client = await _get_user_client(user_jwt)
    res = await (
        client.table("chat_sessions")
        .insert({"title": title, "user_id": user_id})
        .execute()
    )
    return res.data[0] if res.data else {}


async def get_sessions(user_jwt: str) -> List[dict]:
    """List sessions for the authenticated user, ordered by most recently updated."""
    client = await _get_user_client(user_jwt)
    res = await (
        client.table("chat_sessions")
        .select("id, title, summary, created_at, updated_at")
        .order("updated_at", desc=True)
        .execute()
    )
    return res.data or []


async def delete_session(session_id: str, user_jwt: str) -> bool:
    """Delete a session (and cascade its messages). RLS ensures ownership."""
    client = await _get_user_client(user_jwt)
    await (
        client.table("chat_sessions")
        .delete()
        .eq("id", session_id)
        .execute()
    )
    return True


async def _update_session_meta(
    session_id: str,
    user_jwt: str,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    """Update session title and/or summary + bump updated_at."""
    client = await _get_user_client(user_jwt)
    patch: dict = {"updated_at": "now()"}
    if title is not None:
        patch["title"] = title
    if summary is not None:
        patch["summary"] = summary
    await (
        client.table("chat_sessions")
        .update(patch)
        .eq("id", session_id)
        .execute()
    )


# ── Message CRUD ──────────────────────────────────────────────────────────────

async def add_message(
    session_id: str,
    role: str,
    content: str,
    user_jwt: str,
    sources: Optional[list] = None,
    grounded: bool = False,
    *,
    first_user_message: bool = False,
) -> dict:
    """
    Persist a message to Supabase, scoped to the authenticated user.
    If first_user_message=True, also updates the session title.
    """
    user_id = await _get_user_id(user_jwt)
    client = await _get_user_client(user_jwt)

    row = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "sources": sources or [],
        "grounded": grounded,
        "user_id": user_id,
    }
    res = await client.table("chat_messages").insert(row).execute()

    if first_user_message and role == "user":
        title = content[:80] + ("…" if len(content) > 80 else "")
        await _update_session_meta(session_id, user_jwt, title=title)
    else:
        await _update_session_meta(session_id, user_jwt)

    return res.data[0] if res.data else {}


async def get_messages(session_id: str, user_jwt: str) -> List[dict]:
    """Load all messages for a session in chronological order."""
    client = await _get_user_client(user_jwt)
    res = await (
        client.table("chat_messages")
        .select("id, session_id, role, content, sources, grounded, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return res.data or []


# ── Conversation Memory ───────────────────────────────────────────────────────

async def get_conversation_memory(
    session_id: str,
    user_jwt: str,
    window: int = MEMORY_WINDOW,
) -> list:
    """
    Return the last `window` messages as LangChain message objects
    (HumanMessage / AIMessage) for injection into the LLM prompt.
    Returns an empty list if session_id is None or there are no messages.
    """
    from langchain_core.messages import HumanMessage, AIMessage

    if not session_id:
        return []

    all_msgs = await get_messages(session_id, user_jwt)
    recent = all_msgs[-window:] if len(all_msgs) > window else all_msgs

    memory: list = []
    for m in recent:
        if m["role"] == "user":
            memory.append(HumanMessage(content=m["content"]))
        else:
            memory.append(AIMessage(content=m["content"]))
    return memory


# ── AI Summary ────────────────────────────────────────────────────────────────

async def generate_summary(session_id: str, user_jwt: str) -> str:
    """
    Use GPT-4o to summarise the conversation and store it on the session.
    Returns the generated summary string.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    messages = await get_messages(session_id, user_jwt)
    if not messages:
        return "No messages yet."

    transcript_lines = []
    for m in messages:
        role = "User" if m["role"] == "user" else "Assistant"
        snippet = m["content"][:400]
        transcript_lines.append(f"{role}: {snippet}")
    transcript = "\n".join(transcript_lines)

    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
    try:
        response = await llm.ainvoke([
            SystemMessage(content=(
                "You are a helpful assistant that summarises Python programming Q&A conversations. "
                "Write a concise 1-3 sentence summary of the conversation below. "
                "Focus on the key topics discussed and any solutions found."
            )),
            HumanMessage(content=f"Conversation:\n{transcript}"),
        ])
        summary = response.content.strip()
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        summary = "Could not generate summary."

    await _update_session_meta(session_id, user_jwt, summary=summary)
    return summary
