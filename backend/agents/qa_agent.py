"""
LangGraph Q&A Agent with 5 nodes:
  classify_node → retrieve_node → grade_node → generate_node
                                              → fallback_node

Timing logs are emitted at INFO level for every step so you can see
exactly where time is spent.  Example output:

  [TIMER] classify_node            →   812 ms
  [TIMER]   embed_query            →   48 ms
  [TIMER]   supabase_rpc           →   230 ms
  [TIMER] retrieve_node            →   280 ms
  [TIMER]   grade doc 1/5          →   390 ms
  [TIMER]   grade doc 2/5          →   410 ms
  [TIMER] grade_node               →  1950 ms  (3/5 passed)
  [TIMER] generate_node            →  3120 ms
  ─────────────────────────────────────────────
  [TIMER] TOTAL (run_agent)        →  6162 ms
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START

from rag.embeddings import embed_query
from rag.retriever import retrieve_similar

load_dotenv()
logger = logging.getLogger(__name__)


# ── Timer helper ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def timer(label: str):
    """Async context manager that logs elapsed ms for any code block."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[TIMER] {label:<35} → {ms:>7.1f} ms")


# ── LLM ──────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.2,
    api_key=os.getenv("OPENAI_API_KEY"),
    streaming=False,
)

llm_stream = ChatOpenAI(
    model="gpt-4o",
    temperature=0.2,
    api_key=os.getenv("OPENAI_API_KEY"),
    streaming=True,
)


# ── State Schema ─────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    question: str
    is_python_related: bool
    relevant_docs: list[dict]
    answer: str
    sources: list[dict]
    grounded: bool
    error: str | None


# ── Node 1: Classify ─────────────────────────────────────────────────────────
CLASSIFY_PROMPT = """You are a query classifier. Determine if the following question is related to Python programming.
Consider it Python-related if it involves: Python syntax, Python libraries, Python frameworks, Python data science tools,
Python scripting, Python debugging, or Python-specific concepts.

Question: {question}

Respond with ONLY 'yes' or 'no'."""


async def classify_node(state: AgentState) -> AgentState:
    """Classify if the question is Python-related."""
    async with timer("classify_node  [LLM call]"):
        try:
            response = await llm.ainvoke(
                CLASSIFY_PROMPT.format(question=state["question"])
            )
            is_python = response.content.strip().lower().startswith("yes")
            logger.info(f"[classify_node] result → {'PYTHON' if is_python else 'NOT PYTHON'}")
            return {**state, "is_python_related": is_python}
        except Exception as e:
            logger.error(f"[classify_node] error: {e}")
            return {**state, "is_python_related": False, "error": str(e)}


# ── Node 2: Retrieve ─────────────────────────────────────────────────────────
async def retrieve_node(state: AgentState) -> AgentState:
    """Embed query and retrieve similar documents from Supabase pgvector."""
    try:
        async with timer("retrieve_node  [embed_query]"):
            embedding = await embed_query(state["question"])

        async with timer("retrieve_node  [supabase_rpc]"):
            docs = await retrieve_similar(embedding, top_k=5, match_threshold=0.3)

        logger.info(f"[retrieve_node] returned {len(docs)} docs")
        return {**state, "relevant_docs": docs}
    except Exception as e:
        logger.error(f"[retrieve_node] error: {e}")
        return {**state, "relevant_docs": [], "error": str(e)}


# ── Node 3: Grade ─────────────────────────────────────────────────────────────
GRADE_PROMPT = """You are grading whether a retrieved document is relevant to answer a Python question.

Question: {question}

Document content (excerpt):
{content}

Is this document relevant to answering the question? Respond ONLY with 'yes' or 'no'."""


async def grade_node(state: AgentState) -> AgentState:
    """Grade retrieved documents for relevance. Filter out irrelevant ones."""
    docs = state.get("relevant_docs", [])
    if not docs:
        logger.info("[grade_node] no docs to grade")
        return {**state, "relevant_docs": []}

    graded = []
    t_node = time.perf_counter()

    for i, doc in enumerate(docs, 1):
        content_excerpt = doc.get("content", "")[:500]
        async with timer(f"grade_node     [doc {i}/{len(docs)} LLM call]"):
            try:
                response = await llm.ainvoke(
                    GRADE_PROMPT.format(
                        question=state["question"],
                        content=content_excerpt,
                    )
                )
                passed = response.content.strip().lower().startswith("yes")
                if passed:
                    graded.append(doc)
                logger.info(f"[grade_node] doc {i}/{len(docs)} → {'PASS' if passed else 'FAIL'}")
            except Exception as e:
                logger.warning(f"[grade_node] grading error for doc {i}: {e}")
                graded.append(doc)  # Keep on error

    total_grade_ms = (time.perf_counter() - t_node) * 1000
    logger.info(
        f"[TIMER] grade_node     [total]             → {total_grade_ms:>7.1f} ms  "
        f"({len(graded)}/{len(docs)} passed)"
    )
    return {**state, "relevant_docs": graded}


# ── Node 4: Generate ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Python programming expert helping data science learners.
Answer the question using ONLY the provided context from Stack Overflow.
Be concise, accurate, and include code examples when relevant.
If the context doesn't fully answer the question, say so honestly.
Format code blocks with proper markdown. Always mention if your answer
is grounded in retrieved sources or generated from model knowledge."""

GENERATE_PROMPT = """Context from Stack Overflow:
{context}

Question: {question}

Please provide a comprehensive answer using the context above."""


async def generate_node(state: AgentState) -> AgentState:
    """Generate answer grounded in retrieved documents."""
    docs = state.get("relevant_docs", [])
    context = "\n\n---\n\n".join(
        [doc.get("content", "")[:800] for doc in docs]
    )

    sources = [
        {
            "content": doc.get("content", "")[:200],
            "score": doc.get("similarity", 0.0),
            "row_number": doc.get("row_number"),
        }
        for doc in docs
    ]

    async with timer("generate_node  [LLM call]"):
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            response = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=GENERATE_PROMPT.format(
                    context=context,
                    question=state["question"],
                )),
            ])
            return {
                **state,
                "answer": response.content,
                "sources": sources,
                "grounded": True,
            }
        except Exception as e:
            logger.error(f"[generate_node] error: {e}")
            return {
                **state,
                "answer": "I encountered an error generating the answer. Please try again.",
                "sources": sources,
                "grounded": False,
                "error": str(e),
            }


# ── Node 5: Fallback ─────────────────────────────────────────────────────────
FALLBACK_PROMPT = """You are a Python programming expert.
No relevant Stack Overflow answers were found for the question below.
Answer using your own knowledge, but clearly state that this answer is from your general knowledge
and not from retrieved sources. Be accurate and include code examples where appropriate.

Question: {question}"""


async def fallback_node(state: AgentState) -> AgentState:
    """Fallback: answer from model knowledge with disclaimer."""
    async with timer("fallback_node  [LLM call]"):
        try:
            response = await llm.ainvoke(
                FALLBACK_PROMPT.format(question=state["question"])
            )
            return {
                **state,
                "answer": response.content,
                "sources": [],
                "grounded": False,
            }
        except Exception as e:
            logger.error(f"[fallback_node] error: {e}")
            return {
                **state,
                "answer": "I'm unable to answer this question at the moment. Please try again later.",
                "sources": [],
                "grounded": False,
                "error": str(e),
            }


# ── Not Python Response ───────────────────────────────────────────────────────
async def not_python_node(state: AgentState) -> AgentState:
    """Return a graceful refusal for non-Python questions."""
    logger.info("[not_python_node] returning refusal (no LLM call)")
    return {
        **state,
        "answer": (
            "I'm a Python programming assistant and can only answer Python-related questions. "
            "Your question doesn't appear to be about Python programming. "
            "Please ask about Python syntax, libraries, frameworks, or concepts!"
        ),
        "sources": [],
        "grounded": False,
    }


# ── Routing Functions ─────────────────────────────────────────────────────────
def route_after_classify(state: AgentState) -> str:
    return "retrieve_node" if state.get("is_python_related") else "not_python_node"


def route_after_grade(state: AgentState) -> str:
    return "generate_node" if state.get("relevant_docs") else "fallback_node"


# ── Build Graph ───────────────────────────────────────────────────────────────
def build_agent() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("classify_node", classify_node)
    graph.add_node("retrieve_node", retrieve_node)
    graph.add_node("grade_node", grade_node)
    graph.add_node("generate_node", generate_node)
    graph.add_node("fallback_node", fallback_node)
    graph.add_node("not_python_node", not_python_node)

    graph.add_edge(START, "classify_node")
    graph.add_conditional_edges(
        "classify_node",
        route_after_classify,
        {
            "retrieve_node": "retrieve_node",
            "not_python_node": "not_python_node",
        },
    )
    graph.add_edge("retrieve_node", "grade_node")
    graph.add_conditional_edges(
        "grade_node",
        route_after_grade,
        {
            "generate_node": "generate_node",
            "fallback_node": "fallback_node",
        },
    )
    graph.add_edge("generate_node", END)
    graph.add_edge("fallback_node", END)
    graph.add_edge("not_python_node", END)

    return graph.compile()


# Compiled agent (singleton)
qa_agent = build_agent()


async def run_agent(question: str) -> AgentState:
    """Run the full agent pipeline and return final state."""
    logger.info(f"{'─'*55}")
    logger.info(f"[run_agent] START  q={question!r:.60}")

    t0 = time.perf_counter()

    initial_state: AgentState = {
        "question": question,
        "is_python_related": False,
        "relevant_docs": [],
        "answer": "",
        "sources": [],
        "grounded": False,
        "error": None,
    }
    result = await qa_agent.ainvoke(initial_state)

    total_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        f"[TIMER] {'TOTAL (run_agent)':<35} → {total_ms:>7.1f} ms  "
        f"grounded={result['grounded']}"
    )
    logger.info(f"{'─'*55}")

    return result
