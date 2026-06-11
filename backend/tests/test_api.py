"""
pytest tests for the Python Q&A Assistant API.
Run: pytest tests/ -v

Uses httpx.AsyncClient with ASGITransport (no real server needed).
Mocks Supabase and OpenAI calls for deterministic results.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client():
    """Create async test client with mocked dependencies."""

    # Mock embedding (384-dim all-MiniLM-L6-v2 vector)
    mock_embedding = [0.01] * 384

    # Mock Supabase retrieval results
    mock_docs = [
        {
            "id": 1,
            "content": "Question: How to use list comprehensions?\nAnswer: Use [expr for item in iterable]",
            "similarity": 0.92,
            "row_number": 1,
        },
        {
            "id": 2,
            "content": "Question: Python lambda functions?\nAnswer: lambda args: expression",
            "similarity": 0.85,
            "row_number": 2,
        },
    ]

    # Mock LLM responses
    mock_llm_response = MagicMock()
    mock_llm_response.content = (
        "List comprehensions in Python provide a concise way to create lists.\n\n"
        "```python\n# Basic syntax\nnumbers = [x**2 for x in range(10)]\n```\n\n"
        "*This answer is grounded in retrieved Stack Overflow sources.*"
    )

    with (
        patch("rag.embeddings.embed_query", new_callable=AsyncMock, return_value=mock_embedding),
        patch("rag.embeddings._get_model", return_value=MagicMock()),
        patch("rag.retriever.retrieve_similar", new_callable=AsyncMock, return_value=mock_docs),
        patch("rag.retriever.get_sources_for_question", new_callable=AsyncMock, return_value=mock_docs),
        patch("agents.qa_agent.llm") as mock_llm,
        patch("agents.qa_agent.llm_stream") as mock_stream_llm,
        patch("tts.synthesizer.synthesize", new_callable=AsyncMock, return_value="bW9ja19hdWRpbw=="),
    ):
        # Configure LLM mock
        mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)

        # Configure streaming mock
        async def mock_astream(*args, **kwargs):
            tokens = ["List ", "comprehensions ", "are ", "great!"]
            for token in tokens:
                chunk = MagicMock()
                chunk.content = token
                yield chunk

        mock_stream_llm.astream = mock_astream

        from main import app
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


# ── Test 1: Health endpoint ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health_returns_200(client):
    """GET /health returns 200 with correct schema."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "model" in data
    assert "embedding_model" in data
    assert data["embedding_model"] == "all-MiniLM-L6-v2"


# ── Test 2: Valid Python question ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ask_valid_python_question(client):
    """POST /ask with valid Python question returns answer + sources."""
    response = await client.post(
        "/ask",
        json={"question": "How do I use list comprehensions in Python?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert "sources" in data
    assert isinstance(data["sources"], list)
    assert "grounded" in data


# ── Test 3: Voice=True returns audio ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_ask_with_voice_returns_audio(client):
    """POST /ask with voice=true returns non-null audio_base64."""
    response = await client.post(
        "/ask",
        json={"question": "What is a Python decorator?", "voice": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["audio_base64"] is not None
    assert len(data["audio_base64"]) > 0


# ── Test 4: Non-Python question → graceful refusal ────────────────────────────
@pytest.mark.asyncio
async def test_ask_non_python_question_graceful_refusal(client):
    """POST /ask with non-Python question returns graceful refusal."""
    with patch("agents.qa_agent.llm") as mock_llm:
        # Simulate classify returning 'no'
        refusal = MagicMock()
        refusal.content = "no"
        mock_llm.ainvoke = AsyncMock(return_value=refusal)

        response = await client.post(
            "/ask",
            json={"question": "What is the capital of France?"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "python" in data["answer"].lower() or "not" in data["answer"].lower()
    assert data["grounded"] is False


# ── Test 5: Empty question → 422 validation ────────────────────────────────
@pytest.mark.asyncio
async def test_ask_empty_string_returns_422(client):
    """POST /ask with empty string returns 422 validation error."""
    response = await client.post("/ask", json={"question": ""})
    assert response.status_code == 422


# ── Test 6: Streaming endpoint ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ask_stream_returns_sse(client):
    """POST /ask/stream returns SSE content-type and streams tokens."""
    response = await client.post(
        "/ask/stream",
        json={"question": "How do I read a file in Python?"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert len(response.content) > 0


# ── Test 7: GET /sources returns ranked docs ─────────────────────────────────
@pytest.mark.asyncio
async def test_get_sources_returns_ranked_docs(client):
    """GET /sources returns ranked docs with scores."""
    response = await client.get(
        "/sources",
        params={"question": "Python generators", "limit": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    for doc in data["results"]:
        assert "content" in doc
        assert "score" in doc


# ── Test 8: Short/ambiguous question still returns structured response ────────
@pytest.mark.asyncio
async def test_ask_short_question_returns_structured_response(client):
    """POST /ask with short/ambiguous question still returns structured response."""
    response = await client.post(
        "/ask",
        json={"question": "Python list"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data
    assert "grounded" in data
    assert isinstance(data["grounded"], bool)
