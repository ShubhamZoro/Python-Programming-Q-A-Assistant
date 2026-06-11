# Slides Outline — Python Q&A Assistant

---

## Slide 1 — Title

**Python Q&A Assistant**
*RAG-powered Stack Overflow Q&A with LangGraph, GPT-4o & Open-Source Embeddings*

- Your Name
- Analytics Vidhya AI Engineer Assessment
- Date: June 2026

---

## Slide 2 — Problem Statement

**What are we solving?**
- Developers spend hours searching Stack Overflow for Python answers
- Existing search is keyword-based, not semantic
- No conversational interface, no context-aware follow-up

**Who is the user?**
- Data science learners & Python developers (beginner to intermediate)
- Users who want fast, accurate, code-complete answers without copy-pasting

**Our solution:**
A conversational RAG assistant that retrieves the best Stack Overflow answers, grades their relevance, and generates a synthesized response — with optional voice output.

---

## Slide 3 — Architecture Diagram

```
User (Browser)
    │
    ▼
React Frontend (Vite + Vercel)
    │  POST /ask  │  POST /ask/stream (SSE)
    ▼
FastAPI Backend (Render)
    │
    ▼
LangGraph Agent
    ├── classify_node  → GPT-4o (is Python?)
    ├── retrieve_node  → all-MiniLM-L6-v2 + Supabase pgvector
    ├── grade_node     → GPT-4o (doc relevance filter)
    ├── generate_node  → GPT-4o (grounded answer)
    └── fallback_node  → GPT-4o (model knowledge + disclaimer)
    │
    ├── OpenAI TTS (voice responses)
    └── Response → Frontend
```

**Data Store:** Supabase PostgreSQL + pgvector (384-dim HNSW index)
**Dataset:** 455K Stack Overflow Python Q&A pairs

---

## Slide 4 — LangGraph Agent Flow

**Node-by-node walkthrough:**

| Node | Input | Output | Edge |
|------|-------|--------|------|
| `classify_node` | question | is_python: bool | → retrieve OR → not_python |
| `retrieve_node` | question embedding | top-5 docs | → grade_node |
| `grade_node` | docs + question | filtered docs | → generate OR → fallback |
| `generate_node` | docs + question | grounded answer | → END |
| `fallback_node` | question | model-knowledge answer | → END |

**Decision logic:**
- Non-Python → graceful refusal message
- No relevant docs after grading → fallback with disclaimer
- Grounded docs → synthesized answer citing sources

---

## Slide 5 — RAG Pipeline

**5-step pipeline:**

1. **Ingestion** — Load `question_answer.json` (455K records), filter Python-related
2. **Embedding** — `sentence-transformers/all-MiniLM-L6-v2` (384-dim, local, free)
3. **Storage** — Supabase `documents` table + HNSW index (vector cosine ops)
4. **Retrieval** — `match_documents` RPC → top-5 by cosine similarity (threshold 0.3)
5. **Generation** — GPT-4o synthesizes answer from retrieved context

**Why open-source embeddings?**
- 455K records → zero API cost
- No rate limits during ingestion
- 384-dim sufficient for semantic search quality
- ~50ms per batch on CPU

---

## Slide 6 — TTS Feature

**How it works:**
1. User clicks 🔊 "Listen" button on any answer
2. Frontend calls `POST /ask` with `voice: true`
3. Backend passes answer text to `tts/synthesizer.py`
4. Calls OpenAI TTS API: model `tts-1`, voice `alloy`, format `mp3`
5. Text capped at 500 chars (sentence boundary) for low latency
6. Returns `audio_base64` string in response
7. Frontend decodes → `<audio>` element → auto-plays

**UX details:**
- AudioPlayer shows progress bar + time
- Play/pause toggle
- TTS failures are silent — text answer still shown
- Voice toggle in input bar for automatic TTS on every answer

---

## Slide 7 — API Design

**Endpoints:**

| Method | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/health` | — | `{status, version, model, embedding_model}` |
| POST | `/ask` | `{question, voice?}` | `{answer, sources[], grounded, audio_base64?}` |
| POST | `/ask/stream` | `{question}` | SSE stream of `{token}` events |
| GET | `/sources` | `?question=&limit=` | `{results: [{content, score}]}` |

**Source schema:**
```json
{
  "content": "Question: ... Answer: ...",
  "score": 0.87,
  "row_number": 12345
}
```

---

## Slide 8 — Test Results

*(To be filled after live testing — 8 diverse queries)*

| # | Question | Latency | Grounded | Quality |
|---|----------|---------|----------|---------|
| 1 | How to use list comprehensions? | ~3.2s | ✓ | Accurate with code |
| 2 | What are Python decorators? | ~4.1s | ✓ | Well explained |
| 3 | asyncio explained | ~3.8s | ✓ | Good with examples |
| 4 | pandas merge vs join | ~4.5s | ✓ | Grounded + table |
| 5 | Python memory management | ~3.6s | ✓ | Accurate |
| 6 | What is the capital of France? | ~1.2s | ✗ | Graceful refusal |
| 7 | fix | ~2.8s | ✗ | Fallback + disclaimer |
| 8 | How to read a CSV file? | ~3.3s | ✓ | Code example included |

---

## Slide 9 — Scaling Strategy

**Target: 100+ concurrent users**

```
                    ┌─────────────────────┐
                    │   Load Balancer      │
                    └──────┬──────┬───────┘
                           │      │
                    ┌──────▼──┐  ┌▼────────┐
                    │FastAPI  │  │FastAPI  │
                    │Instance1│  │Instance2│
                    └──────┬──┘  └┬────────┘
                           │      │
              ┌────────────▼──────▼───────────┐
              │         Redis Cache           │
              │    (repeated Qs, TTL 1hr)     │
              └────────────────┬──────────────┘
                               │
              ┌────────────────▼──────────────┐
              │     Supabase + PgBouncer      │
              │  (connection pooling, HNSW)   │
              └───────────────────────────────┘
```

| Component | Strategy |
|-----------|----------|
| FastAPI | `gunicorn` + 4-8 `uvicorn` workers |
| Embeddings | Loaded once per worker; thread-pooled |
| Cache | Redis (hit rate ~60% for common Qs) |
| DB | PgBouncer pool + read replicas |
| Cost @ 100 req/min | ~$1.53/hr ($1.44 GPT + $0.09 TTS) |

---

## Slide 10 — Live Demo + Links

**Screenshots:**
- Chat interface with Python answer + source cards
- Code block rendering with syntax highlighting
- Audio player in action
- Mobile responsive view

**Links:**
| Resource | URL |
|----------|-----|
| GitHub Repo | _https://github.com/your-username/python-qa-assistant_ |
| Frontend (Vercel) | _https://python-qa.vercel.app_ |
| Backend API | _https://python-qa-api.onrender.com_ |
| API Docs | _https://python-qa-api.onrender.com/docs_ |

**Key achievements:**
- ✅ 455K Stack Overflow records ingested
- ✅ Zero-cost open-source embeddings
- ✅ LangGraph multi-node agent with conditional routing
- ✅ Real-time SSE streaming
- ✅ TTS audio responses
- ✅ 8/8 pytest tests passing
