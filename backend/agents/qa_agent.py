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

MEMORY_KEYWORDS = [
    "last question",
    "previous question",
    "what did i ask",
    "what was my question",
    "what did you say",
    "your last answer",
    "previous answer",
    "conversation history",
    "chat history",
    "summarize conversation",
]


def is_memory_query(question: str) -> bool:
    q = question.lower()

    return any(keyword in q for keyword in MEMORY_KEYWORDS)
# ── State Schema ─────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    question: str              # original user question
    rewritten_question: str    # standalone query after rewriting (used for retrieval)
    is_python_related: bool
    relevant_docs: list[dict]
    answer: str
    sources: list[dict]
    grounded: bool
    error: str | None
    conversation_memory: list  # prior HumanMessage / AIMessage objects


# ── Node 1: Classify ─────────────────────────────────────────────────────────
CLASSIFY_PROMPT = CLASSIFY_PROMPT = """
You are a query classifier.

Determine if the question should be handled by the Python assistant.

Answer YES if:
- The question is about Python.
- The question is a follow-up to a previous Python discussion.
- The user refers to previous messages, answers, examples, code, or context.
- The user asks about conversation history:
  - what did I ask
  - what was my previous question
  - what did you say
  - summarize the conversation
  - what were the retrieved documents
  - show the previous example

Conversation history:
{history_block}

Question:
{question}

Respond ONLY with 'yes' or 'no'.
"""


async def classify_node(state: AgentState) -> AgentState:
    """Classify if the question is Python-related, using conversation history for context."""
    from langchain_core.messages import HumanMessage, AIMessage

    # Build a compact history block from the last few memory turns (max 6 messages = 3 pairs)
    memory = state.get("conversation_memory", [])
    history_lines = []
    for msg in memory[-6:]:
        if isinstance(msg, HumanMessage):
            history_lines.append(f"User: {msg.content[:200]}")
        elif isinstance(msg, AIMessage):
            history_lines.append(f"Assistant: {msg.content[:200]}")
    history_block = ("Conversation history:\n" + "\n".join(history_lines) + "\n\n") if history_lines else ""

    async with timer("classify_node  [LLM call]"):
        try:
            response = await llm.ainvoke(
                CLASSIFY_PROMPT.format(
                    question=state["question"],
                    history_block=history_block,
                )
            )
            is_python = response.content.strip().lower().startswith("yes")
            logger.info(f"[classify_node] result → {'PYTHON' if is_python else 'NOT PYTHON'}")
            return {**state, "is_python_related": is_python}
        except Exception as e:
            logger.error(f"[classify_node] error: {e}")
            return {**state, "is_python_related": False, "error": str(e)}


# ── Node 2: Rewrite ──────────────────────────────────────────────────────────
REWRITE_PROMPT = """You are a query rewriter for a Python programming Q&A assistant.
Your job: turn the user's latest message into a fully self-contained search query.

Rules:
- Resolve all references ("it", "that", "the above", "this approach", etc.) using the conversation history.
- If the question is already specific and self-contained, return it unchanged.
- Output ONLY the rewritten query — no explanation, no quotes, no prefix.

{history_block}Original question: {question}

Rewritten search query:"""


async def rewrite_node(state: AgentState) -> AgentState:
    """Rewrite vague / reference-heavy questions into standalone queries for better retrieval."""
    from langchain_core.messages import HumanMessage, AIMessage

    memory = state.get("conversation_memory", [])
    question = state["question"]

    # Only rewrite if there is history to reference; otherwise pass through
    if not memory:
        logger.info("[rewrite_node] no memory — keeping original question")
        return {**state, "rewritten_question": question}

    history_lines = []
    for msg in memory[-6:]:
        if isinstance(msg, HumanMessage):
            history_lines.append(f"User: {msg.content[:300]}")
        elif isinstance(msg, AIMessage):
            history_lines.append(f"Assistant: {msg.content[:300]}")
    history_block = "Conversation history:\n" + "\n".join(history_lines) + "\n\n"

    async with timer("rewrite_node   [LLM call]"):
        try:
            response = await llm.ainvoke(
                REWRITE_PROMPT.format(question=question, history_block=history_block)
            )
            rewritten = response.content.strip()
            logger.info(f"[rewrite_node] '{question}' → '{rewritten}'")
        
            return {**state, "rewritten_question": rewritten}
        except Exception as e:
            logger.warning(f"[rewrite_node] error, using original: {e}")
            return {**state, "rewritten_question": question}
async def memory_node(state: AgentState) -> AgentState:
    """
    Answer questions about conversation history without using retrieval.
    """

    memory = state.get("conversation_memory", [])

    if not memory:
        return {
            **state,
            "answer": "No conversation history found.",
            "sources": [],
            "grounded": False,
        }

    question = state["question"].lower()

    # Last user question
    if any(
        phrase in question
        for phrase in [
            "last question",
            "previous question",
            "what did i ask",
            "what was my question",
        ]
    ):
        for msg in reversed(memory):
            if msg.__class__.__name__ == "HumanMessage":
                return {
                    **state,
                    "answer": f"Your last question was:\n\n{msg.content}",
                    "sources": [],
                    "grounded": False,
                }

    # Last assistant response
    if any(
        phrase in question
        for phrase in [
            "what did you say",
            "your last answer",
            "previous answer",
        ]
    ):
        for msg in reversed(memory):
            if msg.__class__.__name__ == "AIMessage":
                return {
                    **state,
                    "answer": f"My previous response was:\n\n{msg.content}",
                    "sources": [],
                    "grounded": False,
                }

    # Generic conversation summary
    history = []

    for msg in memory[-10:]:
        role = (
            "User"
            if msg.__class__.__name__ == "HumanMessage"
            else "Assistant"
        )

        history.append(f"{role}: {msg.content}")

    return {
        **state,
        "answer": "Recent conversation:\n\n" + "\n\n".join(history),
        "sources": [],
        "grounded": False,
    }

# ── Node 3: Retrieve ─────────────────────────────────────────────────────────
async def retrieve_node(state: AgentState) -> AgentState:
    """Embed the rewritten query and retrieve similar documents from Pinecone."""
    # Use rewritten_question for retrieval so vague follow-ups resolve correctly
    query = state.get("rewritten_question") or state["question"]
    try:
        async with timer("retrieve_node  [embed_query]"):
            embedding = await embed_query(query)

        async with timer("retrieve_node  [supabase_rpc]"):
            docs = await retrieve_similar(embedding, top_k=5, match_threshold=0.3)

        logger.info(f"[retrieve_node] returned {len(docs)} docs  (query='{query[:60]}')")
        return {**state, "relevant_docs": docs}
    except Exception as e:
        logger.error(f"[retrieve_node] error: {e}")
        return {**state, "relevant_docs": [], "error": str(e)}


# ── Node 4: Grade ─────────────────────────────────────────────────────────────
GRADE_PROMPT = """You are grading whether a retrieved document is relevant to answer a Python question.

Question: {question}

Document content (excerpt):
{content}

Is this document relevant to answering the question? Respond ONLY with 'yes' or 'no'."""


async def grade_node(state: AgentState) -> AgentState:
    """Grade retrieved documents for relevance using the rewritten query."""
    docs = state.get("relevant_docs", [])
    if not docs:
        logger.info("[grade_node] no docs to grade")
        return {**state, "relevant_docs": []}

    # Grade against the rewritten (more specific) query for better precision
    grading_question = state.get("rewritten_question") or state["question"]
    graded = []
    t_node = time.perf_counter()

    for i, doc in enumerate(docs, 1):
        content_excerpt = doc.get("content", "")[:500]
        async with timer(f"grade_node     [doc {i}/{len(docs)} LLM call]"):
            try:
                response = await llm.ainvoke(
                    GRADE_PROMPT.format(
                        question=grading_question,
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


# ── Node 5: Generate ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Python programming expert helping data science learners.
Answer the question using ONLY the provided context from Stack Overflow.
Be concise, accurate, and include code examples when relevant.
If the context doesn't fully answer the question, say so honestly.
Format code blocks with proper markdown. Always mention if your answer
is grounded in retrieved sources or generated from model knowledge.
You have access to the conversation history — use it to understand follow-up
questions and references like 'it', 'that', 'the above', etc."""

GENERATE_PROMPT = """Context from Stack Overflow:
{context}

Question: {question}

Please provide a comprehensive answer using the context above."""


async def generate_node(state: AgentState) -> AgentState:
    """Generate answer grounded in retrieved documents, with conversation memory."""
    from langchain_core.messages import SystemMessage, HumanMessage

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

    # Build message list: system + prior memory + current question
    memory = state.get("conversation_memory", [])
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *memory,  # interleaved HumanMessage / AIMessage from prior turns
        HumanMessage(content=GENERATE_PROMPT.format(
            context=context,
            question=state["question"],
        )),
    ]

    async with timer("generate_node  [LLM call]"):
        try:
            response = await llm.ainvoke(messages)
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


# ── Node 6: Fallback ─────────────────────────────────────────────────────────
FALLBACK_PROMPT = """You are a Python programming expert.
No relevant Stack Overflow answers were found for the question below.
Answer using your own knowledge, but clearly state that this answer is from your general knowledge
and not from retrieved sources. Be accurate and include code examples where appropriate.
You have access to the conversation history — use it to understand follow-up questions.

Question: {question}"""


async def fallback_node(state: AgentState) -> AgentState:
    """Fallback: answer from model knowledge with disclaimer, with conversation memory."""
    from langchain_core.messages import SystemMessage, HumanMessage

    memory = state.get("conversation_memory", [])
    messages = [
        SystemMessage(content="You are a Python programming expert. Use the conversation history for context."),
        *memory,
        HumanMessage(content=FALLBACK_PROMPT.format(question=state["question"])),
    ]

    async with timer("fallback_node  [LLM call]"):
        try:
            response = await llm.ainvoke(messages)
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

    if is_memory_query(state["question"]):
        return "memory_node"

    if state.get("is_python_related"):
        return "rewrite_node"

    return "not_python_node"


def route_after_grade(state: AgentState) -> str:
    return "generate_node" if state.get("relevant_docs") else "fallback_node"


# ── Build Graph ───────────────────────────────────────────────────────────────
# Pipeline: classify → rewrite → retrieve → grade → generate | fallback
#                                                  → not_python (if off-topic)
def build_agent() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("memory_node", memory_node)
    graph.add_node("classify_node", classify_node)
    graph.add_node("rewrite_node", rewrite_node)      # NEW: query rewriting
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
        "memory_node": "memory_node",
        "rewrite_node": "rewrite_node",
        "not_python_node": "not_python_node",
    },
)
    graph.add_edge("rewrite_node", "retrieve_node")   # rewrite → retrieve
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
    graph.add_edge("memory_node", END)
    return graph.compile()


# Compiled agent (singleton)
qa_agent = build_agent()


async def run_agent(question: str, memory: list | None = None) -> AgentState:
    """
    Run the full agent pipeline and return final state.

    Args:
        question: The user's current question.
        memory:   Optional list of HumanMessage / AIMessage objects from prior
                  turns in the session, injected into generate/fallback nodes.
    """
    logger.info(
    f"memory type={type(memory)} "
    f"first={type(memory[0]).__name__ if memory else None}"
    )
    logger.info(f"{'─'*55}")
    logger.info(
        f"[run_agent] START  q={question!r:.60}  "
        f"memory_turns={len(memory) if memory else 0}"
    )

    t0 = time.perf_counter()

    initial_state: AgentState = {
        "question": question,
        "rewritten_question": question,  # default; overwritten by rewrite_node
        "is_python_related": False,
        "relevant_docs": [],
        "answer": "",
        "sources": [],
        "grounded": False,
        "error": None,
        "conversation_memory": memory or [],
    }
    result = await qa_agent.ainvoke(initial_state)

    total_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        f"[TIMER] {'TOTAL (run_agent)':<35} → {total_ms:>7.1f} ms  "
        f"grounded={result['grounded']}"
    )
    logger.info(f"{'─'*55}")

    return result
