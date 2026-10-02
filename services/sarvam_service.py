import base64
import os
from pathlib import Path

import requests

SARVAM_BASE_URL = "https://api.sarvam.ai"


def _api_key() -> str:
    key = os.getenv("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY is missing from the environment")
    return key


def _audio_content_type(filename: str, supplied: str | None) -> str:
    # Sarvam accepts audio/webm, but some browsers report the recorder MIME
    # as `audio/webm;codecs=opus`. Normalize MIME parameters before sending
    # the multipart part so Sarvam receives the bare supported type.
    candidate = (supplied or "").split(";", 1)[0].strip().lower()
    if candidate.startswith("audio/"):
        allowed = {
            "audio/mpeg", "audio/mp3", "audio/mpeg3",
            "audio/x-mpeg-3", "audio/x-mp3", "audio/wav",
            "audio/x-wav", "audio/wave", "audio/pcm_s16le",
            "audio/l16", "audio/raw", "audio/aac", "audio/x-aac",
            "audio/aiff", "audio/x-aiff", "audio/ogg", "audio/opus",
            "audio/flac", "audio/x-flac", "audio/mp4", "audio/x-m4a",
            "audio/amr", "audio/x-ms-wma", "audio/webm",
        }
        if candidate in allowed:
            return candidate

    suffix = Path(filename).suffix.lower()
    return {
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".mp4": "audio/mp4",
        ".m4a": "audio/x-m4a",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".aiff": "audio/aiff",
        ".amr": "audio/amr",
    }.get(suffix, "audio/webm")


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    language_code: str,
    content_type: str | None = None,
) -> str:
    mime = _audio_content_type(filename, content_type)
    response = requests.post(
        f"{SARVAM_BASE_URL}/speech-to-text",
        headers={"api-subscription-key": _api_key()},
        files={
            "file": (
                filename or "recording.webm",
                audio_bytes,
                mime,
            )
        },
        data={
            "model": os.getenv("SARVAM_STT_MODEL", "saaras:v4"),
            "mode": os.getenv("SARVAM_STT_MODE", "codemix"),
        },
        timeout=45,
    )
    if not response.ok:
        raise RuntimeError(f"Sarvam STT error ({response.status_code}): {response.text[:1000]}")

    data = response.json()
    transcript = (data.get("transcript") or "").strip()
    if not transcript:
        raise RuntimeError("Sarvam returned an empty transcript")
    return transcript


def synthesize_speech(text: str, language_code: str) -> bytes:
    text = text.strip()
    if not text:
        raise ValueError("Empty text")

    # REST Bulbul v3 limit is 2500 characters; prefer a clean boundary when possible.
    if len(text) > 2500:
        text = text[:2497].rsplit(" ", 1)[0] + "..."

    response = requests.post(
        f"{SARVAM_BASE_URL}/text-to-speech",
        headers={
            "api-subscription-key": _api_key(),
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "language_code": language_code,
            "model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
            "speaker": os.getenv("SARVAM_TTS_SPEAKER", "shubh"),
            "output_audio_codec": "wav",
            "speech_sample_rate": 24000,
        },
        timeout=45,
    )
    if not response.ok:
        raise RuntimeError(f"Sarvam TTS error ({response.status_code}): {response.text[:1000]}")

    data = response.json()
    audio_chunks = data.get("audios") or []
    if not audio_chunks:
        raise RuntimeError("Sarvam returned no audio")
    return base64.b64decode("".join(audio_chunks))
