(() => {
  "use strict";

  const body = document.body;
  const languageCode = body.dataset.languageCode;
  const maxRecordSeconds = Number(body.dataset.maxRecordSeconds || 25);
  const maxHistoryMessages = Number(body.dataset.maxHistoryMessages || 24);
  const storageKey = `vaani-duo-chat-${languageCode}`;
  const narrateKey = "vaani-duo-narrate";

  const messagesEl = document.getElementById("messages");
  const emptyState = document.getElementById("emptyState");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const micBtn = document.getElementById("micBtn");
  const attachBtn = document.getElementById("attachBtn");
  const imageInput = document.getElementById("imageInput");
  const preview = document.getElementById("attachmentPreview");
  const narrateToggle = document.getElementById("narrateToggle");
  const statusText = document.getElementById("statusText");

  let messages = loadMessages();
  let selectedImage = null;
  let mediaRecorder = null;
  let mediaStream = null;
  let chunks = [];
  let recordingTimer = null;
  let recordingStartedAt = 0;
  let currentAudio = null;
  let pendingAutoplayText = null;
  let busy = false;

  function loadMessages() {
    try {
      const raw = JSON.parse(localStorage.getItem(storageKey) || "[]");
      return Array.isArray(raw) ? raw.slice(-30) : [];
    } catch {
      return [];
    }
  }

  function saveMessages() {
    localStorage.setItem(storageKey, JSON.stringify(messages.slice(-30)));
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value ?? "");
    return div.innerHTML.replace(/\n/g, "<br>");
  }

  function setStatus(message, isError = false) {
    statusText.textContent = message || "Voice is off";
    statusText.parentElement.classList.toggle("error", isError);
  }

  function render() {
    messagesEl.innerHTML = "";
    emptyState.classList.toggle("hidden", messages.length > 0);

    messages.forEach((message) => {
      const row = document.createElement("article");
      row.className = `message-row ${message.role}`;

      const wrap = document.createElement("div");
      wrap.className = "message-wrap";

      const bubble = document.createElement("div");
      bubble.className = "message-bubble";

      if (message.imageName) {
        const chip = document.createElement("div");
        chip.className = "image-chip";
        chip.textContent = `Screenshot · ${message.imageName}`;
        bubble.appendChild(chip);
      }

      const text = document.createElement("div");
      text.innerHTML = escapeHtml(message.content || "");
      bubble.appendChild(text);
      wrap.appendChild(bubble);

      if (message.role === "assistant") {
        const actions = document.createElement("div");
        actions.className = "message-actions";
        const repeat = document.createElement("button");
        repeat.type = "button";
        repeat.className = "repeat-btn";
        repeat.textContent = "↻ Repeat";
        repeat.addEventListener("click", () => speakText(message.content, true));
        actions.appendChild(repeat);
        wrap.appendChild(actions);
      }

      row.appendChild(wrap);
      messagesEl.appendChild(row);
    });

    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(role, content, extra = {}) {
    messages.push({ role, content, ...extra });
    messages = messages.slice(-30);
    saveMessages();
    render();
  }

  function setBusy(value) {
    busy = value;
    sendBtn.disabled = value;
    attachBtn.disabled = value;
    input.disabled = value;
    micBtn.disabled = value;
  }

  function resizeInput() {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
  }

  function showPreview(file) {
    preview.innerHTML = "";
    preview.classList.remove("hidden");
    const chip = document.createElement("span");
    chip.className = "preview-chip";
    const label = document.createElement("span");
    label.textContent = `Screenshot · ${file.name}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove screenshot");
    remove.textContent = "×";
    remove.addEventListener("click", clearImage);
    chip.append(label, remove);
    preview.appendChild(chip);
  }

  function clearImage() {
    selectedImage = null;
    imageInput.value = "";
    preview.innerHTML = "";
    preview.classList.add("hidden");
  }

  async function sendChat() {
    if (busy) return;
    const text = input.value.trim();
    if (!text && !selectedImage) return;

    const outgoingImage = selectedImage;
    const historyBeforeTurn = messages.slice(-maxHistoryMessages);

    input.value = "";
    resizeInput();
    clearImage();

    addMessage("user", text || "[Screenshot uploaded]", outgoingImage ? { imageName: outgoingImage.name } : {});
    setBusy(true);
    setStatus("Thinking…");

    const formData = new FormData();
    formData.append("language_code", languageCode);
    formData.append("message", text);
    formData.append("history", JSON.stringify(historyBeforeTurn));
    if (outgoingImage) formData.append("image", outgoingImage, outgoingImage.name);

    try {
      const response = await fetch("/api/chat", { method: "POST", body: formData });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Chat request failed");

      const answer = (data.answer || "").trim();
      if (!answer) throw new Error("Gemini returned an empty response.");

      addMessage("assistant", answer);
      setStatus(narrateToggle.checked ? "Speaking…" : "Voice is off");

      if (narrateToggle.checked) {
        await speakText(answer, true);
      }
    } catch (error) {
      console.error(error);
      addMessage("assistant", `Sorry — ${error.message}`);
      setStatus("Something went wrong", true);
    } finally {
      setBusy(false);
    }
  }

  async function speakText(text, userInitiated) {
    const cleanText = String(text || "").trim();
    if (!cleanText) return;

    if (currentAudio) {
      currentAudio.pause();
      currentAudio.src = "";
      currentAudio = null;
    }

    const formData = new FormData();
    formData.append("language_code", languageCode);
    formData.append("text", cleanText);

    try {
      const response = await fetch("/api/tts", { method: "POST", body: formData });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Narration failed");
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.preload = "auto";
      currentAudio = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        if (currentAudio === audio) currentAudio = null;
        if (narrateToggle.checked) setStatus("");
      };

      try {
        await audio.play();
        pendingAutoplayText = null;
        setStatus("");
      } catch (playError) {
        pendingAutoplayText = cleanText;
        setStatus("Tap once to enable voice playback.");
        if (userInitiated) console.warn("Browser blocked playback", playError);
      }
    } catch (error) {
      console.error(error);
      setStatus(`Narration error: ${error.message}`, true);
    }
  }

  function recorderMime() {
    const candidates = [
      ["audio/webm;codecs=opus", "webm"],
      ["audio/webm", "webm"],
      ["audio/ogg;codecs=opus", "ogg"],
      ["audio/ogg", "ogg"],
    ];
    for (const [mime, ext] of candidates) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(mime)) return { mime, ext };
    }
    return { mime: "", ext: "webm" };
  }

  async function startRecording() {
    if (busy || mediaRecorder) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setStatus("Microphone recording is not supported here.", true);
      return;
    }

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const selected = recorderMime();
      mediaRecorder = selected.mime
        ? new MediaRecorder(mediaStream, { mimeType: selected.mime })
        : new MediaRecorder(mediaStream);
      chunks = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        clearTimeout(recordingTimer);
        recordingTimer = null;
        micBtn.classList.remove("recording");
        setStatus("Transcribing…");

        const recorder = mediaRecorder;
        const actualMime = recorder?.mimeType || selected.mime || "audio/webm";
        const extension = actualMime.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunks, { type: actualMime });
        const duration = (Date.now() - recordingStartedAt) / 1000;

        mediaRecorder = null;
        chunks = [];
        mediaStream?.getTracks().forEach((track) => track.stop());
        mediaStream = null;

        if (!blob.size || duration < 0.25) {
          setStatus("Recording was too short.");
          return;
        }

        try {
          const formData = new FormData();
          formData.append("language_code", languageCode);
          formData.append("audio", blob, `recording.${extension}`);
          // Send the bare container MIME. Chrome commonly reports
          // `audio/webm;codecs=opus`, while Sarvam expects `audio/webm`.
          const sarvamMime = extension === "ogg" ? "audio/ogg" : "audio/webm";
          formData.append("audio_mime", sarvamMime);

          const response = await fetch("/api/stt", { method: "POST", body: formData });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || "Speech recognition failed");

          const transcript = (result.transcript || "").trim();
          if (!transcript) throw new Error("No speech was detected.");

          input.value = transcript;
          resizeInput();
          setStatus("Voice transcript ready");
          input.focus();
        } catch (error) {
          console.error(error);
          setStatus(`Voice-to-text error: ${error.message}`, true);
        } finally {
          void recorder;
        }
      };

      mediaRecorder.start();
      recordingStartedAt = Date.now();
      micBtn.classList.add("recording");
      setStatus(`Listening… ${maxRecordSeconds}s max`);

      recordingTimer = window.setTimeout(() => {
        if (mediaRecorder?.state === "recording") stopRecording();
      }, maxRecordSeconds * 1000);
    } catch (error) {
      console.error(error);
      mediaStream?.getTracks().forEach((track) => track.stop());
      mediaStream = null;
      setStatus("Allow microphone access and try again.", true);
    }
  }

  function stopRecording() {
    clearTimeout(recordingTimer);
    recordingTimer = null;
    if (mediaRecorder?.state === "recording") mediaRecorder.stop();
  }

  // Keep a gesture listener alive so autoplay can be retried even when the
  // first click happened before the TTS request finished.
  document.addEventListener("click", async () => {
    if (!pendingAutoplayText || !narrateToggle.checked) return;
    const text = pendingAutoplayText;
    pendingAutoplayText = null;
    await speakText(text, true);
  });

  micBtn.addEventListener("click", () => {
    if (mediaRecorder) stopRecording();
    else startRecording();
  });

  attachBtn.addEventListener("click", () => imageInput.click());
  imageInput.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      clearImage();
      setStatus("Please choose an image file.", true);
      return;
    }
    selectedImage = file;
    showPreview(file);
    setStatus("Screenshot attached");
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void sendChat();
  });

  input.addEventListener("input", resizeInput);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendChat();
    }
  });

  narrateToggle.checked = localStorage.getItem(narrateKey) === "true";
  narrateToggle.addEventListener("change", () => {
    localStorage.setItem(narrateKey, narrateToggle.checked ? "true" : "false");
    if (!narrateToggle.checked) {
      pendingAutoplayText = null;
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.src = "";
        currentAudio = null;
      }
      setStatus("Voice is off");
    }
  });

  // Load browser-only history. No database is used.
  render();
  resizeInput();

  // Requested behavior: narrate the newest assistant answer on every chat load.
  if (narrateToggle.checked && messages.length) {
    const latestAssistant = [...messages].reverse().find((item) => item.role === "assistant");
    if (latestAssistant) {
      pendingAutoplayText = latestAssistant.content;
      void speakText(latestAssistant.content, false);
    }
  }
})();
