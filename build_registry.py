"""build_registry.py — Scan agents/ and generate the complete registry system.

Produces:
    system/agent_registry.json        — per-agent metadata + actions
    system/action_registry.json       — flat action→agent lookup
    system/agent_capabilities.json    — capability matrix
    system/planner_context.json       — LLM-planner-optimised metadata
    system/generated_docs/            — one Markdown file per agent

Run from the project root:

    python build_registry.py

Re-run any time a new agent is added or an existing one changes.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
AGENTS_DIR = PROJECT_ROOT / "agents"
SYSTEM_DIR = PROJECT_ROOT / "system"
DOCS_DIR = SYSTEM_DIR / "generated_docs"

# ── keyword / use-case catalogue (keyed by agent name) ─────────────────────
_AGENT_META: dict[str, dict[str, Any]] = {
    "gmail_agent": {
        "keywords": [
            "email", "gmail", "inbox", "mail", "unread", "sender",
            "subject", "attachment", "draft", "starred", "sent",
        ],
        "suggested_use_cases": [
            "Check for unread emails",
            "Search emails by sender or subject",
            "Get email count matching a query",
            "Retrieve email details including body and attachments",
            "List starred or important emails",
            "Search emails within a date range",
        ],
        "avoid_use_cases": [
            "Sending or composing emails",
            "Deleting or modifying emails",
            "Managing Gmail labels or filters",
            "Calendar operations",
        ],
    },
    "news_agent": {
        "keywords": [
            "news", "headlines", "article", "journalism", "press",
            "breaking", "current events", "media", "trending news",
        ],
        "suggested_use_cases": [
            "Get top headlines for a country or category",
            "Search news articles by keyword",
            "Compare news across multiple topics",
            "Find news from a specific source",
            "Get news within a date range",
        ],
        "avoid_use_cases": [
            "Social media posts or tweets",
            "Blog or forum content",
            "Historical news older than 30 days (API limit)",
            "Real-time stock or financial data",
        ],
    },
    "weather_agent": {
        "keywords": [
            "weather", "temperature", "forecast", "rain", "humidity",
            "wind", "climate", "sunny", "cloudy", "storm",
        ],
        "suggested_use_cases": [
            "Get current weather for a location",
            "Get hourly or daily forecast",
            "Compare weather across multiple cities",
            "Look up weather by coordinates",
            "Check tomorrow's weather",
        ],
        "avoid_use_cases": [
            "Historical weather data (beyond 16-day window)",
            "Air quality or pollution data",
            "Climate change analysis",
            "Weather alerts or warnings",
        ],
    },
    "file_agent": {
        "keywords": [
            "file", "folder", "directory", "document", "pdf", "excel",
            "word", "powerpoint", "read", "list", "search", "disk",
        ],
        "suggested_use_cases": [
            "List files and folders in a directory",
            "Read text files, PDFs, Excel, Word, or PowerPoint",
            "Search for files by name pattern",
            "Get file metadata (size, dates)",
            "Read multiple files at once",
        ],
        "avoid_use_cases": [
            "Writing, creating, or modifying files",
            "Deleting files or directories",
            "Renaming or moving files",
            "Accessing network drives or cloud storage",
        ],
    },
    "todo_agent": {
        "keywords": [
            "todo", "task", "checklist", "reminder", "pending",
            "completed", "to-do", "task list", "action item",
        ],
        "suggested_use_cases": [
            "Add, update, complete, or delete todos",
            "List all, pending, or completed todos",
            "Search todos by keyword or tag",
            "Bulk add or complete multiple todos",
            "Get todo statistics",
        ],
        "avoid_use_cases": [
            "Calendar scheduling or recurring events",
            "Project management with dependencies",
            "Time tracking or pomodoro",
            "Team task assignment",
        ],
    },
    "browser_agent": {
        "keywords": [
            "search", "web", "browse", "url", "website", "internet",
            "google", "duckduckgo", "crawl", "scrape", "link",
        ],
        "suggested_use_cases": [
            "Search the web via DuckDuckGo",
            "Fetch and extract text from a webpage",
            "Extract links or images from a page",
            "Crawl a website's pages",
            "Check if a URL is reachable",
            "Research a topic across multiple queries",
        ],
        "avoid_use_cases": [
            "Interacting with web apps (login, forms)",
            "Downloading large files",
            "Accessing paywalled content",
            "JavaScript-rendered single-page apps",
        ],
    },
    "project_tracker_agent": {
        "keywords": [
            "project", "milestone", "meeting", "decision", "risk",
            "progress", "tracker", "note", "knowledge base",
        ],
        "suggested_use_cases": [
            "Create and manage projects with notes, todos, milestones",
            "Record meetings, decisions, and risks",
            "Track project progress with updates",
            "Search across all projects",
            "Get a project dashboard summary",
        ],
        "avoid_use_cases": [
            "Gantt charts or timeline visualisation",
            "Resource allocation or budgeting",
            "Integration with Jira, Linear, or GitHub Issues",
            "Real-time collaboration",
        ],
    },
    "youtube_agent": {
        "keywords": [
            "youtube", "video", "channel", "playlist", "watch",
            "stream", "tutorial", "trending", "play",
        ],
        "suggested_use_cases": [
            "Search YouTube for videos",
            "Get video details (title, duration, views)",
            "Open a video in the browser",
            "List videos from a channel or playlist",
            "Get trending videos by country",
        ],
        "avoid_use_cases": [
            "Downloading video files",
            "Uploading or publishing videos",
            "Managing YouTube accounts",
            "Accessing private or age-restricted videos",
        ],
    },
    "notes_generator_agent": {
        "keywords": [
            "notes", "generate", "study", "exam", "presentation",
            "report", "document", "summary", "lecture", "academic",
        ],
        "suggested_use_cases": [
            "Generate comprehensive study notes on any topic",
            "Create exam preparation materials",
            "Generate presentations (PPTX)",
            "Create professional reports",
            "Generate notes from a source file (PDF, DOCX)",
        ],
        "avoid_use_cases": [
            "Real-time note-taking or transcription",
            "Collaborative document editing",
            "Plagiarism-checked academic papers",
            "Generating code or software",
        ],
    },
    "memory_agent": {
        "keywords": [
            "memory", "remember", "recall", "store", "history", "past",
            "context", "archive", "summary", "conversation", "forget"
        ],
        "suggested_use_cases": [
            "Store information for long-term recall",
            "Search past conversations or stored memories",
            "Retrieve specific memory details",
            "Update or delete existing memories",
            "Archive the current chat and start fresh",
            "Create a summary of the current conversation"
        ],
        "avoid_use_cases": [
            "Storing large files or documents",
            "Acting as a general-purpose database"
        ],
    },
}

# ── optional params per action (supplement _REQUIRED_PARAMS) ───────────────
_OPTIONAL_PARAMS: dict[str, dict[str, list[str]]] = {
    "gmail_agent": {
        "get_latest_emails": ["limit"],
        "get_unread_emails": ["limit"],
        "search_sender": ["limit"],
        "search_subject": ["limit"],
        "search_date_range": ["limit"],
        "search_gmail_query": ["limit"],
        "get_attachments": ["limit"],
        "get_starred_emails": ["limit"],
        "get_sent_emails": ["limit"],
        "get_important_emails": ["limit"],
        "get_drafts": ["limit"],
    },
    "news_agent": {
        "top_headlines": ["country", "category", "limit"],
        "search_news": ["sort_by", "language", "limit"],
        "search_multiple_topics": ["limit_per_topic"],
        "search_multiple_queries": ["limit"],
        "get_latest_news": ["country", "limit"],
        "get_category_news": ["country", "limit"],
        "get_source_news": ["limit"],
        "get_sources": ["category", "language", "country"],
        "search_date_range": ["from_date", "to_date", "sort_by", "language", "limit"],
        "search_combined": ["topics", "categories", "sources", "country", "limit"],
    },
    "weather_agent": {
        "hourly_forecast": ["hours"],
        "daily_forecast": ["days"],
        "weather_next_days": ["days"],
        "get_trending": ["country", "limit"],
    },
    "file_agent": {
        "list_directory_recursive": ["max_depth"],
        "get_folder_tree": ["max_depth"],
        "get_recent_files": ["limit"],
        "read_folder_contents": ["limit"],
    },
    "todo_agent": {
        "add_todo": ["description", "tags", "metadata"],
        "update_todo": ["title", "description", "tags", "metadata"],
    },
    "browser_agent": {
        "web_search": ["max_results"],
        "multi_search": ["max_results"],
        "crawl_website": ["max_pages"],
        "research_bundle": ["max_results_per_query", "fetch_top_pages"],
    },
    "youtube_agent": {
        "search_videos": ["limit"],
        "search_multiple": ["limit"],
        "get_video_details": ["video_url", "video_id"],
        "play_video": ["video_url", "video_id"],
        "get_channel_videos": ["limit"],
        "get_trending": ["country", "limit"],
        "get_playlist_videos": ["limit"],
        "search_bundle": ["limit"],
    },
    "notes_generator_agent": {
        "generate_notes": ["pages", "word_count", "difficulty", "audience",
                           "output_format", "structure", "academic_mode", "model"],
        "generate_exam_notes": ["pages", "word_count", "difficulty", "audience",
                                "output_format", "model"],
        "generate_detailed_notes": ["pages", "word_count", "difficulty", "audience",
                                    "output_format", "model"],
        "generate_short_notes": ["pages", "word_count", "difficulty", "audience",
                                 "output_format", "model"],
        "generate_presentation": ["slides", "difficulty", "audience", "model"],
        "generate_report": ["pages", "word_count", "difficulty", "audience",
                            "output_format", "model"],
        "generate_from_structure": ["pages", "word_count", "difficulty", "audience",
                                    "output_format", "model"],
        "generate_from_prompt": ["topic", "word_count", "output_format", "model"],
        "generate_from_file": ["source_path", "topic", "pages", "word_count",
                               "difficulty", "audience", "output_format", "model"],
    },
    "project_tracker_agent": {
        "create_project": ["description", "metadata"],
        "update_project": ["project_name", "description", "status", "metadata"],
        "add_note": ["project_name", "content"],
        "update_note": ["project_name", "title", "content"],
        "add_todo": ["project_name", "description", "tags"],
        "update_todo": ["project_name", "title", "description", "tags"],
        "add_milestone": ["project_name", "description", "due_date"],
        "update_milestone": ["project_name", "title", "description", "due_date"],
        "add_meeting": ["project_name", "date", "attendees", "agenda", "notes", "action_items"],
        "update_meeting": ["project_name", "title", "date", "agenda", "notes", "attendees", "action_items"],
        "add_decision": ["project_name", "rationale", "decided_by", "date"],
        "add_risk": ["project_name", "description", "severity", "mitigation"],
        "update_risk": ["project_name", "title", "description", "severity", "mitigation"],
        "add_link": ["project_name", "title", "description"],
        "add_file_reference": ["project_name", "name", "description"],
        "add_progress_update": ["project_name", "author"],
        "get_project": ["project_name"],
        "get_project_dashboard": ["project_name"],
        "list_todos": ["project_name"],
        "list_notes": ["project_name"],
        "list_milestones": ["project_name"],
        "list_meetings": ["project_name"],
        "list_decisions": ["project_name"],
        "list_risks": ["project_name"],
        "list_links": ["project_name"],
        "list_files": ["project_name"],
        "list_progress_updates": ["project_name"],
    },
}

# ── example I/O per action ─────────────────────────────────────────────────
_EXAMPLES: dict[str, dict[str, dict[str, Any]]] = {
    "gmail_agent": {
        "get_latest_emails": {
            "input": {"action": "get_latest_emails", "parameters": {"limit": 5}},
            "output_summary": "List of 5 most recent inbox emails with id, from, to, subject, date, snippet",
        },
        "search_sender": {
            "input": {"action": "search_sender", "parameters": {"sender": "boss@company.com", "limit": 10}},
            "output_summary": "List of emails from the specified sender",
        },
    },
    "news_agent": {
        "top_headlines": {
            "input": {"action": "top_headlines", "parameters": {"country": "us", "category": "technology"}},
            "output_summary": "List of top technology headlines in the US",
        },
        "search_news": {
            "input": {"action": "search_news", "parameters": {"query": "artificial intelligence", "limit": 5}},
            "output_summary": "List of news articles matching the query",
        },
    },
    "weather_agent": {
        "current_weather": {
            "input": {"action": "current_weather", "parameters": {"location": "Bangalore"}},
            "output_summary": "Current temperature, humidity, wind, weather description for Bangalore",
        },
        "daily_forecast": {
            "input": {"action": "daily_forecast", "parameters": {"location": "London", "days": 7}},
            "output_summary": "7-day forecast with daily high/low temperatures and conditions",
        },
    },
    "file_agent": {
        "list_directory": {
            "input": {"action": "list_directory", "parameters": {"path": "C:/Users/Documents"}},
            "output_summary": "Lists of folders and files with metadata in the directory",
        },
        "read_text_file": {
            "input": {"action": "read_text_file", "parameters": {"path": "README.md"}},
            "output_summary": "The text content of the file",
        },
    },
    "todo_agent": {
        "add_todo": {
            "input": {"action": "add_todo", "parameters": {"title": "Buy groceries", "tags": ["shopping"]}},
            "output_summary": "The newly created todo with generated id and timestamps",
        },
        "list_pending_todos": {
            "input": {"action": "list_pending_todos", "parameters": {}},
            "output_summary": "List of all todos with status 'pending'",
        },
    },
    "browser_agent": {
        "web_search": {
            "input": {"action": "web_search", "parameters": {"query": "best Python frameworks 2025"}},
            "output_summary": "List of search results with title, url, and snippet",
        },
        "fetch_page": {
            "input": {"action": "fetch_page", "parameters": {"url": "https://example.com"}},
            "output_summary": "Page title, extracted text, HTML, links, and images",
        },
    },
    "project_tracker_agent": {
        "create_project": {
            "input": {"action": "create_project", "parameters": {"project_name": "MAYA AI Assistant"}},
            "output_summary": "The newly created project with generated id and empty sub-collections",
        },
        "get_project_dashboard": {
            "input": {"action": "get_project_dashboard", "parameters": {"project_id": "<uuid>"}},
            "output_summary": "Summary counts: todos, milestones, risks, notes, meetings, etc.",
        },
    },
    "youtube_agent": {
        "search_videos": {
            "input": {"action": "search_videos", "parameters": {"query": "Python tutorial", "limit": 5}},
            "output_summary": "List of videos with title, channel, duration, view_count, url, thumbnail",
        },
        "play_video": {
            "input": {"action": "play_video", "parameters": {"video_id": "dQw4w9WgXcQ"}},
            "output_summary": "Opens the video in the default browser and returns video metadata",
        },
    },
    "notes_generator_agent": {
        "generate_notes": {
            "input": {"action": "generate_notes", "parameters": {"topic": "Docker Containers", "pages": 10}},
            "output_summary": "Generated notes file path, word count, and page count",
        },
        "generate_presentation": {
            "input": {"action": "generate_presentation", "parameters": {"topic": "Machine Learning Basics", "slides": 15}},
            "output_summary": "Generated PPTX file path with requested number of slides",
        },
    },
}


# ── agent loader ───────────────────────────────────────────────────────────
def _load_agent_module(path: Path) -> Any:
    """Import an agent module by file path without executing its CLI."""
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def _discover_agents() -> list[dict[str, Any]]:
    """Scan agents/ and extract metadata from each agent module."""
    agents: list[dict[str, Any]] = []

    for py_file in sorted(AGENTS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            module = _load_agent_module(py_file)
        except Exception as exc:
            print(f"  WARN: could not import {py_file.name}: {exc}")
            continue

        plugin_info = getattr(module, "PLUGIN_INFO", None)
        if plugin_info is None:
            print(f"  SKIP: {py_file.name} has no PLUGIN_INFO")
            continue

        actions_dict = getattr(module, "_ACTIONS", {})
        required_params = getattr(module, "_REQUIRED_PARAMS", {})
        agent_name = plugin_info.get("name", py_file.stem)

        optional_params = _OPTIONAL_PARAMS.get(agent_name, {})
        extra_meta = _AGENT_META.get(agent_name, {})
        examples = _EXAMPLES.get(agent_name, {})

        action_list: list[dict[str, Any]] = []
        for action_name in sorted(actions_dict.keys()):
            handler = actions_dict[action_name]
            doc = (handler.__doc__ or "").strip().split("\n")[0]

            action_entry: dict[str, Any] = {
                "name": action_name,
                "description": doc,
                "required_params": required_params.get(action_name, []),
                "optional_params": optional_params.get(action_name, []),
            }

            if action_name in examples:
                action_entry["example_input"] = examples[action_name]["input"]
                action_entry["example_output_summary"] = examples[action_name]["output_summary"]

            action_list.append(action_entry)

        agent_entry: dict[str, Any] = {
            "name": agent_name,
            "agent_name": plugin_info.get("agent_name", agent_name),
            "version": plugin_info.get("version", "0.0.0"),
            "type": plugin_info.get("type", "tool"),
            "description": plugin_info.get("description", ""),
            "input_format": plugin_info.get("input_format", "json"),
            "output_format": plugin_info.get("output_format", "json"),
            "entrypoint": plugin_info.get("entrypoint", "execute"),
            "file": py_file.name,
            "action_count": len(action_list),
            "actions": action_list,
            "keywords": extra_meta.get("keywords", []),
            "suggested_use_cases": extra_meta.get("suggested_use_cases", []),
            "avoid_use_cases": extra_meta.get("avoid_use_cases", []),
        }
        agents.append(agent_entry)
        print(f"  OK: {agent_name} ({len(action_list)} actions)")

    return agents


# ── generators ─────────────────────────────────────────────────────────────
def _build_agent_registry(agents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "agent_count": len(agents),
        "agents": agents,
    }


def _build_action_registry(agents: list[dict[str, Any]]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for agent in agents:
        for action in agent["actions"]:
            actions.append({
                "action": action["name"],
                "agent": agent["name"],
                "agent_class": agent["agent_name"],
                "description": action["description"],
                "required_params": action["required_params"],
                "optional_params": action["optional_params"],
            })
    return {
        "version": "1.0.0",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_actions": len(actions),
        "actions": actions,
    }


def _build_capabilities(agents: list[dict[str, Any]]) -> dict[str, Any]:
    capabilities: list[dict[str, Any]] = []
    for agent in agents:
        capabilities.append({
            "agent": agent["name"],
            "agent_class": agent["agent_name"],
            "type": agent["type"],
            "action_count": agent["action_count"],
            "actions": [a["name"] for a in agent["actions"]],
            "keywords": agent["keywords"],
            "suggested_use_cases": agent["suggested_use_cases"],
            "avoid_use_cases": agent["avoid_use_cases"],
        })
    return {
        "version": "1.0.0",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "agent_count": len(capabilities),
        "capabilities": capabilities,
    }


def _build_planner_context(agents: list[dict[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for agent in agents:
        compact_actions: list[dict[str, Any]] = []
        for action in agent["actions"]:
            entry: dict[str, Any] = {
                "name": action["name"],
                "required_params": action["required_params"],
            }
            if action["optional_params"]:
                entry["optional_params"] = action["optional_params"]
            if action["description"]:
                entry["description"] = action["description"]
            compact_actions.append(entry)

        entries.append({
            "agent": agent["name"],
            "purpose": agent["description"],
            "type": agent["type"],
            "keywords": agent["keywords"],
            "actions": compact_actions,
        })
    return {
        "version": "1.0.0",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "instruction": (
            "Use this context to decide which agent and action to invoke. "
            "Match user intent against keywords, then select the action whose "
            "required_params you can fill from the user's request. "
            "For project_tracker_agent: you can pass 'project_name' instead of "
            "'project_id' — the agent will resolve the name to an ID automatically."
        ),
        "agents": entries,
    }


def _generate_agent_doc(agent: dict[str, Any]) -> str:
    """Generate a Markdown documentation file for one agent."""
    lines: list[str] = []
    lines.append(f"# {agent['agent_name']}")
    lines.append("")
    lines.append(f"**Module:** `{agent['file']}`  ")
    lines.append(f"**Version:** {agent['version']}  ")
    lines.append(f"**Type:** {agent['type']}  ")
    lines.append(f"**Entrypoint:** `{agent['entrypoint']}`  ")
    lines.append("")

    if agent["description"]:
        lines.append(f"## Purpose")
        lines.append("")
        lines.append(agent["description"])
        lines.append("")

    if agent["keywords"]:
        lines.append("## Keywords")
        lines.append("")
        lines.append(", ".join(f"`{kw}`" for kw in agent["keywords"]))
        lines.append("")

    if agent["suggested_use_cases"]:
        lines.append("## Suggested Use Cases")
        lines.append("")
        for uc in agent["suggested_use_cases"]:
            lines.append(f"- {uc}")
        lines.append("")

    if agent["avoid_use_cases"]:
        lines.append("## Avoid Use Cases")
        lines.append("")
        for uc in agent["avoid_use_cases"]:
            lines.append(f"- {uc}")
        lines.append("")

    lines.append(f"## Actions ({agent['action_count']})")
    lines.append("")

    for action in agent["actions"]:
        lines.append(f"### `{action['name']}`")
        lines.append("")
        if action["description"]:
            lines.append(action["description"])
            lines.append("")

        if action["required_params"]:
            lines.append("**Required parameters:**")
            lines.append("")
            for p in action["required_params"]:
                lines.append(f"- `{p}`")
            lines.append("")

        if action["optional_params"]:
            lines.append("**Optional parameters:**")
            lines.append("")
            for p in action["optional_params"]:
                lines.append(f"- `{p}`")
            lines.append("")

        if "example_input" in action:
            lines.append("**Example input:**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(action["example_input"], indent=2))
            lines.append("```")
            lines.append("")

        if "example_output_summary" in action:
            lines.append(f"**Example output:** {action['example_output_summary']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  wrote {path.relative_to(PROJECT_ROOT)}")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(PROJECT_ROOT)}")


# ── validation ─────────────────────────────────────────────────────────────
def _validate(agents: list[dict[str, Any]]) -> list[str]:
    """Return a list of validation warnings (empty = all good)."""
    warnings: list[str] = []

    for agent in agents:
        if not agent["description"]:
            warnings.append(f"{agent['name']}: missing description in PLUGIN_INFO")
        if not agent["keywords"]:
            warnings.append(f"{agent['name']}: no keywords defined")
        if agent["action_count"] == 0:
            warnings.append(f"{agent['name']}: no actions discovered")
        for action in agent["actions"]:
            if not action["description"]:
                warnings.append(f"{agent['name']}.{action['name']}: missing docstring")

    return warnings


# ── main ───────────────────────────────────────────────────────────────────
def main() -> int:
    print("build_registry: scanning agents/\n")

    if not AGENTS_DIR.is_dir():
        print(f"ERROR: agents/ directory not found at {AGENTS_DIR}")
        return 1

    agents = _discover_agents()

    if not agents:
        print("\nERROR: no agents discovered")
        return 1

    print(f"\nDiscovered {len(agents)} agents, generating registry files...\n")

    agent_registry = _build_agent_registry(agents)
    action_registry = _build_action_registry(agents)
    capabilities = _build_capabilities(agents)
    planner_context = _build_planner_context(agents)

    _write_json(SYSTEM_DIR / "agent_registry.json", agent_registry)
    _write_json(SYSTEM_DIR / "action_registry.json", action_registry)
    _write_json(SYSTEM_DIR / "agent_capabilities.json", capabilities)
    _write_json(SYSTEM_DIR / "planner_context.json", planner_context)

    print()
    for agent in agents:
        doc = _generate_agent_doc(agent)
        doc_path = DOCS_DIR / f"{agent['name']}.md"
        _write_text(doc_path, doc)

    warnings = _validate(agents)
    if warnings:
        print(f"\nValidation warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("\nValidation: all checks passed")

    total_actions = sum(a["action_count"] for a in agents)
    print(f"\nDone. {len(agents)} agents, {total_actions} actions registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
