# generate_test_report.py

import asyncio
from httpx import AsyncClient

QUESTIONS = [
    "How do I use list comprehensions in Python?",
    "What are lambda functions in Python?",
    "What is a Python decorator?",
    "How do I read a file in Python?",
    "What are Python generators?",
    "Explain dictionary comprehensions.",
    "Difference between append() and extend()?",
    "What is the capital of France?"
]

async def main():
    async with AsyncClient(base_url="http://localhost:8000") as client:
        for i, q in enumerate(QUESTIONS, 1):
            response = await client.post(
                "/ask",
                json={"question": q},
                headers={"Authorization": "eyJhbGciOiJFUzI1NiIsImtpZCI6IjZkMmUxNDdkLTExNjUtNDUyYS05MzAyLTk3MjI4ODNiNGMwYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JjdXlxd3hmdWVyb2hnZHdqdXprLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiIzNGNjOTk5Zi03MzVhLTQ0OTItODc5YS1iZWNlYjgzNTdkZGEiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzgxMzM0NjI0LCJpYXQiOjE3ODEzMzEwMjQsImVtYWlsIjoic2h1YmhhbS4yMGdjZWJjczA5MUBnYWxnb3RpYWNvbGxlZ2UuZWR1IiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbCI6InNodWJoYW0uMjBnY2ViY3MwOTFAZ2FsZ290aWFjb2xsZWdlLmVkdSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJwaG9uZV92ZXJpZmllZCI6ZmFsc2UsInN1YiI6IjM0Y2M5OTlmLTczNWEtNDQ5Mi04NzlhLWJlY2ViODM1N2RkYSJ9LCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImFhbCI6ImFhbDEiLCJhbXIiOlt7Im1ldGhvZCI6InBhc3N3b3JkIiwidGltZXN0YW1wIjoxNzgxMzMxMDI0fV0sInNlc3Npb25faWQiOiJhNWI4OTgzNS1jMGQ3LTQyNDMtOTQ3ZS1hOWEyOGU5NDRlZDciLCJpc19hbm9ueW1vdXMiOmZhbHNlfQ.QgDwE79D5VCUGfePuW3KmM6vjdcWK0a3kM81yx5O1IqryX_IJQN5aCHpGY8jSazienIvulYq3pH3fw-8CV_yVQ"}
            )

            data = response.json()

            print("\n" + "=" * 80)
            print(f"TEST {i}")
            print("QUESTION:", q)
            print("ANSWER:", data.get("answer"))
            print("GROUNDED:", data.get("grounded"))
            print("=" * 80)

asyncio.run(main())