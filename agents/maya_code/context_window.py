"""v2 Context Window — assembles LLM prompts for each agentic loop iteration.

Manages what the LLM sees: goal, subtask, tool definitions, relevant file
contents, and recent action history.  Older actions are summarized to stay
within the character budget.
"""

from __future__ import annotations

from agents.maya_code import config
from agents.maya_code.contracts import (
    ActionRecord,
    ParsedGoal,
    Subtask,
    ToolName,
)


# ── System prompt with tool definitions ──────────────────────────────────────

AGENTIC_SYSTEM_PROMPT = """\
You are a coding agent. Execute ONE tool per turn. Respond with ONLY JSON.

## Response Format
{"tool": "<name>", "args": {}, "reasoning": "why"}

## Tools

read_file    — Read a file: {"tool":"read_file","args":{"path":"src/app.js"},"reasoning":"need to see current code"}
write_file   — Create new file with FULL content: {"tool":"write_file","args":{"path":"src/app.js","content":"...all code..."},"reasoning":"creating main file"}
edit_file    — Search/replace in file (search must be unique): {"tool":"edit_file","args":{"path":"src/app.js","search":"old code","replace":"new code"},"reasoning":"fixing bug"}
run_cmd      — Run shell command: {"tool":"run_cmd","args":{"command":"npm install"},"reasoning":"installing deps"}
search_code  — Search pattern in files: {"tool":"search_code","args":{"pattern":"functionName","glob":"*.js"},"reasoning":"finding usage"}
list_files   — List directory: {"tool":"list_files","args":{"path":"src"},"reasoning":"seeing structure"}
run_tests    — Run tests: {"tool":"run_tests","args":{"command":"pytest"},"reasoning":"checking correctness"}
done         — Subtask finished: {"tool":"done","args":{"summary":"Created login page with form validation"},"reasoning":"all files created"}

## Rules
- ONE tool per response. JSON only. No extra text.
- write_file: put ALL content in one call. Do NOT create skeleton then edit.
- edit_file: read the file FIRST. Do NOT edit same file more than 3 times in a row.
- Call done as soon as core work is finished. Do NOT polish or optimize.
- Every action costs budget. Be minimal.
"""


def assemble_context(
    parsed_goal: ParsedGoal,
    subtask: Subtask,
    file_cache: dict[str, str],
    action_history: list[ActionRecord],
    analysis_text: str = "",
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for one iteration of the agentic loop.

    Returns a pair of strings ready to pass to ``call_llm_structured``.
    Enforces the character budget from config.
    """
    # Scale context budget based on LLM context window setting
    # Smaller models (4k-8k ctx) get proportionally less context
    ctx_ratio = min(config.LLM_NUM_CTX / 16384, 1.0)
    budget = int(config.V2_CONTEXT_WINDOW_CHARS * max(ctx_ratio, 0.4))
    system = AGENTIC_SYSTEM_PROMPT
    budget -= len(system)

    sections: list[str] = []

    # 1. Goal + subtask (always included, high priority)
    remaining = subtask.action_budget - subtask.actions_used
    budget_pct = subtask.actions_used / max(subtask.action_budget, 1)

    goal_section = (
        f"## Goal\n{parsed_goal.refined or parsed_goal.raw}\n\n"
        f"## Current Subtask: {subtask.title}\n{subtask.description}\n"
        f"Budget: {subtask.actions_used}/{subtask.action_budget} actions used ({remaining} remaining)"
    )

    if budget_pct >= 0.85:
        goal_section += (
            "\n\n⚠️ CRITICAL: You are almost out of actions! "
            "You MUST call `done` NOW with a summary of what you accomplished. "
            "Do NOT attempt any more edits. Call `done` immediately."
        )
    elif budget_pct >= 0.7:
        goal_section += (
            "\n\n⚠️ WARNING: Budget is running low. "
            "Finish your current work and call `done` within the next 2-3 actions. "
            "Focus only on what's essential — skip polish and optimization."
        )

    if parsed_goal.acceptance_criteria:
        goal_section += "\n\nAcceptance criteria:\n" + "\n".join(
            f"- {c}" for c in parsed_goal.acceptance_criteria
        )
    sections.append(goal_section)
    budget -= len(goal_section)

    # 2. Project analysis (compressed)
    if analysis_text and budget > 2000:
        trimmed = analysis_text[:2000]
        sections.append(f"## Project Overview\n{trimmed}")
        budget -= len(trimmed) + 20

    # 3. Recent action history (full for recent, summarized for older)
    if action_history:
        history_section = _build_history(action_history, budget // 3)
        sections.append(history_section)
        budget -= len(history_section)

    # 4. Relevant file contents from cache (fill remaining budget)
    if file_cache and budget > 500:
        files_section = _build_file_context(
            file_cache, subtask.relevant_files, action_history, budget
        )
        if files_section:
            sections.append(files_section)

    user_prompt = "\n\n".join(sections)
    user_prompt += "\n\nWhat is your next action? Respond with JSON only."

    return system, user_prompt


def _build_history(history: list[ActionRecord], budget: int) -> str:
    """Build action history section, summarizing older entries."""
    lines: list[str] = []
    keep_full = config.V2_ACTION_HISTORY_KEEP
    total = len(history)

    # Older entries get summarized
    if total > keep_full:
        old = history[: total - keep_full]
        for rec in old:
            lines.append(summarize_action(rec))

    # Recent entries get full detail
    recent = history[-keep_full:] if total > keep_full else history
    for rec in recent:
        status = "OK" if rec.tool_result.success else "FAILED"
        line = f"[{rec.iteration}] {rec.tool_call.tool.value}("
        args_short = ", ".join(
            f"{k}={_truncate(str(v), 80)}" for k, v in rec.tool_call.args.items()
        )
        line += f"{args_short}) → {status}"
        if rec.tool_result.error:
            line += f" — {rec.tool_result.error[:200]}"
        elif rec.tool_result.output:
            line += f"\n  Output: {_truncate(rec.tool_result.output, 300)}"
        lines.append(line)

    section = "## Action History\n" + "\n".join(lines)
    if len(section) > budget:
        section = section[:budget] + "\n... [history truncated]"
    return section


def _build_file_context(
    cache: dict[str, str],
    relevant_files: list[str],
    history: list[ActionRecord],
    budget: int,
) -> str:
    """Include file contents in priority order: recently read > relevant > others."""
    # Priority: files read in recent actions first, then relevant_files
    recently_read = []
    for rec in reversed(history):
        if rec.tool_call.tool == ToolName.READ_FILE:
            p = rec.tool_call.args.get("path", "")
            if p and p not in recently_read:
                recently_read.append(p)

    ordered: list[str] = []
    for f in recently_read:
        if f in cache and f not in ordered:
            ordered.append(f)
    for f in relevant_files:
        if f in cache and f not in ordered:
            ordered.append(f)
    for f in cache:
        if f not in ordered:
            ordered.append(f)

    parts: list[str] = []
    remaining = budget - 30
    for path in ordered:
        content = cache.get(path, "")
        header = f"### {path}\n```\n"
        footer = "\n```"
        entry_len = len(header) + len(footer) + min(len(content), remaining - 100)
        if entry_len > remaining:
            break
        trimmed = content[: remaining - len(header) - len(footer)]
        parts.append(f"{header}{trimmed}{footer}")
        remaining -= len(parts[-1])
        if remaining < 200:
            break

    if not parts:
        return ""
    return "## Files in Context\n" + "\n\n".join(parts)


def summarize_action(record: ActionRecord) -> str:
    """Compress an action record to a single line."""
    tool = record.tool_call.tool.value
    status = "OK" if record.tool_result.success else "FAIL"
    target = ""
    args = record.tool_call.args
    if "path" in args:
        target = f" {args['path']}"
    elif "command" in args:
        target = f" `{_truncate(args['command'], 40)}`"
    elif "pattern" in args:
        target = f" /{args['pattern']}/"

    return f"[{record.iteration}] {tool}{target} → {status}"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
