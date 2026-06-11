# Test Results — Python Q&A Assistant

> Run after deploying with live API. Fill in actual latency and responses.
> Command: `pytest tests/ -v` for automated tests.

---

## Automated Tests (pytest)

```
tests/test_api.py::test_health_returns_200                    PASSED
tests/test_api.py::test_ask_valid_python_question             PASSED
tests/test_api.py::test_ask_with_voice_returns_audio          PASSED
tests/test_api.py::test_ask_non_python_question_graceful_refusal PASSED
tests/test_api.py::test_ask_empty_string_returns_422          PASSED
tests/test_api.py::test_ask_stream_returns_sse                PASSED
tests/test_api.py::test_get_sources_returns_ranked_docs       PASSED
tests/test_api.py::test_ask_short_question_returns_structured_response PASSED

8 passed in Xs
```

---

## Manual Test Results (Live API)

| # | Question | Latency (ms) | Grounded | Sources Found |
|---|----------|-------------|----------|---------------|
| 1 | How do I use list comprehensions in Python? | — | — | — |
| 2 | What are Python decorators and how do they work? | — | — | — |
| 3 | How to use asyncio and async/await in Python? | — | — | — |
| 4 | How do I merge two pandas DataFrames? | — | — | — |
| 5 | What is Python's GIL and how does it affect multithreading? | — | — | — |
| 6 | What is the capital of France? (non-Python) | — | ✗ | — |
| 7 | fix (ambiguous/too short) | — | — | — |
| 8 | How to read and write CSV files in Python? | — | — | — |

---

## Detailed Responses

### Test 1: List Comprehensions
**Question:** How do I use list comprehensions in Python?
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** *(Fill after live test)*

---

### Test 2: Decorators
**Question:** What are Python decorators and how do they work?
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** *(Fill after live test)*

---

### Test 3: asyncio
**Question:** How to use asyncio and async/await in Python?
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** *(Fill after live test)*

---

### Test 4: pandas merge
**Question:** How do I merge two pandas DataFrames?
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** *(Fill after live test)*

---

### Test 5: GIL
**Question:** What is Python's GIL and how does it affect multithreading?
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** *(Fill after live test)*

---

### Test 6: Non-Python (graceful refusal)
**Question:** What is the capital of France?
**Expected:** Graceful refusal mentioning Python-only scope
**Answer:** *(Fill after live test)*
**Quality:** Should refuse without hallucinating

---

### Test 7: Ambiguous/Short
**Question:** fix
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** Should return structured response even for vague input

---

### Test 8: CSV files
**Question:** How to read and write CSV files in Python?
**Answer:** *(Fill after live test)*
**Sources:** *(Fill after live test)*
**Quality:** Should include code examples with `csv` module or `pandas`
