"""Tests for the Memory Layer.

Runs without Ollama — LLM calls in the summarizer are mocked.
ChromaDB uses an ephemeral/temp directory.

Run:
    python -m pytest tests/test_memory.py -v
    python tests/test_memory.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Redirect all memory dirs to a temp directory for test isolation
_TEMP_DIR = Path(tempfile.mkdtemp(prefix="maya_test_memory_"))


def _patch_config():
    """Monkey-patch memory.config paths to use temp dir."""
    import memory.config as cfg

    cfg.MEMORY_DIR = _TEMP_DIR
    cfg.ACTIVE_CHAT_DIR = _TEMP_DIR / "active_chat"
    cfg.ARCHIVE_DIR = _TEMP_DIR / "archive"
    cfg.CHAT_SUMMARIES_DIR = _TEMP_DIR / "chat_summaries"
    cfg.LONG_TERM_DIR = _TEMP_DIR / "long_term"
    cfg.AGENT_HISTORY_DIR = _TEMP_DIR / "agent_history"
    cfg.PLANNER_HISTORY_DIR = _TEMP_DIR / "planner_history"
    cfg.VECTORS_DIR = _TEMP_DIR / "vectors"
    cfg.BRAIN_STATE_PATH = _TEMP_DIR / "brain_state.json"
    cfg.LONG_TERM_MEMORY_PATH = cfg.LONG_TERM_DIR / "long_term_memory.json"
    cfg.ALL_DIRS = [
        cfg.MEMORY_DIR, cfg.ACTIVE_CHAT_DIR, cfg.ARCHIVE_DIR,
        cfg.CHAT_SUMMARIES_DIR, cfg.LONG_TERM_DIR, cfg.AGENT_HISTORY_DIR,
        cfg.PLANNER_HISTORY_DIR, cfg.VECTORS_DIR,
    ]


_patch_config()

from memory.active_chat import ActiveChat
from memory.agent_history import AgentHistory
from memory.chat_rotator import ChatRotator
from memory.chat_summarizer import ChatSummarizer
from memory.config import ensure_dirs
from memory.context_builder import ContextBuilder
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.planner_history import PlannerHistory
from memory.recovery import RecoveryManager
from memory.schemas import (
    BrainState,
    Chat,
    ChatMessage,
    ChatSummary,
    LongTermMemoryStore,
    MemoryCategory,
    MemoryEntry,
    MessageRole,
)
from memory.vector_memory import VectorMemory


# ═══════════════════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_chat_message_schema():
    msg = ChatMessage(role=MessageRole.USER, content="hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "hello"
    assert msg.timestamp is not None


def test_chat_schema():
    chat = Chat(chat_id="test_123")
    assert chat.chat_id == "test_123"
    assert chat.messages == []
    assert chat.message_count == 0


def test_memory_entry_schema():
    entry = MemoryEntry(
        id="abc123",
        category=MemoryCategory.PROJECTS,
        content="Working on MAYA",
        importance=0.9,
    )
    assert entry.importance == 0.9
    assert entry.category == MemoryCategory.PROJECTS


def test_memory_entry_importance_bounds():
    import pytest
    with pytest.raises(Exception):
        MemoryEntry(
            id="x", category=MemoryCategory.FACTS,
            content="test", importance=1.5,
        )


def test_chat_summary_schema():
    s = ChatSummary(chat_id="c1", summary="test summary")
    assert s.summary == "test summary"
    assert s.key_topics == []


def test_brain_state_schema():
    state = BrainState()
    assert state.active_chat_id is None
    assert state.unfinished_tasks == []


# ═══════════════════════════════════════════════════════════════════════════
# Active Chat Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_active_chat_create():
    ensure_dirs()
    ac = ActiveChat()
    chat_id = ac.create_new()
    assert chat_id is not None
    assert ac.message_count == 0


def test_active_chat_add_messages():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "Hello MAYA")
    ac.add_message("assistant", "Hi there!")
    assert ac.message_count == 2


def test_active_chat_get_recent():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    for i in range(15):
        ac.add_message("user", f"Message {i}")
    recent = ac.get_recent_messages(limit=5)
    assert len(recent) == 5
    assert recent[-1]["content"] == "Message 14"


def test_active_chat_persistence():
    ensure_dirs()
    ac = ActiveChat()
    chat_id = ac.create_new()
    ac.add_message("user", "Persistent message")

    ac2 = ActiveChat()
    loaded = ac2.load_existing(chat_id)
    assert loaded
    assert ac2.message_count == 1
    assert ac2.get_recent_messages(1)[0]["content"] == "Persistent message"


def test_active_chat_text():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "What time is it?")
    ac.add_message("assistant", "It's 3pm")
    text = ac.get_messages_as_text()
    assert "user: What time is it?" in text
    assert "assistant: It's 3pm" in text


def test_active_chat_clear():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "test")
    ac.clear()
    assert ac.chat is None
    assert ac.message_count == 0


def test_active_chat_tokens():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "a" * 400)
    assert ac.estimated_tokens >= 100


# ═══════════════════════════════════════════════════════════════════════════
# Long-Term Memory Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_ltm_add_memory():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    mid = ltm.add_memory("projects", "Working on MAYA AI", 0.9)
    assert mid is not None


def test_ltm_below_threshold():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    mid = ltm.add_memory("facts", "Unimportant fact", 0.3)
    assert mid is None


def test_ltm_duplicate_prevention():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    ltm.add_memory("goals", "Finish Phase 2", 0.9)
    mid2 = ltm.add_memory("goals", "Finish Phase 2", 0.95)
    assert mid2 is None


def test_ltm_search():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    ltm.add_memory("projects", "Building a voice assistant called MAYA", 0.9, tags=["maya", "voice"])
    ltm.add_memory("preferences", "User prefers dark mode", 0.8, tags=["ui"])
    results = ltm.search_memories("voice assistant")
    assert len(results) >= 1
    assert any("MAYA" in r.content for r in results)


def test_ltm_update():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    mid = ltm.add_memory("facts", "Python 3.11 is used", 0.8)
    assert mid is not None
    success = ltm.update_memory(mid, content="Python 3.12 is used")
    assert success
    mem = ltm.get_memory_by_id(mid)
    assert mem is not None
    assert "3.12" in mem.content


def test_ltm_delete():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    mid = ltm.add_memory("skills", "User knows Python", 0.85)
    assert mid is not None
    success = ltm.delete_memory(mid)
    assert success
    assert ltm.get_memory_by_id(mid) is None


def test_ltm_get_all_as_text():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    ltm.add_memory("decisions", "Using Ollama for local inference", 0.9)
    text = ltm.get_all_as_text()
    assert isinstance(text, str)


def test_ltm_summary():
    ensure_dirs()
    ltm = LongTermMemory()
    ltm.load()
    summary = ltm.get_summary()
    assert isinstance(summary, dict)
    assert "projects" in summary


# ═══════════════════════════════════════════════════════════════════════════
# Chat Rotator Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_rotator_no_rotation_needed():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "hello")
    summarizer = ChatSummarizer()
    rotator = ChatRotator(ac, summarizer)
    assert not rotator.needs_rotation()


def test_rotator_rotation_by_messages():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    summarizer = ChatSummarizer()
    rotator = ChatRotator(ac, summarizer, max_messages=5, max_tokens=999999)

    for i in range(6):
        ac.add_message("user", f"msg {i}")

    assert rotator.needs_rotation()


def test_rotator_rotate_creates_new_chat():
    ensure_dirs()
    ac = ActiveChat()
    old_id = ac.create_new()
    ac.add_message("user", "test message for rotation")

    summarizer = ChatSummarizer()

    mock_summary = ChatSummary(chat_id=old_id, summary="Test chat about rotation")
    with patch.object(summarizer, "summarize_chat", return_value=mock_summary):
        rotator = ChatRotator(ac, summarizer)
        summary, new_id = rotator.rotate()

    assert new_id != old_id
    assert summary is not None
    assert summary.chat_id == old_id


# ═══════════════════════════════════════════════════════════════════════════
# Agent History Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_agent_history_record():
    ensure_dirs()
    ah = AgentHistory()
    ah.record(
        agent="gmail_agent",
        action="get_unread_emails",
        parameters={"limit": 5},
        status="success",
        result_summary="Found 3 unread emails",
        duration_ms=150.0,
    )
    recent = ah.get_recent(1)
    assert len(recent) == 1
    assert recent[0].agent == "gmail_agent"


def test_agent_history_by_agent():
    ensure_dirs()
    ah = AgentHistory()
    ah.record(agent="a", action="x", parameters={})
    ah.record(agent="b", action="y", parameters={})
    ah.record(agent="a", action="z", parameters={})
    by_a = ah.get_by_agent("a")
    assert len(by_a) == 2


def test_agent_history_text():
    ensure_dirs()
    ah = AgentHistory()
    ah.record(agent="todo_agent", action="add_todo", parameters={"text": "test"}, result_summary="Added")
    text = ah.get_recent_as_text(1)
    assert "todo_agent" in text


def test_agent_history_stats():
    ensure_dirs()
    ah = AgentHistory()
    ah.record(agent="x", action="a", parameters={})
    ah.record(agent="x", action="b", parameters={})
    stats = ah.get_stats()
    assert stats["total_recent"] >= 2


# ═══════════════════════════════════════════════════════════════════════════
# Planner History Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_planner_history_record():
    ensure_dirs()
    ph = PlannerHistory()
    ph.record(
        user_command="check emails",
        plan_json={"tasks": []},
        execution_results=[],
        response="No new emails",
    )
    recent = ph.get_recent(1)
    assert len(recent) == 1
    assert recent[0].user_command == "check emails"


def test_planner_history_text():
    ensure_dirs()
    ph = PlannerHistory()
    ph.record("test cmd", {"tasks": [{"id": "t1"}]}, [], "done")
    text = ph.get_recent_as_text(1)
    assert "test cmd" in text


# ═══════════════════════════════════════════════════════════════════════════
# Recovery Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_recovery_save_and_load():
    ensure_dirs()
    rm = RecoveryManager()
    rm.load()
    rm.save_active_chat("chat_abc")
    rm.save_current_project("MAYA")
    rm.save_unfinished_tasks([{"id": "t1", "desc": "finish memory"}])

    rm2 = RecoveryManager()
    state = rm2.load()
    assert state.active_chat_id == "chat_abc"
    assert state.current_project == "MAYA"
    assert len(state.unfinished_tasks) == 1


def test_recovery_clear():
    ensure_dirs()
    rm = RecoveryManager()
    rm.load()
    rm.save_unfinished_tasks([{"id": "t1"}])
    rm.clear_unfinished_tasks()
    assert rm.state.unfinished_tasks == []


def test_recovery_info():
    ensure_dirs()
    rm = RecoveryManager()
    rm.load()
    rm.save_active_chat("test_chat")
    info = rm.get_recovery_info()
    assert info["has_active_chat"] is True
    assert info["active_chat_id"] == "test_chat"


def test_recovery_full_save():
    ensure_dirs()
    rm = RecoveryManager()
    rm.load()
    rm.full_save(
        chat_id="c1",
        project="proj",
        unfinished_tasks=[],
        queue_state={"pending": 0},
        planner_state={"last": "ok"},
    )
    assert rm.state.active_chat_id == "c1"
    assert rm.state.current_project == "proj"
    assert rm.state.queue_state == {"pending": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Vector Memory Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_vector_add_and_search():
    ensure_dirs()
    vm = VectorMemory()
    vm.add("The weather in Tokyo is sunny today", doc_type="test")
    vm.add("User prefers Python over JavaScript", doc_type="test")
    vm.add("MAYA project uses Ollama for inference", doc_type="test")

    results = vm.search("weather forecast", top_k=2)
    assert len(results) >= 1
    assert any("weather" in r["text"].lower() or "sunny" in r["text"].lower() for r in results)


def test_vector_count():
    ensure_dirs()
    vm = VectorMemory()
    initial = vm.count()
    vm.add("Test document for counting", doc_type="test")
    assert vm.count() == initial + 1


def test_vector_delete():
    ensure_dirs()
    vm = VectorMemory()
    doc_id = vm.add("Delete me", doc_type="test")
    before = vm.count()
    vm.delete(doc_id)
    assert vm.count() == before - 1


def test_vector_batch_add():
    ensure_dirs()
    vm = VectorMemory()
    before = vm.count()
    ids = vm.add_batch(
        ["Doc one", "Doc two", "Doc three"],
        doc_type="test_batch",
    )
    assert len(ids) == 3
    assert vm.count() == before + 3


def test_vector_type_filter():
    ensure_dirs()
    vm = VectorMemory()
    vm.add("Memory type A", doc_type="type_a")
    vm.add("Memory type B", doc_type="type_b")
    results = vm.search("memory", doc_type="type_a", top_k=10)
    for r in results:
        assert r["metadata"].get("type") == "type_a"


# ═══════════════════════════════════════════════════════════════════════════
# Context Builder Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_context_builder_basic():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "I need help with MAYA")
    ac.add_message("assistant", "Sure, what do you need?")

    ltm = LongTermMemory()
    ltm.load()
    ltm.add_memory("projects", "MAYA is a voice AI assistant", 0.9)

    vm = VectorMemory()
    ah = AgentHistory()
    ph = PlannerHistory()

    cb = ContextBuilder(ac, ltm, vm, ah, ph)
    ctx = cb.build("tell me about MAYA", include_vectors=False)
    assert "MAYA" in ctx


def test_context_builder_compact():
    ensure_dirs()
    ac = ActiveChat()
    ac.create_new()
    ac.add_message("user", "hello")

    ltm = LongTermMemory()
    ltm.load()

    vm = VectorMemory()
    ah = AgentHistory()
    ph = PlannerHistory()

    cb = ContextBuilder(ac, ltm, vm, ah, ph)
    ctx = cb.build_compact("greeting")
    assert isinstance(ctx, str)


# ═══════════════════════════════════════════════════════════════════════════
# Chat Summarizer Tests (mocked LLM)
# ═══════════════════════════════════════════════════════════════════════════

def test_summarizer_with_mock():
    ensure_dirs()
    s = ChatSummarizer()

    mock_response = json.dumps({
        "summary": "User asked about weather",
        "key_topics": ["weather"],
        "important_facts": ["User lives in Tokyo"],
        "projects": [],
        "decisions": [],
        "todos": ["Check weather daily"],
    })

    messages = [
        ChatMessage(role=MessageRole.USER, content="What's the weather?"),
        ChatMessage(role=MessageRole.ASSISTANT, content="It's sunny in Tokyo"),
    ]

    with patch.object(s, "_call_llm", return_value=mock_response):
        summary = s.summarize_chat("test_chat", messages)

    assert summary.summary == "User asked about weather"
    assert "weather" in summary.key_topics
    assert len(summary.todos) == 1


def test_summarizer_fallback():
    ensure_dirs()
    s = ChatSummarizer()

    messages = [
        ChatMessage(role=MessageRole.USER, content="hello world"),
    ]

    with patch.object(s, "_call_llm", side_effect=Exception("LLM down")):
        summary = s.summarize_chat("fallback_test", messages)

    assert summary.chat_id == "fallback_test"
    assert "1 messages" in summary.summary


def test_summarizer_extract_memories_mock():
    ensure_dirs()
    s = ChatSummarizer()

    mock_response = json.dumps([
        {
            "category": "projects",
            "content": "User works on MAYA AI",
            "importance": 0.9,
            "tags": ["maya", "ai"],
        }
    ])

    messages = [
        ChatMessage(role=MessageRole.USER, content="I'm building MAYA AI"),
    ]

    with patch.object(s, "_call_llm", return_value=mock_response):
        memories = s.extract_memories(messages, chat_id="test")

    assert len(memories) == 1
    assert memories[0]["category"] == "projects"
    assert "id" in memories[0]


# ═══════════════════════════════════════════════════════════════════════════
# Memory Manager Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_memory_manager_startup():
    ensure_dirs()
    mm = MemoryManager()
    info = mm.startup()
    assert "active_chat_id" in info


def test_memory_manager_add_messages():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    # Force a fresh chat so prior test state doesn't interfere
    mm.active_chat.create_new()
    mm.add_user_message("Test user message")
    mm.add_assistant_message("Test assistant response")
    assert mm.active_chat.message_count == 2


def test_memory_manager_store_and_search():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    mid = mm.store_memory("projects", "Building MAYA voice assistant", 0.9, tags=["maya"])
    assert mid is not None
    results = mm.search_memory("MAYA")
    assert len(results) >= 1


def test_memory_manager_context():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    mm.add_user_message("I need to check my emails")
    ctx = mm.get_context_for_planner("check emails")
    assert isinstance(ctx, str)


def test_memory_manager_record_agent():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    mm.record_agent_execution(
        agent="gmail_agent",
        action="get_unread_emails",
        parameters={"limit": 5},
        status="success",
        result_summary="3 unread emails found",
    )
    recent = mm.agent_history.get_recent(1)
    assert len(recent) == 1


def test_memory_manager_record_planner():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    mm.record_planner_execution(
        user_command="check emails",
        plan_json={"tasks": []},
        execution_results=[],
        response="No new emails",
    )
    recent = mm.planner_history.get_recent(1)
    assert len(recent) == 1


def test_memory_manager_save_state():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    mm.save_state(project="MAYA", unfinished_tasks=[{"id": "t1"}])
    info = mm.recovery.get_recovery_info()
    assert info["current_project"] == "MAYA"


def test_memory_manager_status():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    status = mm.get_status()
    assert "active_chat_id" in status
    assert "long_term_summary" in status


def test_memory_manager_force_rotate():
    ensure_dirs()
    mm = MemoryManager()
    mm.startup()
    mm.add_user_message("Test before rotation")

    mock_summary = ChatSummary(chat_id="old", summary="test rotation")
    with patch.object(mm.summarizer, "summarize_chat", return_value=mock_summary):
        with patch.object(mm.summarizer, "extract_memories", return_value=[]):
            summary, new_id = mm.force_rotate()
    assert new_id is not None


# ═══════════════════════════════════════════════════════════════════════════
# Memory Agent Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_memory_agent_store():
    ensure_dirs()
    from agents.memory_agent import execute

    # Reset the singleton
    import agents.memory_agent as ma
    ma._manager = None

    result = execute({
        "action": "store_memory",
        "parameters": {
            "category": "facts",
            "content": "Test fact from agent",
            "importance": 0.85,
        },
    })
    assert result["status"] == "success"


def test_memory_agent_search():
    ensure_dirs()
    from agents.memory_agent import execute

    result = execute({
        "action": "search_memory",
        "parameters": {"query": "test"},
    })
    assert result["status"] == "success"
    assert "keyword_results" in result


def test_memory_agent_get_status():
    ensure_dirs()
    from agents.memory_agent import execute

    result = execute({
        "action": "get_status",
        "parameters": {},
    })
    assert result["status"] == "success"


def test_memory_agent_unknown_action():
    from agents.memory_agent import execute

    result = execute({
        "action": "nonexistent_action",
        "parameters": {},
    })
    assert result["status"] == "error"
    assert "available_actions" in result


def test_memory_agent_missing_params():
    from agents.memory_agent import execute

    result = execute({
        "action": "store_memory",
        "parameters": {"category": "facts"},
    })
    assert result["status"] == "error"
    assert "Missing" in result["message"]


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup & Runner
# ═══════════════════════════════════════════════════════════════════════════

def _cleanup():
    try:
        shutil.rmtree(_TEMP_DIR, ignore_errors=True)
    except Exception:
        pass


def _run_all() -> int:
    tests = [
        (name, func)
        for name, func in sorted(globals().items())
        if name.startswith("test_") and callable(func)
    ]

    passed = failed = 0
    for name, func in tests:
        try:
            func()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    _cleanup()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run_all())
