"""
maya_tts.py
===========
Interruptible text-to-speech for MAYA.

Backends (set JARVIS_TTS_BACKEND in .env):
  * "piper"   - LOCAL neural voices (natural, fully offline once downloaded).
  * "pyttsx3" - Windows SAPI (robotic, but zero setup).
  * "sapi"    - dependency-free PowerShell SAPI fallback.

Speech is chunked by sentence and a stop flag is checked between chunks,
so barge-in halts MAYA almost immediately.

CLI:
    python maya_tts.py --list
    python maya_tts.py --download en_US-amy-medium
    python maya_tts.py "Hello, I am Maya."
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BACKEND = os.getenv("JARVIS_TTS_BACKEND", "pyttsx3").lower()
RATE = int(os.getenv("JARVIS_TTS_RATE", "178"))

# ── Piper (local neural) config ──────────────────────────────────────────
_PROJECT_DIR = Path(__file__).resolve().parent
VOICE = os.getenv("JARVIS_TTS_VOICE", "en_US-amy-medium")
VOICE_DIR = Path(os.getenv("JARVIS_TTS_VOICE_DIR", str(_PROJECT_DIR / "voices")))
SPEED = float(os.getenv("JARVIS_TTS_SPEED", "1.0"))
SPEAKER = os.getenv("JARVIS_TTS_SPEAKER")
_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

PIPER_CATALOG = {
    "en_US-amy-medium": "US female, warm (default)",
    "en_US-lessac-medium": "US female, very clear",
    "en_US-hfc_female-medium": "US female, neutral",
    "en_US-kristin-medium": "US female, soft",
    "en_GB-cori-high": "UK female, expressive (high quality)",
    "en_GB-jenny_dioco-medium": "UK female",
    "en_GB-alba-medium": "Scottish female",
    "en_GB-alan-medium": "UK male, calm",
    "en_US-ryan-high": "US male, natural (high quality)",
    "en_US-joe-medium": "US male, deep",
    "en_US-hfc_male-medium": "US male, neutral",
    "en_US-bryce-medium": "US male",
    "en_GB-northern_english_male-medium": "UK male, northern",
    "en_US-libritts_r-medium": "US, 900+ speakers (use JARVIS_TTS_SPEAKER)",
}

_URL_RE = re.compile(r"https?://\S+")
_MD_RE = re.compile(r"[*_`#>\[\]|]")

_stop = threading.Event()
_speaking = threading.Event()
_lock = threading.Lock()
_engine = {}
_piper = {}
_sd = None


def clean_for_speech(text: str) -> str:
    text = _URL_RE.sub("a link", text)
    text = _MD_RE.sub("", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    text = "".join(ch for ch in text if ch.isascii() or ch.isalpha())
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]


def request_stop() -> None:
    _stop.set()
    if _sd is not None:
        try:
            _sd.stop()
        except Exception:
            pass
    eng = _engine.get("e")
    if eng:
        try:
            eng.stop()
        except Exception:
            pass


def is_speaking() -> bool:
    return _speaking.is_set()


# ── Piper voice management ────────────────────────────────────────────────
def _hf_subpath(name: str) -> str:
    region, voice, quality = name.split("-", 2)
    lang = region.split("_")[0]
    return f"{lang}/{region}/{voice}/{quality}"


def download_voice(name: str, dest: Path | None = None) -> Path:
    import requests
    dest = dest or VOICE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    sub = _hf_subpath(name)
    for ext in (".onnx", ".onnx.json"):
        path = dest / (name + ext)
        if path.exists() and path.stat().st_size > 1000:
            print(f"[tts] have {path.name}")
            continue
        url = f"{_HF}/{sub}/{name}{ext}"
        print(f"[tts] downloading {name}{ext} ...")
        r = requests.get(url, stream=True, timeout=600)
        r.raise_for_status()
        total = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                total += len(chunk)
        print(f"[tts]   saved {path.name}  ({total / 1e6:.1f} MB)")
    return dest / (name + ".onnx")


def _get_piper_voice(name: str | None = None):
    name = name or VOICE
    if name in _piper:
        return _piper[name]
    from piper import PiperVoice
    model = VOICE_DIR / (name + ".onnx")
    if not model.exists():
        download_voice(name)
    voice = PiperVoice.load(str(model))
    _piper[name] = voice
    return voice


def warm() -> None:
    if BACKEND == "piper":
        try:
            _get_piper_voice()
        except Exception:
            pass


def _syn_config(voice):
    from piper.config import SynthesisConfig
    kwargs = {"length_scale": SPEED}
    if SPEAKER is not None and getattr(voice.config, "num_speakers", 1) > 1:
        try:
            kwargs["speaker_id"] = int(SPEAKER)
        except ValueError:
            pass
    return SynthesisConfig(**kwargs)


# ── Backends ─────────────────────────────────────────────────────────────
def _speak_piper(text: str, name: str | None = None) -> None:
    global _sd
    import numpy as np
    if _sd is None:
        import sounddevice as sd
        _sd = sd
    voice = _get_piper_voice(name)
    cfg = _syn_config(voice)
    parts = [c.audio_int16_array for c in voice.synthesize(text, syn_config=cfg)]
    if not parts:
        return
    audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
    _sd.play(audio, voice.config.sample_rate)
    _sd.wait()


def _speak_pyttsx3(text: str) -> None:
    import pyttsx3
    e = pyttsx3.init()
    _engine["e"] = e
    try:
        e.setProperty("rate", RATE)
        e.say(text)
        e.runAndWait()
    finally:
        try:
            e.stop()
        except Exception:
            pass
        _engine.pop("e", None)


def _speak_sapi(text: str) -> None:
    safe = text.replace("'", "''")
    rate = max(-10, min(10, round((RATE - 200) / 20)))
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"$v=New-Object -ComObject SAPI.SpVoice; $v.Rate={rate}; $v.Speak('{safe}') | Out-Null"],
                   check=False, capture_output=True)


_FUNCS = {"piper": _speak_piper, "pyttsx3": _speak_pyttsx3, "sapi": _speak_sapi}
_ORDER = {"piper": ["piper", "sapi"], "sapi": ["sapi", "pyttsx3"], "pyttsx3": ["pyttsx3", "sapi"]}


def _speak_one(text: str) -> None:
    for b in _ORDER.get(BACKEND, ["pyttsx3", "sapi"]):
        try:
            _FUNCS[b](text)
            return
        except Exception as exc:
            print(f"[tts:{b} failed: {exc}]", file=sys.stderr)
    print(f"[tts unavailable] {text}", file=sys.stderr)


def speak(text: str, allow_interrupt: bool = True) -> None:
    text = clean_for_speech(text)
    if not text:
        return
    with _lock:
        _stop.clear()
        _speaking.set()
        try:
            for sentence in _sentences(text):
                if allow_interrupt and _stop.is_set():
                    break
                _speak_one(sentence)
        finally:
            _speaking.clear()


def speak_async(text: str, allow_interrupt: bool = True) -> threading.Thread:
    t = threading.Thread(target=speak, args=(text, allow_interrupt), daemon=True)
    t.start()
    return t


# ── CLI ──────────────────────────────────────────────────────────────────
def _list_voices() -> None:
    print("Piper voices ([x] = downloaded). Set JARVIS_TTS_VOICE=<name> in .env.\n")
    for name, desc in PIPER_CATALOG.items():
        mark = "[x]" if (VOICE_DIR / (name + ".onnx")).exists() else "[ ]"
        print(f"  {mark} {name:38} {desc}")
    print(f"\nVoices dir: {VOICE_DIR}")


def main() -> None:
    ap = argparse.ArgumentParser(description="MAYA TTS - local neural voices (piper).")
    ap.add_argument("text", nargs="*", help="Text to speak.")
    ap.add_argument("--list", action="store_true", help="List voices.")
    ap.add_argument("--download", metavar="NAME", help="Download a voice model.")
    ap.add_argument("--voice", metavar="NAME", help="Test a specific voice.")
    args = ap.parse_args()

    if args.list:
        _list_voices()
        return
    if args.download:
        download_voice(args.download)
        print(f"[tts] done. Set JARVIS_TTS_VOICE={args.download} in .env to use it.")
        return

    text = " ".join(args.text) or "Hello, I am Maya. All systems are fully operational."
    if args.voice:
        try:
            _speak_piper(text, name=args.voice)
            return
        except Exception as exc:
            print(f"[tts:piper failed: {exc}] falling back.", file=sys.stderr)
    speak(text)


if __name__ == "__main__":
    main()
