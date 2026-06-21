"""Voice orchestrator — JARVIS-style always-on listening adapted for MAYA.

Flow:
    1. Always-on mic via speech_recognition.listen()
    2. Fast transcribe (base.en) → check for wake word "Maya"
    3. If no wake word → ignore, keep listening
    4. If wake word found → accurate transcribe (small.en)
    5. Strip wake word from command
    6. If bare wake word (no command) → greet + listen once for follow-up
    7. Speak filler (async) → process command with Brain (mic blocked — TTS is blocking)
    8. Speak final response (blocking — mic stays off until done)
    9. Back to step 1

3-min conversation window: after the first wake word, subsequent commands
don't need the wake word. After 3 min of no commands → require wake word again.

Usage:
    from voice.voice_orchestrator import VoiceOrchestrator
    orch = VoiceOrchestrator()
    orch.run()
"""

from __future__ import annotations

import difflib
import os
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from voice.config import CONVERSATION_TIMEOUT, VOICE_MODE_ENABLED
from voice.voice_logger import log_voice

# ── Configuration ─────────────────────────────────────────────────────────
END_SILENCE = float(os.getenv("JARVIS_END_SILENCE", "2.0"))
WAKE_MODEL_NAME = os.getenv("JARVIS_WAKE_MODEL", "base.en")
CMD_MODEL_NAME = os.getenv("JARVIS_LOCAL_STT_MODEL", "small.en")

NAME = "maya"
NAME_CAP = "Maya"
WAKE_WORDS = [
    "maya", "maia", "mya", "maya.", "my a",
    "mayer", "maya!", "maia!", "maya,", "mya,",
    "maia.", "mayah", "maiya", "maya's",
]

GREETINGS = [
    "Yes?", "I'm listening.", "Go ahead.", "How can I help?",
    "What do you need?", "Yes, what is it?",
]

QUICK_FILLERS = [
    "One moment.", "Sure, one second.", "Let me think.", "Let me see.",
    "Give me a second.", "Right away.", "Of course.", "Let me think on that.",
]

SLOW_FILLERS = [
    "Working on it, this will just take a moment.",
    "Let me get that for you.", "On it, one moment.",
    "Just a moment, gathering that now.", "Let me sort that out.",
    "Give me just a second.", "Let me put that together.",
]

PROGRESS_FILLERS = [
    "Still working on it.", "Almost there.", "Just a moment more.",
    "Hang tight, nearly done.", "Nearly finished now.",
    "Won't be much longer.",
]

CONTEXT_FILLERS = {
    "weather": ["Let me check the weather for you.", "Checking the skies now.",
                "One moment, pulling up the forecast."],
    "news": ["Let me pull up the latest headlines.", "Fetching the news now.",
             "Getting the headlines for you."],
    "youtube": ["Finding that for you now.", "Searching for that video now.",
                "Let me get that playing."],
    "email": ["Checking your inbox now.", "Let me look through your emails.",
              "Going through your mail now."],
    "todo": ["Updating your to-dos.", "Noting that down.",
             "Let me jot that down for you."],
    "file": ["Reading through that now.", "Let me look through those files.",
             "Going through the contents now."],
    "memory": ["Checking my memory.", "Let me recall that.",
               "Searching through memories."],
}

DOMAIN_KEYWORDS = [
    (("weather", "forecast", "umbrella", "temperature", "rain", "humid", "sunny"), "weather"),
    (("news", "headline", "happening"), "news"),
    (("play", "song", "music", "video", "youtube", "watch"), "youtube"),
    (("email", "gmail", "inbox", "mail"), "email"),
    (("remind", "reminder", "todo", "to-do", "task", "my list"), "todo"),
    (("folder", "file", "read the", "open the"), "file"),
    (("remember", "forget", "note that"), "memory"),
]

STOP_WORDS = {"stop", "cancel", "quiet", "enough"}
SLEEP_PHRASES = ("go to sleep", "good night", "goodbye", "that's all",
                 "stop listening", "sleep now")

# Whisper hallucinations on silence
_NOISE_PHRASES = {"thank you", "thanks", "thanks for watching", "thank you for watching",
                  "you", "okay", "ok", "bye", "bye bye", "yeah", "uh", "um", "hmm",
                  "so", "right", "mm", "mhm", "please subscribe", "subscribe"}

_WAKE_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in WAKE_WORDS) + r")\b", re.I)
_LEAD_FILLER = re.compile(
    r"^\s*(?:(?:hey|hi|hello|ok|okay|yeah|yep|yo|so|well|um|uh|please|and|but|just|"
    r"alright|right)\b[,\s]+)+", re.I)

# ── Lazy globals ──────────────────────────────────────────────────────────
_sr = None
_recog = None
_wake_model = None


def _ensure_loaded():
    global _sr, _recog, _wake_model
    if _wake_model is not None:
        return
    import speech_recognition as sr
    from faster_whisper import WhisperModel
    _sr = sr
    _recog = sr.Recognizer()
    _recog.dynamic_energy_threshold = True
    _recog.pause_threshold = END_SILENCE
    manual = os.getenv("JARVIS_MIC_THRESHOLD")
    if manual:
        _recog.energy_threshold = float(manual)
    print(f"[maya] loading wake model ({WAKE_MODEL_NAME})...")
    _wake_model = WhisperModel(WAKE_MODEL_NAME, device="auto", compute_type="int8")


def _to_numpy(audio) -> np.ndarray:
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    return np.frombuffer(raw, dtype=np.int16)


def _transcribe_fast(audio) -> str:
    """Fast wake-word check with base.en model."""
    samples = _to_numpy(audio).astype(np.float32) / 32768.0
    segments, _ = _wake_model.transcribe(
        samples, beam_size=1, language="en", vad_filter=True,
        condition_on_previous_text=False, without_timestamps=True)
    return " ".join(s.text for s in segments).strip().lower()


def _transcribe_accurate(audio) -> str:
    """Accurate command transcription with small.en model."""
    import voice_text
    return voice_text.transcribe_local(_to_numpy(audio), 16000)


def _is_wakeish(token: str) -> bool:
    t = re.sub(r"[^a-z]", "", token.lower())
    if len(t) < 3:
        return False
    if any(t == w or (len(w) >= 4 and (t in w or w in t)) for w in WAKE_WORDS):
        return True
    return any(difflib.SequenceMatcher(None, t, w).ratio() >= 0.76 for w in WAKE_WORDS)


def has_wake(text: str) -> bool:
    low = text.lower()
    if any(w in low for w in WAKE_WORDS):
        return True
    name = NAME.lower()
    return any(len(re.sub(r"[^a-z]", "", tok)) >= 3
               and difflib.SequenceMatcher(None, re.sub(r"[^a-z]", "", tok), name).ratio() >= 0.8
               for tok in low.split())


def strip_wake(text: str) -> str:
    t = re.sub(r"\s+", " ", _WAKE_RE.sub(" ", text)).strip(" ,.!?-")
    t = _LEAD_FILLER.sub("", t)
    parts = t.split(" ", 1)
    if parts and _is_wakeish(parts[0]):
        t = parts[1] if len(parts) > 1 else ""
    t = _LEAD_FILLER.sub("", t)
    return t.strip(" ,.!?-")


def _is_real_command(text: str) -> bool:
    low = re.sub(r"[^a-z0-9' ]", " ", (text or "").lower()).strip()
    low = re.sub(r"\s+", " ", low)
    if len(low) < 4 or len(low.split()) < 2:
        return False
    return low not in _NOISE_PHRASES


def pick_filler(text: str) -> str:
    low = text.lower()
    for keywords, domain in DOMAIN_KEYWORDS:
        if any(k in low for k in keywords):
            return random.choice(CONTEXT_FILLERS[domain])
    return random.choice(SLOW_FILLERS)


# ── The orchestrator ──────────────────────────────────────────────────────
class VoiceOrchestrator:
    def __init__(self) -> None:
        self._brain: Any = None
        self._running = False
        self._bg_thread: Optional[threading.Thread] = None
        self._greet_i = 0
        self._conversation_active = False
        self._last_activity: float = 0.0

    def _get_brain(self):
        if self._brain is None:
            from brain.brain import Brain
            self._brain = Brain(enable_memory=True)
            log_voice("brain_initialized")
        return self._brain

    # ── TTS helpers (use maya_tts) ────────────────────────────────────────

    @staticmethod
    def say(text: str) -> None:
        import maya_tts
        maya_tts.speak(text)

    @staticmethod
    def say_async(text: str):
        import maya_tts
        return maya_tts.speak_async(text)

    def greet(self) -> None:
        self.say(GREETINGS[self._greet_i % len(GREETINGS)])
        self._greet_i += 1

    # ── Conversation window ───────────────────────────────────────────────

    def _start_conversation(self) -> None:
        self._conversation_active = True
        self._last_activity = time.monotonic()

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    def _conversation_timed_out(self) -> bool:
        if not self._conversation_active:
            return False
        return (time.monotonic() - self._last_activity) > CONVERSATION_TIMEOUT

    def _end_conversation(self) -> None:
        self._conversation_active = False
        log_voice("conversation_ended")

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self) -> None:
        if not VOICE_MODE_ENABLED:
            print("[maya] VOICE_MODE_ENABLED=false, exiting.")
            return

        self._running = True
        _ensure_loaded()

        # Pre-warm TTS + STT in background
        import maya_tts
        import voice_text
        threading.Thread(target=maya_tts.warm, daemon=True).start()
        threading.Thread(
            target=lambda: voice_text.transcribe_local(np.zeros(1600, dtype=np.int16), 16000),
            daemon=True).start()

        with _sr.Microphone(sample_rate=16000) as src:
            print("[maya] adjusting for ambient noise (~1s)...")
            _recog.adjust_for_ambient_noise(src, duration=1.0)
            _recog.energy_threshold = max(_recog.energy_threshold, 200)
            print(f"[maya] energy threshold = {_recog.energy_threshold:.0f}")

            self.say(f"{NAME_CAP} is online. Say my name to activate.")
            print(f"[maya] listening — say '{NAME}' to activate.\n")

            while self._running:
                try:
                    self._listen(src)
                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    log_voice("listen_error", error=str(exc))
                    print(f"[error] {exc}")
                    time.sleep(0.5)

        self._shutdown()

    def run_in_background(self) -> None:
        if self._bg_thread and self._bg_thread.is_alive():
            return
        self._bg_thread = threading.Thread(target=self.run, daemon=True)
        self._bg_thread.start()

    def stop(self) -> None:
        self._running = False
        import maya_tts
        maya_tts.request_stop()

    # ── Single listen cycle ───────────────────────────────────────────────

    def _listen(self, src) -> None:
        # Check conversation timeout
        if self._conversation_active and self._conversation_timed_out():
            print("\n😴 No activity for 3 minutes — going to sleep.")
            self.say("Going to sleep. Say Maya to wake me up.")
            self._end_conversation()
            return

        # Capture audio
        try:
            audio = _recog.listen(src, timeout=10 if self._conversation_active else None,
                                 phrase_time_limit=15)
        except Exception:
            if self._conversation_active and self._conversation_timed_out():
                print("\n😴 No activity for 3 minutes — going to sleep.")
                self.say("Going to sleep. Say Maya to wake me up.")
                self._end_conversation()
            return

        # Fast transcription (base.en) — check for wake word
        gist = _transcribe_fast(audio)
        if not gist:
            return

        # In conversation mode: accept commands without wake word
        if self._conversation_active:
            # Check for sleep commands
            low = gist.lower()
            if any(p in low for p in SLEEP_PHRASES):
                self.say("Going to sleep. Goodbye.")
                self._end_conversation()
                return

            # Check for stop words
            words = low.split()
            if len(words) <= 3 and any(w in STOP_WORDS for w in words):
                self.say("Okay.")
                self._end_conversation()
                return

            # In conversation mode — process without requiring wake word
            if has_wake(gist):
                accurate = _transcribe_accurate(audio) or gist
                command = strip_wake(accurate)
            else:
                # No wake word but conversation active — treat entire utterance as command
                accurate = _transcribe_accurate(audio) or gist
                command = accurate.strip()

            if not _is_real_command(command):
                return

            print(f"[heard] {accurate}")
            self._touch()
            self._process(command)
            return

        # Not in conversation — require wake word
        if not has_wake(gist):
            print(f"\r[idle] {gist[:60]:<60}", end="", flush=True)
            return

        # Wake word detected!
        print(f"\n🟢 Activated!")
        log_voice("wake_word_detected")
        self._start_conversation()

        # Accurate transcription
        accurate = _transcribe_accurate(audio) or gist
        command = strip_wake(accurate)
        print(f"[heard] {accurate}")

        if not command:
            # Bare wake word — greet and listen once for follow-up
            self.greet()
            try:
                follow = _recog.listen(src, timeout=8, phrase_time_limit=15)
                command = (_transcribe_accurate(follow) or "").strip()
            except Exception:
                command = ""
            if command:
                print(f"[heard] {command}")
            if not _is_real_command(command):
                print("✅ Ready — listening for command...")
                return

        self._touch()
        self._process(command)

    # ── Process a command (mic is blocked — TTS is synchronous) ───────────

    def _process(self, command: str) -> None:
        log_voice("command_received", command=command)

        # Speak context-aware filler async while brain processes
        filler = pick_filler(command)
        self.say_async(filler)

        try:
            brain = self._get_brain()
            start = time.perf_counter()
            response = brain.process(command)
            duration_ms = (time.perf_counter() - start) * 1000
            log_voice("brain_response", command=command[:100],
                      response=(response or "")[:200], duration_ms=round(duration_ms, 2))
        except Exception as exc:
            log_voice("brain_error", error=str(exc))
            response = "I encountered an issue while processing your request."

        # Stop any ongoing filler speech, then speak the real response
        import maya_tts
        maya_tts.request_stop()
        time.sleep(0.1)

        if response:
            print(f"[maya] {response}")
            self.say(response)  # blocking — mic stays off until done

        self._touch()
        print("✅ Ready — listening...")

    # ── Shutdown ──────────────────────────────────────────────────────────

    def _shutdown(self) -> None:
        self._running = False
        self._end_conversation()
        log_voice("orchestrator_stop")
        print("\n[maya] stopped.")

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running


# ── CLI entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    orch = VoiceOrchestrator()
    try:
        orch.run()
    except KeyboardInterrupt:
        orch.stop()
        print("\nGoodbye.")
