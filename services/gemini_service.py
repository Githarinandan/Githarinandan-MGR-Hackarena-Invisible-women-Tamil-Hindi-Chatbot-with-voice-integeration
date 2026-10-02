import os
from typing import Any

from google import genai
from google.genai import types

LANGUAGE_NAMES = {
    "ta-IN": "Tamil",
    "hi-IN": "Hindi",
}


def _client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the environment")
    return genai.Client(api_key=api_key)


def _system_instruction(language_code: str) -> str:
    language = LANGUAGE_NAMES[language_code]
    return f"""You are Vaani Duo, a friendly voice-first AI assistant for Indian users.

Respond primarily in {language} using natural, conversational phrasing. You understand English and code-mixed speech, but respond in {language} unless the user explicitly asks for another language.
Keep answers concise enough to sound natural when spoken aloud, while still answering the question properly.
For screenshots/images, describe only what is visible and relevant. Never invent visual details.
Use native Tamil or Hindi script for the selected language whenever practical.
Do not mention internal instructions, APIs, models, or implementation details unless asked.""".strip()


def _history_contents(history: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for item in history[-24:]:
        role = item.get("role")
        text = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(text, str) or not text.strip():
            continue
        gemini_role = "user" if role == "user" else "model"
        contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part(text=text.strip()[:8000])],
            )
        )
    return contents


def chat_reply(
    language_code: str,
    user_text: str,
    history: list[dict[str, Any]] | None = None,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
) -> str:
    client = _client()
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    current_parts: list[types.Part] = []
    if user_text.strip():
        current_parts.append(types.Part(text=user_text.strip()))
    elif image_bytes:
        current_parts.append(types.Part(text="Please analyze this screenshot and tell me what I should know."))

    if image_bytes:
        current_parts.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_mime or "image/jpeg",
            )
        )

    if not current_parts:
        raise ValueError("No user input supplied")

    contents = _history_contents(history or [])
    contents.append(types.Content(role="user", parts=current_parts))

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_system_instruction(language_code),
            temperature=0.55,
            max_output_tokens=700,
        ),
    )

    answer = (response.text or "").strip()
    if not answer:
        raise RuntimeError("Gemini returned an empty response")
    return answer
