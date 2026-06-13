# Python Q&A Assistant

> A RAG-powered Python programming Q&A assistant using Stack Overflow data, a LangGraph agentic pipeline, GPT-4o, and open-source embeddings — with a full-stack React frontend, Supabase auth, and persistent chat history.

---

## Architecture

```
User (Browser)
      │
      ▼
React Frontend  (Vite + Vercel)
      │  POST /ask
      ▼
FastAPI Backend  (Render)
      │
      ▼
LangGraph Agent
  ├── classify_node   → GPT-4o  (is this Python-related?)
  ├── memory_node     → local   (conversation history queries)
  ├── rewrite_node    → GPT-4o  (resolve follow-up references)
  ├── retrieve_node   → BAAI/bge-small-en-v1.5 + Pinecone
  ├── grade_node      → GPT-4o  (relevance filter, per doc)
  ├── generate_node   → GPT-4o  (grounded answer with memory)
  ├── fallback_node   → GPT-4o  (model-knowledge + disclaimer)
  └── not_python_node → static  (graceful refusal)
      │
      ├── Supabase  (chat_sessions + chat_messages, RLS-enforced)
```

---

## Features

- **7-node LangGraph agent** — classify → rewrite → retrieve → grade → generate, with memory and fallback branches
- **Query rewriting** — vague follow-ups ("how does it work?") are resolved into self-contained queries before retrieval
- **Conversation memory** — last N messages injected into every LLM call for multi-turn coherence
- **Relevance grading** — each retrieved doc is scored by GPT-4o before generation, preventing hallucination on off-topic results
- **Graceful non-Python refusal** — classifier gates the pipeline; off-topic queries return a polite message without hitting retrieval
- **Per-session chat history** — stored in Supabase with row-level security; messages persist across page reloads
- **AI session summaries** — GPT-4o can summarize any conversation and store it on the session record
- **Full auth flow** — email/password + Google OAuth via Supabase Auth; JWT forwarded to backend on every request
- **Voice input** — browser Web Speech API for STT; result appended to the chat input
- **Pinecone vector store** — 50K+ Stack Overflow Q&A pairs ingested with async pipeline, resumable via checkpoint

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | GPT-4o (OpenAI) |
| Agent Framework | LangGraph + LangChain |
| Backend | FastAPI + Uvicorn |
| Embeddings | BAAI/bge-small-en-v1.5 via FastEmbed (local, free) |
| Vector Database | Pinecone (serverless, cosine, 384-dim) |
| Auth & DB | Supabase (Auth + PostgreSQL + RLS) |
| Chat History | Supabase `chat_sessions` + `chat_messages` |
| Frontend | React 19 + Vite 8 |
| Deployment | Render (backend) + Vercel (frontend) |

---

## Project Structure

```
.
├── backend/
│   ├── agents/
│   │   └── qa_agent.py          # LangGraph StateGraph (7 nodes)
│   ├── chat/
│   │   └── sessions.py          # Supabase session + message CRUD
│   ├── rag/
│   │   ├── embeddings.py        # FastEmbed wrapper (BAAI/bge-small)
│   │   ├── retriever.py         # Pinecone query + async wrapper
│   │   ├── ingest.py            # Supabase ingestion (legacy)
│   │   └── pinecone_ingest.py   # Async Pinecone ingestion pipeline
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response schemas
│   ├── main.py                  # FastAPI app + all endpoints
│   ├── config.py                # Settings from environment
│   ├── supabase_setup.sql       # DB schema + RLS policies
│   ├── render.yaml              # Render deployment config
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/          # ChatInterface, MessageBubble, Sidebar, AuthPage, …
    │   ├── hooks/               # useAuth, useChat, useSessions, useSpeech, useStream
    │   └── lib/                 # api.js, supabaseClient.js
    ├── index.html
    └── package.json
```

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 20+
- A [Supabase](https://supabase.com) project (free tier)
- A [Pinecone](https://pinecone.io) account (free tier)
- OpenAI API key

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY,
#         PINECONE_API_KEY, PINECONE_INDEX_NAME
```

Run the Supabase schema (one-time — paste into the Supabase SQL Editor):

```bash
# Open supabase_setup.sql and run all four sections in order
```

Ingest Stack Overflow data into Pinecone (one-time, ~30–60 min for 50K records):

```bash
python rag/pinecone_ingest.py
# Resumes automatically from checkpoint on interruption
# Run with --reset to start over
```

Start the API server:

```bash
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.example .env
# Set VITE_API_URL=http://localhost:8000
# Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY
npm install
npm run dev
```

Frontend: http://localhost:5173

---

## LangGraph Agent

The agent is a `StateGraph` with seven nodes and conditional routing:

```
START → classify_node
            ├─ memory query  → memory_node       → END
            ├─ python        → rewrite_node
            │                      └─ retrieve_node
            │                              └─ grade_node
            │                                    ├─ docs found  → generate_node  → END
            │                                    └─ no docs     → fallback_node  → END
            └─ not python    → not_python_node   → END
```

**State fields:**

| Field | Type | Description |
|---|---|---|
| `question` | `str` | Original user question |
| `rewritten_question` | `str` | Standalone query after reference resolution |
| `is_python_related` | `bool` | Output of classify_node |
| `relevant_docs` | `list[dict]` | Docs that passed grading |
| `answer` | `str` | Final response text |
| `sources` | `list[dict]` | Source snippets with similarity scores |
| `grounded` | `bool` | Whether answer is backed by retrieved docs |
| `conversation_memory` | `list` | LangChain `HumanMessage` / `AIMessage` objects |

**Timing:** every node is wrapped in an async `timer()` context manager that logs elapsed ms at INFO level, making it easy to identify latency bottlenecks.

---

## RAG Pipeline

**Data source:** Stack Overflow Python Q&A pairs preprocessed from the Kaggle dataset (`question_answer.json`, 262K records total; 50K ingested by default).

**Ingestion pipeline** (`rag/pinecone_ingest.py`):

```
JSON file
    │
    ▼ producer (main thread)
embed_queue  (asyncio.Queue)
    │
    ▼ N embed workers (ThreadPoolExecutor — CPU-bound)
upsert_queue (asyncio.Queue)
    │
    ▼ M upsert workers (AsyncPinecone — true async I/O)
Pinecone index
```

- Embeddings: `BAAI/bge-small-en-v1.5` via FastEmbed — 384-dim, runs locally, zero API cost
- Default concurrency: `EMBED_WORKERS=2`, `UPSERT_WORKERS=4`, `BATCH_SIZE=100`
- Checkpoint file (`.ingest_checkpoint`) makes ingestion resumable after interruption
- Idempotent: pass `--reset` to restart from row 0

**Retrieval** (`rag/retriever.py`):

- `top_k=5`, `match_threshold=0.3` (cosine similarity)
- Pinecone sync client wrapped in `asyncio.run_in_executor` so FastAPI stays non-blocking

---

## API Endpoints

### WebSocket — none (HTTP only)

### REST

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Version + model info |
| `POST` | `/ask` | Bearer JWT |
| `GET` | `/sources` | Bearer JWT | Retrieve matching docs without answering |
| `POST` | `/auth/signup` | — | Create account |
| `POST` | `/auth/login` | — | Sign in, returns JWT |
| `POST` | `/auth/logout` | Bearer JWT | Sign out (stateless) |
| `GET` | `/auth/me` | Bearer JWT | Current user info |
| `GET` | `/sessions` | Bearer JWT | List user's sessions |
| `POST` | `/sessions` | Bearer JWT | Create session |
| `GET` | `/sessions/{id}/messages` | Bearer JWT | Load message history |
| `POST` | `/sessions/{id}/summarize` | Bearer JWT | Generate AI summary |
| `DELETE` | `/sessions/{id}` | Bearer JWT | Delete session + messages |

**`POST /ask` request:**

```json
{ "question": "How do list comprehensions work?", "session_id": "uuid" }
```

**`POST /ask` response:**

```json
{
  "answer": "...",
  "sources": [{ "content": "...", "score": 0.87, "row_number": 12345 }],
  "grounded": true,
  "session_id": "uuid"
}
```

---

## Auth & Security

The backend uses the Supabase **service role key** for connectivity but overrides PostgREST's `Authorization` header with the user's JWT on every data call via `client.postgrest.auth(user_jwt)`. This means:

- PostgREST evaluates **RLS policies** using `auth.uid()` from the user's JWT
- Each user can only read and write their own sessions and messages
- JWT decoding for `user_id` extraction is done manually (base64 payload, no signature verification needed — PostgREST re-validates the JWT against Supabase's public key)

---

## Deployment

### Backend → Render

```bash
# render.yaml is included — just connect the repo
# Required env vars:
OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY,
PINECONE_API_KEY, PINECONE_INDEX_NAME, ENVIRONMENT=production, ALLOWED_ORIGIN
```

### Frontend → Vercel

```bash
# Connect frontend/ directory
# Required env vars:
VITE_API_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
```

### Live URLs

| Service | URL |
|---|---|
| Frontend | *(add after deployment)* |
| Backend API | *(add after deployment)* |
| API Docs | `{backend-url}/docs` |

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

8 tests covering health check, valid Q&A, voice response, non-Python refusal, empty input validation, SSE streaming, source retrieval, and structured response shape.

---

## Design Decisions

**Why LangGraph over bare function calling?**
Explicit `StateGraph` gives named nodes, conditional edges, and an append-only `conversation_memory` field — all of which make multi-turn context and the classify→rewrite→retrieve→grade→generate pipeline easy to inspect, test, and extend.

**Why open-source embeddings (BAAI/bge-small-en-v1.5)?**
Embedding 50K+ records with OpenAI would incur non-trivial cost and rate-limit management. FastEmbed runs entirely locally at ~50ms per batch with zero API calls. The same model runs at query time, so the vector space is consistent.

**Why Pinecone over pgvector?**
Pinecone's async client and serverless index handle high-concurrency vector queries without adding infrastructure. The legacy pgvector tables remain in `supabase_setup.sql` for reference but are no longer queried.

**Why query rewriting?**
Follow-up questions like "can you show me an example?" have no useful embedding on their own. The `rewrite_node` resolves references against the last few turns before retrieval, dramatically improving precision on conversational queries.

**Why per-user JWT scoping instead of separate anon/service clients?**
Forwarding the user's JWT to PostgREST enables native RLS enforcement without maintaining a separate connection pool or implementing ownership checks in application code.

---

## Scaling Plan for 100+ Concurrent Users

| Layer | Strategy |
|---|---|
| FastAPI | `gunicorn` with 4–8 `uvicorn` workers |
| Embeddings | Loaded once per worker; CPU work in `asyncio.run_in_executor` |
| Pinecone | Serverless index handles ~1000 QPS; no changes needed at this scale |
| Supabase | Built-in PgBouncer connection pooling |
| Caching | Redis (TTL 1h) for repeated questions — skip LLM on cache hit |
| Horizontal scaling | Multiple Render instances behind load balancer |
| OpenAI rate limits | Exponential backoff via `tenacity`; batch embedding at ingestion |

**Estimated cost at 100 req/min:**
- GPT-4o: ~$0.30/1K tokens × avg 800 tokens/req × 6K req/hr ≈ **$1.44/hr**
- Supabase free tier: sufficient up to ~200K req/day
- Render: ~$14/mo for two instances

---

## Known Limitations

- **In-memory Pinecone client** — the sync client is wrapped in an executor; a production setup should use `AsyncPinecone` throughout the request path
- **Grade node latency** — grading 5 docs with individual GPT-4o calls adds ~2s; batching or a smaller model (e.g. GPT-4o-mini) would reduce this significantly
- **SSE streaming endpoint** — `POST /ask/stream` is implemented but commented out in `main.py`; it works locally but was disabled pending session persistence integration
- **Google OAuth** — requires the real Supabase anon key with PKCE flow enabled; the current frontend uses implicit flow
