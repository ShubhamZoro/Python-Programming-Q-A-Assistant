"""
OpenAI TTS wrapper.
Model: tts-1 (fast, low latency)
Voice: alloy
Format: mp3 → base64 string
Caps synthesis at 500 characters to keep latency low.
"""

from __future__ import annotations

import base64
import logging
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MAX_TTS_CHARS = 500


async def synthesize(text: str) -> str | None:
    """
    Convert text to speech using OpenAI TTS API.
    Returns base64-encoded mp3 string, or None on failure.
    """
    try:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Cap to 500 chars
        if len(text) > MAX_TTS_CHARS:
            # Truncate at last sentence boundary within limit
            truncated = text[:MAX_TTS_CHARS]
            last_period = max(
                truncated.rfind("."),
                truncated.rfind("!"),
                truncated.rfind("?"),
            )
            if last_period > MAX_TTS_CHARS // 2:
                truncated = truncated[: last_period + 1]
            text = truncated

        response = await client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text,
            response_format="mp3",
        )

        audio_bytes = response.content
        return base64.b64encode(audio_bytes).decode("utf-8")

    except Exception as e:
        logger.warning(f"TTS synthesis failed (non-fatal): {e}")
        return None
