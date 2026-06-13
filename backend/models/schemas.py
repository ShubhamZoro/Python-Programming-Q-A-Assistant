from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Existing models ────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=1,
        description="The Python programming question"
    )
    session_id: Optional[str] = Field(
        None,
        description="Chat session ID to persist messages"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "How do I use list comprehensions in Python?",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }


class SourceDoc(BaseModel):
    content: str
    score: float
    row_number: Optional[int] = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceDoc]
    grounded: bool
    session_id: Optional[str] = None


class StreamRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None)


class HealthResponse(BaseModel):
    status: str
    version: str
    model: str
    embedding_model: str


# ── Chat session models ────────────────────────────────────────────────────────

class ChatSession(BaseModel):
    id: str
    title: str
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    id: str
    session_id: str
    role: str          # 'user' | 'assistant'
    content: str
    sources: Optional[List[dict]] = []
    grounded: bool = False
    created_at: datetime


class CreateSessionRequest(BaseModel):
    title: str = Field("New Chat", description="Optional initial session title")


class CreateSessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: datetime


class SummarizeResponse(BaseModel):
    session_id: str
    summary: str


# ── Auth models ───────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="Password (min 6 characters)")

    class Config:
        json_schema_extra = {
            "example": {"email": "user@example.com", "password": "securepassword"}
        }


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    class Config:
        json_schema_extra = {
            "example": {"email": "user@example.com", "password": "securepassword"}
        }


class UserInfo(BaseModel):
    id: str
    email: str
    created_at: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    user: UserInfo
    message: str = "Success"
