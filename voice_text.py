"""
voice_text.py
=============
Speech-to-text for commands, with a LOCAL fallback.

  * Primary:  Groq Whisper (cloud, very accurate/fast) — used when reachable.
  * Backup:   a local faster-whisper model (default "small.en") — used
              automatically if Groq fails (no network, no key, error, timeout).

Set JARVIS_STT_BACKEND=local in .env to run fully offline (skip Groq entirely).
The local model loads lazily (only when first needed) and is then cached.

Entry points:
  * transcribe_array(audio_int16, sample_rate) — used by the always-on listener
  * listen_and_transcribe() — record from the mic until you stop talking, then
    transcribe. RMS is float (int16**2 overflows) and the end-of-speech timer
    only starts AFTER you actually begin speaking, so it won't clip you.
"""

import os
import time

import numpy as np
import scipy.io.wavfile as wavfile
import sounddevice as sd
from dotenv import load_dotenv

load_dotenv()

SAMPLE_RATE = 16000
SILENCE_THRESHOLD = int(os.getenv("JARVIS_MIC_THRESHOLD", "350"))
END_SILENCE = float(os.getenv("JARVIS_END_SILENCE", "2.5"))
MAX_DURATION = 15.0

GROQ_KEY = os.environ.get("GROQ_API_KEY")
STT_BACKEND = os.getenv("JARVIS_STT_BACKEND", "groq").lower()        # "groq" | "local"
LOCAL_STT_MODEL = os.getenv("JARVIS_LOCAL_STT_MODEL", "small.en")    # tiny.en/base.en/small.en/medium.en

_client = None       # Groq client (lazy)
_local = None        # faster-whisper model (lazy)


# ── Groq (primary) ───────────────────────────────────────────────────────
def _groq():
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=GROQ_KEY)
    return _client


def _transcribe_groq(audio_int16: np.ndarray, sample_rate: int) -> str:
    tmp = "temp_recording.wav"
    try:
        wavfile.write(tmp, sample_rate, audio_int16)
        with open(tmp, "rb") as f:
            tr = _groq().audio.transcriptions.create(
                file=("recording.wav", f.read()),
                model="whisper-large-v3",
                response_format="text",
            )
        return (tr or "").strip()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ── Local faster-whisper (backup / offline) ──────────────────────────────
def transcribe_local(audio_int16: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    global _local
    if _local is None:
        from faster_whisper import WhisperModel
        print(f"[stt] loading local model '{LOCAL_STT_MODEL}' (one-time)...")
        _local = WhisperModel(LOCAL_STT_MODEL, device="auto", compute_type="int8")
    samples = audio_int16.astype(np.float32) / 32768.0
    segments, _ = _local.transcribe(
        samples, beam_size=1, language="en", vad_filter=True,   # drop silence/noise -> fewer hallucinations
        condition_on_previous_text=False, without_timestamps=True)
    return " ".join(s.text for s in segments).strip()


# ── Unified entry point: Groq first, local fallback ──────────────────────
def transcribe_array(audio_int16: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    if audio_int16 is None or len(audio_int16) < sample_rate * 0.3:
        return ""
    if STT_BACKEND != "local" and GROQ_KEY:
        try:
            return _transcribe_groq(audio_int16, sample_rate)
        except Exception as exc:  # noqa: BLE001 — network/api/timeout -> fall back local
            print(f"[stt] Groq unavailable ({str(exc).splitlines()[0]}); using local model.")
    return transcribe_local(audio_int16, sample_rate)


# ── Standalone recorder ──────────────────────────────────────────────────
def listen_and_transcribe() -> str:
    chunk = 0.1
    chunk_samples = int(SAMPLE_RATE * chunk)
    max_silent = max(1, int(END_SILENCE / chunk))

    data: list[np.ndarray] = []
    started = False        # only count trailing silence once speech has begun
    silent = 0
    recording = True

    def cb(indata, frames, time_info, status):
        nonlocal started, silent, recording
        if not recording:
            return
        data.append(indata.copy())
        rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))  # float -> no overflow
        if rms >= SILENCE_THRESHOLD:
            started = True
            silent = 0
        elif started:
            silent += 1
            if silent >= max_silent:
                recording = False
                raise sd.CallbackStop()

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=chunk_samples, callback=cb):
            t0 = time.time()
            while recording and time.time() - t0 < MAX_DURATION:
                time.sleep(0.05)
    except sd.CallbackStop:
        pass
    except Exception:
        return ""

    if not data:
        return ""
    audio = np.concatenate(data, axis=0).flatten()
    return transcribe_array(audio, SAMPLE_RATE)


if __name__ == "__main__":
    text = listen_and_transcribe()
    if text:
        print(text)
