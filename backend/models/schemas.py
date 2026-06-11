from pydantic import BaseModel, Field
from typing import Optional


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The Python programming question")
    voice: bool = Field(False, description="If true, return TTS audio as base64")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "How do I use list comprehensions in Python?",
                "voice": False
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
    audio_base64: Optional[str] = None


class StreamRequest(BaseModel):
    question: str = Field(..., min_length=1)


class HealthResponse(BaseModel):
    status: str
    version: str
    model: str
    embedding_model: str
