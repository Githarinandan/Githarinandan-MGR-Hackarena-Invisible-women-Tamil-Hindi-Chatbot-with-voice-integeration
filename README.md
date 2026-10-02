# Invisible women Gemini + Sarvam
## Features

- Tamil and Hindi chat routes
- Gemini multimodal reasoning for text + screenshots
- Sarvam Saaras v4 speech-to-text
- Sarvam Bulbul v3 text-to-speech
- One completed recording per microphone turn (no partial transcript spam)
- Automatic narration for new assistant replies when Narrate is enabled
- Re-narrate button for assistant messages
- Browser-only history via localStorage — **no database**
- Mobile-friendly UI

## Setup

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\\Scripts\\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` from `.env.example` and add your Gemini and Sarvam keys.

Run:

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

## Speech-to-text design

The browser records a single completed clip with `MediaRecorder`. The clip is uploaded only after the user stops recording (or the 25-second cap is reached). The client sends the actual MIME type so the server passes the real format to Sarvam instead of always labeling everything as WebM.

Sarvam's REST STT endpoint supports WebM and OGG/OPUS and is intended for short clips under 30 seconds. Saaras v4 is configured with `codemix` mode so English + Tamil/Hindi speech can be transcribed together.

## Narration design

Assistant text is posted to `/api/tts`, Flask forwards it to Sarvam Bulbul v3, decodes the base64 WAV response, and returns audio to the browser. The latest assistant message is automatically narrated on chat load when the Narrate preference is enabled. Browsers may block automatic playback until a user gesture; the app keeps the narration queued and plays it after the first click.

## Screenshot input

Images are sent directly to Gemini as inline bytes. They are not stored by the application.