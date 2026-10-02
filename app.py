import os
from io import BytesIO
from pathlib import Path
from mimetypes import guess_type

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from services.gemini_service import chat_reply
from services.sarvam_service import synthesize_speech, transcribe_audio

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_MB", "8")) * 1024 * 1024
MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", "25"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "24"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_BYTES + 20 * 1024 * 1024

LANGUAGES = {
    "ta-IN": {
        "name": "தமிழ்",
        "english": "Tamil",
        "route": "tamil",
        "greeting": "வணக்கம்!",
        "welcome": "நான் தயார். பேசுங்கள் அல்லது தட்டச்சு செய்யுங்கள்.",
        "placeholder": "Type in English or Tamil...",
    },
    "hi-IN": {
        "name": "हिन्दी",
        "english": "Hindi",
        "route": "hindi",
        "greeting": "नमस्ते!",
        "welcome": "मैं तैयार हूँ। बोलिए या टाइप कीजिए।",
        "placeholder": "Type in English or Hindi...",
    },
}


def validate_language(language_code: str) -> str:
    if language_code not in LANGUAGES:
        raise ValueError("Unsupported language")
    return language_code


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/chat/<language>")
def chat_page(language: str):
    code = {item["route"]: key for key, item in LANGUAGES.items()}.get(language)
    if not code:
        return render_template("404.html"), 404
    lang = LANGUAGES[code]
    return render_template(
        "chat.html",
        language_code=code,
        language_name=lang["name"],
        language_english=lang["english"],
        greeting=lang["greeting"],
        welcome=lang["welcome"],
        placeholder=lang["placeholder"],
        max_record_seconds=MAX_RECORD_SECONDS,
        max_history_messages=MAX_HISTORY_MESSAGES,
    )


@app.post("/api/chat")
def api_chat():
    try:
        language_code = validate_language(request.form.get("language_code", ""))
        message = (request.form.get("message") or "").strip()
        image = request.files.get("image")
        history_raw = request.form.get("history") or "[]"

        if not message and not (image and image.filename):
            return jsonify({"error": "Type a message, record your voice, or attach a screenshot."}), 400

        import json

        try:
            history = json.loads(history_raw)
        except json.JSONDecodeError:
            history = []
        if not isinstance(history, list):
            history = []
        history = history[-MAX_HISTORY_MESSAGES:]

        image_bytes = None
        image_mime = None
        image_name = None
        if image and image.filename:
            image_name = secure_filename(image.filename) or "screenshot"
            ext = image_name.rsplit(".", 1)[-1].lower() if "." in image_name else ""
            if ext not in ALLOWED_IMAGES:
                return jsonify({"error": "Please upload a PNG, JPG, JPEG, WEBP, or GIF image."}), 400
            image_bytes = image.read(MAX_IMAGE_BYTES + 1)
            if len(image_bytes) > MAX_IMAGE_BYTES:
                return jsonify({"error": f"Image must be smaller than {os.getenv('MAX_IMAGE_MB', '8')} MB."}), 400
            image_mime = image.mimetype or guess_type(image_name)[0] or f"image/{ext}"

        answer = chat_reply(
            language_code=language_code,
            user_text=message,
            history=history,
            image_bytes=image_bytes,
            image_mime=image_mime,
        )
        return jsonify({"answer": answer, "image_name": image_name})
    except Exception as exc:
        app.logger.exception("chat failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/stt")
def api_stt():
    try:
        language_code = validate_language(request.form.get("language_code", ""))
        audio = request.files.get("audio")
        if not audio:
            return jsonify({"error": "No recording uploaded."}), 400

        audio_bytes = audio.read(14 * 1024 * 1024 + 1)
        if not audio_bytes:
            return jsonify({"error": "The recording was empty."}), 400
        if len(audio_bytes) > 14 * 1024 * 1024:
            return jsonify({"error": "Recording is too large."}), 400

        filename = secure_filename(audio.filename or "recording.webm")
        content_type = request.form.get("audio_mime") or audio.mimetype or "audio/webm"
        transcript = transcribe_audio(audio_bytes, filename, language_code, content_type)
        return jsonify({"transcript": transcript, "language_code": language_code})
    except Exception as exc:
        app.logger.exception("stt failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/tts")
def api_tts():
    try:
        language_code = validate_language(request.form.get("language_code", ""))
        text = (request.form.get("text") or "").strip()
        if not text:
            return jsonify({"error": "No text supplied."}), 400

        audio_bytes = synthesize_speech(text, language_code)
        return send_file(BytesIO(audio_bytes), mimetype="audio/wav", download_name="narration.wav")
    except Exception as exc:
        app.logger.exception("tts failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/config")
def api_config():
    return jsonify({
        "max_record_seconds": MAX_RECORD_SECONDS,
        "max_history_messages": MAX_HISTORY_MESSAGES,
    })


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Uploaded content is too large."}), 413


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
