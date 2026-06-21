"""MAYA AI Assistant — Main Entry Point

Usage:
    python main.py              → Interactive menu
    python main.py voice        → Voice mode (mic + speaker)
    python main.py text         → Text mode (keyboard + screen)
    python main.py tv           → Text in + Voice out (keyboard + speaker)
    python main.py vt           → Voice in + Text out (mic + screen)
    python main.py check        → Run prerequisite checks only
    python main.py test         → Run all test suites
    python main.py setup        → Install deps, pull models
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ═══════════════════════════════════════════════════════════════════════════════
# ANSI colors (Windows 10+ supports these)
# ═══════════════════════════════════════════════════════════════════════════════

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

os.system("")  # enable ANSI on Windows

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _ok(msg: str) -> None:
    print(f"  {_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_RED}[FAIL]{_RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_YELLOW}[WARN]{_RESET} {msg}")


def _info(msg: str) -> None:
    print(f"  {_DIM}→{_RESET} {msg}")


def _header(msg: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{msg}{_RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# Prerequisite checks
# ═══════════════════════════════════════════════════════════════════════════════

_REQUIRED_PACKAGES = [
    ("pydantic", "pydantic>=2.0"),
    ("ollama", "ollama>=0.4.0"),
    ("dotenv", "python-dotenv>=1.0.0"),
    ("chromadb", "chromadb>=0.5.0"),
    ("pyttsx3", "pyttsx3"),
    ("speech_recognition", "SpeechRecognition"),
]

_VOICE_PACKAGES = [
    ("faster_whisper", "faster-whisper"),
    ("sounddevice", "sounddevice"),
    ("groq", "groq"),
    ("numpy", "numpy"),
]


def _check_python_version() -> bool:
    v = sys.version_info
    if v >= (3, 10):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    _fail(f"Python {v.major}.{v.minor}.{v.micro} — need 3.10+")
    return False


def _check_package(module_name: str, pip_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        _ok(pip_name)
        return True
    except ImportError:
        _fail(f"{pip_name} — not installed")
        return False


def _check_ollama_running() -> bool:
    try:
        import ollama as _ollama
        _ollama.list()
        _ok("Ollama is running")
        return True
    except Exception:
        _fail("Ollama is not running — start with: ollama serve")
        return False


def _get_ollama_models() -> set[str]:
    try:
        import ollama as _ollama
        response = _ollama.list()
        models = set()
        for m in response.get("models", []):
            name = m.get("name", "") if isinstance(m, dict) else getattr(m, "model", "")
            if name:
                models.add(name)
                if ":" in name:
                    models.add(name.split(":")[0])
        return models
    except Exception:
        return set()


def _check_model(model_name: str, available: set[str]) -> bool:
    base = model_name.split(":")[0]
    if model_name in available or base in available:
        _ok(f"Model: {model_name}")
        return True
    _fail(f"Model: {model_name} — not found")
    return False


def _check_registry() -> bool:
    reg = PROJECT_ROOT / "system" / "agent_registry.json"
    if reg.exists():
        with open(reg) as f:
            data = json.load(f)
        count = len(data) if isinstance(data, (list, dict)) else 0
        _ok(f"Agent registry ({count} agents)")
        return True
    _fail("Agent registry missing — run: python build_registry.py")
    return False


def _check_agents() -> int:
    agents_dir = PROJECT_ROOT / "agents"
    if not agents_dir.is_dir():
        _fail("agents/ directory not found")
        return 0
    agents = list(agents_dir.glob("*_agent.py"))
    _ok(f"{len(agents)} agents found")
    return len(agents)


def _check_directories() -> None:
    dirs = [
        PROJECT_ROOT / "brain" / "logs",
        PROJECT_ROOT / "memory" / "active_chat",
        PROJECT_ROOT / "memory" / "archive",
        PROJECT_ROOT / "memory" / "chat_summaries",
        PROJECT_ROOT / "memory" / "vector_db",
    ]
    created = 0
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created += 1
    if created:
        _ok(f"Created {created} missing directories")
    else:
        _ok("All directories exist")


def run_checks(*, voice: bool = True) -> dict:
    """Run all prerequisite checks. Returns a status dict."""
    results = {
        "python": False,
        "packages": False,
        "voice_packages": False,
        "ollama": False,
        "models": False,
        "registry": False,
        "agents": 0,
    }

    _header("Python")
    results["python"] = _check_python_version()

    _header("Core Packages")
    pkg_ok = all(_check_package(mod, pip) for mod, pip in _REQUIRED_PACKAGES)
    results["packages"] = pkg_ok

    if voice:
        _header("Voice Packages")
        vpkg_ok = all(_check_package(mod, pip) for mod, pip in _VOICE_PACKAGES)
        results["voice_packages"] = vpkg_ok

    _header("Ollama")
    results["ollama"] = _check_ollama_running()

    if results["ollama"]:
        _header("LLM Models")
        available = _get_ollama_models()
        from brain.utils.config import PLANNER_MODEL, RESPONSE_MODEL
        p = _check_model(PLANNER_MODEL, available)
        r = _check_model(RESPONSE_MODEL, available)
        results["models"] = p and r
        if not p:
            _info(f"Pull with: ollama pull {PLANNER_MODEL}")
        if not r:
            _info(f"Pull with: ollama pull {RESPONSE_MODEL}")

    _header("Agent System")
    results["registry"] = _check_registry()
    results["agents"] = _check_agents()

    _header("Directories")
    _check_directories()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Install missing packages
# ═══════════════════════════════════════════════════════════════════════════════

def install_packages(include_voice: bool = True) -> bool:
    _header("Installing Dependencies")
    packages = [pip for _, pip in _REQUIRED_PACKAGES]
    if include_voice:
        packages += [pip for _, pip in _VOICE_PACKAGES]

    missing = []
    for mod, pip_name in _REQUIRED_PACKAGES + (_VOICE_PACKAGES if include_voice else []):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        _ok("All packages already installed")
        return True

    _info(f"Installing {len(missing)} packages: {', '.join(missing)}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + missing,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        _ok("Installation complete")
        return True
    except subprocess.CalledProcessError:
        _fail("pip install failed — check errors above")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Pull missing models
# ═══════════════════════════════════════════════════════════════════════════════

def pull_models() -> bool:
    _header("Pulling LLM Models")
    try:
        from brain.utils.config import PLANNER_MODEL, RESPONSE_MODEL
        available = _get_ollama_models()
        models_needed = []

        for model in [PLANNER_MODEL, RESPONSE_MODEL]:
            base = model.split(":")[0]
            if model not in available and base not in available:
                models_needed.append(model)

        if not models_needed:
            _ok("All models already available")
            return True

        for model in models_needed:
            _info(f"Pulling {model}... (this may take a while)")
            try:
                subprocess.check_call(
                    ["ollama", "pull", model],
                    timeout=1800,  # 30 min max
                )
                _ok(f"Pulled {model}")
            except subprocess.CalledProcessError:
                _fail(f"Failed to pull {model}")
                return False
            except FileNotFoundError:
                _fail("ollama command not found — install from https://ollama.com")
                return False

        return True
    except Exception as exc:
        _fail(f"Error: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Build registry if missing
# ═══════════════════════════════════════════════════════════════════════════════

def build_registry() -> bool:
    reg = PROJECT_ROOT / "system" / "agent_registry.json"
    if reg.exists():
        _ok("Registry already exists")
        return True

    builder = PROJECT_ROOT / "build_registry.py"
    if not builder.exists():
        _fail("build_registry.py not found")
        return False

    _info("Building agent registry...")
    try:
        subprocess.check_call([sys.executable, str(builder)], cwd=str(PROJECT_ROOT))
        _ok("Registry built")
        return True
    except subprocess.CalledProcessError:
        _fail("Registry build failed")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Run tests
# ═══════════════════════════════════════════════════════════════════════════════

def run_tests() -> int:
    _header("Running Test Suites")
    test_files = [
        ("Brain Core", "tests/test_brain.py"),
        ("Memory Layer", "tests/test_memory.py"),
        ("Voice Layer", "tests/test_voice.py"),
    ]

    total_pass = total_fail = 0
    for name, path in test_files:
        full = PROJECT_ROOT / path
        if not full.exists():
            _warn(f"{name}: {path} not found, skipping")
            continue

        print(f"\n  {_BOLD}{name}{_RESET} ({path})")
        result = subprocess.run(
            [sys.executable, str(full)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

        # Parse last line for pass/fail counts
        lines = (result.stdout + result.stderr).strip().split("\n")
        summary = lines[-1] if lines else ""
        print(f"    {summary}")

        if result.returncode == 0:
            _ok(f"{name} — all passed")
        else:
            _fail(f"{name} — some tests failed")

    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Start modes
# ═══════════════════════════════════════════════════════════════════════════════

def start_voice_mode() -> None:
    _header("Starting MAYA — Voice Mode")
    print(f"  {_DIM}Say 'Maya' to activate. Ctrl+C to quit.{_RESET}\n")

    from voice.voice_orchestrator import VoiceOrchestrator
    orch = VoiceOrchestrator()
    try:
        orch.run()
    except KeyboardInterrupt:
        orch.stop()
        print(f"\n{_DIM}Goodbye.{_RESET}")


def start_text_voice_mode() -> None:
    """Text input with voice output — type commands, hear responses."""
    _header("Starting MAYA — Text + Voice Mode")
    print(f"  {_DIM}Type your commands. MAYA speaks the responses. 'quit' to stop.{_RESET}\n")

    from brain.brain import Brain
    import maya_tts

    brain = Brain(enable_memory=True)
    _ok("Brain initialized with memory\n")

    while True:
        try:
            command = input(f"{_CYAN}You:{_RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{_DIM}Goodbye.{_RESET}")
            break
        if not command:
            continue
        if command.lower() in ("quit", "exit", "bye", "q"):
            maya_tts.speak("Goodbye.")
            break
        try:
            start = time.perf_counter()
            response = brain.process(command)
            elapsed = time.perf_counter() - start
            print(f"{_GREEN}MAYA:{_RESET} {response}")
            print(f"{_DIM}  [{elapsed:.1f}s]{_RESET}")
            maya_tts.speak(response)
            print()
        except KeyboardInterrupt:
            maya_tts.request_stop()
            print(f"\n{_YELLOW}  Cancelled.{_RESET}\n")
        except Exception as exc:
            print(f"{_RED}  Error: {exc}{_RESET}\n")


def start_voice_text_mode() -> None:
    """Voice input with text output — speak commands, read responses on screen."""
    _header("Starting MAYA — Voice In + Text Out")
    print(f"  {_DIM}Say 'Maya' then your command. Responses shown as text. Ctrl+C to quit.{_RESET}\n")

    import numpy as np
    from voice.voice_orchestrator import (
        _ensure_loaded, _sr, _recog, _transcribe_fast, _transcribe_accurate,
        has_wake, strip_wake, _is_real_command, END_SILENCE,
    )
    from brain.brain import Brain

    _ensure_loaded()
    brain = Brain(enable_memory=True)
    _ok("Brain initialized with memory\n")

    with _sr.Microphone(sample_rate=16000) as src:
        print(f"  {_DIM}Adjusting for ambient noise...{_RESET}")
        _recog.adjust_for_ambient_noise(src, duration=1.0)
        _recog.energy_threshold = max(_recog.energy_threshold, 200)
        print(f"  {_GREEN}Ready!{_RESET} Say 'Maya' followed by your command.\n")

        while True:
            try:
                audio = _recog.listen(src, phrase_time_limit=15)
            except KeyboardInterrupt:
                print(f"\n{_DIM}Goodbye.{_RESET}")
                break
            except Exception:
                continue

            gist = _transcribe_fast(audio)
            if not gist:
                continue
            if not has_wake(gist):
                print(f"\r{_DIM}[idle] {gist[:60]:<60}{_RESET}", end="", flush=True)
                continue

            accurate = _transcribe_accurate(audio) or gist
            command = strip_wake(accurate)
            if not command:
                print(f"\n{_CYAN}You:{_RESET} (just the wake word)")
                # Listen once more for the actual command
                try:
                    follow = _recog.listen(src, timeout=8, phrase_time_limit=15)
                    command = (_transcribe_accurate(follow) or "").strip()
                except Exception:
                    command = ""
                if not _is_real_command(command):
                    print(f"  {_DIM}Didn't catch a command.{_RESET}\n")
                    continue

            print(f"\n{_CYAN}You:{_RESET} {command}")

            try:
                start = time.perf_counter()
                response = brain.process(command)
                elapsed = time.perf_counter() - start
                print(f"{_GREEN}MAYA:{_RESET} {response}")
                print(f"{_DIM}  [{elapsed:.1f}s]{_RESET}\n")
            except KeyboardInterrupt:
                print(f"\n{_YELLOW}  Cancelled.{_RESET}\n")
            except Exception as exc:
                print(f"{_RED}  Error: {exc}{_RESET}\n")


def start_text_mode() -> None:
    _header("Starting MAYA — Text Mode")
    print(f"  {_DIM}Type your commands. 'quit' or 'exit' to stop.{_RESET}\n")

    from brain.brain import Brain
    brain = Brain(enable_memory=True)
    _ok("Brain initialized with memory\n")

    while True:
        try:
            command = input(f"{_CYAN}You:{_RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{_DIM}Goodbye.{_RESET}")
            break

        if not command:
            continue
        if command.lower() in ("quit", "exit", "bye", "q"):
            print(f"{_DIM}Goodbye.{_RESET}")
            break

        try:
            start = time.perf_counter()
            response = brain.process(command)
            elapsed = time.perf_counter() - start
            print(f"{_GREEN}MAYA:{_RESET} {response}")
            print(f"{_DIM}  [{elapsed:.1f}s]{_RESET}\n")
        except KeyboardInterrupt:
            print(f"\n{_YELLOW}  Cancelled.{_RESET}\n")
        except Exception as exc:
            print(f"{_RED}  Error: {exc}{_RESET}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Setup wizard
# ═══════════════════════════════════════════════════════════════════════════════

def setup() -> bool:
    """Run full setup: install packages, pull models, build registry."""
    _header("MAYA Setup")

    print(f"\n  {_BOLD}Step 1/4:{_RESET} Install Python packages")
    install_packages(include_voice=True)

    print(f"\n  {_BOLD}Step 2/4:{_RESET} Check Ollama")
    if not _check_ollama_running():
        _info("Start Ollama first: ollama serve")
        _info("Then re-run: python main.py setup")
        return False

    print(f"\n  {_BOLD}Step 3/4:{_RESET} Pull LLM models")
    pull_models()

    print(f"\n  {_BOLD}Step 4/4:{_RESET} Build agent registry")
    build_registry()

    _header("Setup Complete")
    _check_directories()

    print(f"\n  Start MAYA with:")
    _info("python main.py voice   — voice assistant")
    _info("python main.py text    — text chat")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive menu
# ═══════════════════════════════════════════════════════════════════════════════

_BANNER = f"""
{_CYAN}{_BOLD}
  ███╗   ███╗ █████╗ ██╗   ██╗ █████╗
  ████╗ ████║██╔══██╗╚██╗ ██╔╝██╔══██╗
  ██╔████╔██║███████║ ╚████╔╝ ███████║
  ██║╚██╔╝██║██╔══██║  ╚██╔╝  ██╔══██║
  ██║ ╚═╝ ██║██║  ██║   ██║   ██║  ██║
  ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝
{_RESET}{_DIM}  Your AI Assistant — Brain · Memory · Voice{_RESET}
"""


def interactive_menu() -> None:
    print(_BANNER)
    print(f"  {_BOLD}1{_RESET}  Voice Mode            {_DIM}(mic + speaker){_RESET}")
    print(f"  {_BOLD}2{_RESET}  Text Mode             {_DIM}(keyboard + screen){_RESET}")
    print(f"  {_BOLD}3{_RESET}  Text In + Voice Out   {_DIM}(keyboard + speaker){_RESET}")
    print(f"  {_BOLD}4{_RESET}  Voice In + Text Out   {_DIM}(mic + screen){_RESET}")
    print(f"  {_BOLD}5{_RESET}  Run Setup             {_DIM}(install deps, pull models){_RESET}")
    print(f"  {_BOLD}6{_RESET}  Check Prerequisites   {_DIM}(verify everything){_RESET}")
    print(f"  {_BOLD}7{_RESET}  Run Tests             {_DIM}(all test suites){_RESET}")
    print(f"  {_BOLD}8{_RESET}  Exit")
    print()

    try:
        choice = input(f"  {_CYAN}Select [1-8]:{_RESET} ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{_DIM}Goodbye.{_RESET}")
        return

    if choice == "1":
        results = run_checks(voice=True)
        if results["ollama"] and results["packages"]:
            start_voice_mode()
        else:
            print(f"\n  {_YELLOW}Fix the issues above, or run setup first (option 5).{_RESET}")
    elif choice == "2":
        results = run_checks(voice=False)
        if results["ollama"] and results["packages"]:
            start_text_mode()
        else:
            print(f"\n  {_YELLOW}Fix the issues above, or run setup first (option 5).{_RESET}")
    elif choice == "3":
        results = run_checks(voice=False)
        if results["ollama"] and results["packages"]:
            start_text_voice_mode()
        else:
            print(f"\n  {_YELLOW}Fix the issues above, or run setup first (option 5).{_RESET}")
    elif choice == "4":
        results = run_checks(voice=True)
        if results["ollama"] and results["packages"]:
            start_voice_text_mode()
        else:
            print(f"\n  {_YELLOW}Fix the issues above, or run setup first (option 5).{_RESET}")
    elif choice == "5":
        setup()
    elif choice == "6":
        run_checks(voice=True)
    elif choice == "7":
        run_tests()
    elif choice == "8":
        print(f"{_DIM}Goodbye.{_RESET}")
    else:
        print(f"{_RED}Invalid choice.{_RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if len(sys.argv) < 2:
        interactive_menu()
        return

    cmd = sys.argv[1].lower()

    if cmd == "voice":
        run_checks(voice=True)
        start_voice_mode()
    elif cmd == "text":
        run_checks(voice=False)
        start_text_mode()
    elif cmd in ("text-voice", "tv"):
        run_checks(voice=False)
        start_text_voice_mode()
    elif cmd in ("voice-text", "vt"):
        run_checks(voice=True)
        start_voice_text_mode()
    elif cmd == "check":
        run_checks(voice=True)
    elif cmd == "test":
        run_tests()
    elif cmd == "setup":
        setup()
    elif cmd == "api":
        import uvicorn
        _header("Starting MAYA API Server")
        uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
    elif cmd in ("help", "--help", "-h"):
        print(__doc__)
    else:
        print(f"{_RED}Unknown command: {cmd}{_RESET}")
        print(__doc__)


if __name__ == "__main__":
    main()
