"""LLM client with fallback chain for Maya Code Agent.

Tries MODEL_PRIMARY → MODEL_FALLBACK → MODEL_FALLBACK_2 in order.
Every call returns both the parsed result and which model served it.

Designed to be robust with smaller / weaker models (gemma, kimi, etc.):
- Fuzzy JSON extraction from messy LLM output
- Tool name normalization (maps "read" → "read_file", etc.)
- JSON repair for common mistakes (trailing commas, single quotes)
- Fallback to non-JSON mode when format="json" fails
"""

from __future__ import annotations

import json
import re
import traceback
from typing import Any, Optional, Type, TypeVar

import ollama
from pydantic import BaseModel, ValidationError

from agents.maya_code import config

T = TypeVar("T", bound=BaseModel)

_MODEL_CHAIN: tuple[str, ...] = (
    config.MODEL_PRIMARY,
    config.MODEL_FALLBACK,
    config.MODEL_FALLBACK_2,
)

# ── Tool name aliases (smaller models use short/wrong names) ─────────────────

_TOOL_NAME_ALIASES: dict[str, str] = {
    "read": "read_file",
    "readfile": "read_file",
    "read_files": "read_file",
    "cat": "read_file",
    "open": "read_file",
    "view": "read_file",
    "write": "write_file",
    "writefile": "write_file",
    "create": "write_file",
    "create_file": "write_file",
    "new_file": "write_file",
    "edit": "edit_file",
    "editfile": "edit_file",
    "modify": "edit_file",
    "modify_file": "edit_file",
    "replace": "edit_file",
    "patch": "edit_file",
    "run": "run_cmd",
    "runcmd": "run_cmd",
    "exec": "run_cmd",
    "execute": "run_cmd",
    "command": "run_cmd",
    "shell": "run_cmd",
    "cmd": "run_cmd",
    "search": "search_code",
    "searchcode": "search_code",
    "grep": "search_code",
    "find": "search_code",
    "find_code": "search_code",
    "list": "list_files",
    "listfiles": "list_files",
    "ls": "list_files",
    "dir": "list_files",
    "test": "run_tests",
    "runtests": "run_tests",
    "tests": "run_tests",
    "finish": "done",
    "complete": "done",
    "completed": "done",
    "end": "done",
    "stop": "done",
}


def _normalize_tool_name(name: str) -> str:
    """Map common LLM aliases to canonical tool names."""
    clean = name.strip().lower().replace("-", "_").replace(" ", "_")
    return _TOOL_NAME_ALIASES.get(clean, clean)


def _repair_json(raw: str) -> str:
    """Fix common JSON mistakes from smaller models."""
    # Remove trailing commas before } or ]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    # Replace single quotes with double quotes (but not inside strings)
    if "'" in raw and '"' not in raw:
        raw = raw.replace("'", '"')
    # Fix unquoted keys: {tool: "read_file"} → {"tool": "read_file"}
    raw = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', raw)
    # Remove comments (// style)
    raw = re.sub(r'//[^\n]*', '', raw)
    # Fix True/False/None → true/false/null
    raw = raw.replace(": True", ": true").replace(": False", ": false").replace(": None", ": null")
    return raw


def _normalize_data(data: dict, schema: Type) -> dict:
    """Normalize parsed JSON to match expected schema before validation."""
    # Normalize tool names in ToolCall-like objects
    if "tool" in data and isinstance(data["tool"], str):
        data["tool"] = _normalize_tool_name(data["tool"])

    # Some models put tool name in "action" or "name" instead of "tool"
    if "tool" not in data:
        for alt_key in ("action", "name", "tool_name", "function", "type"):
            if alt_key in data and isinstance(data[alt_key], str):
                data["tool"] = _normalize_tool_name(data[alt_key])
                break

    # Some models put args in "parameters", "input", "arguments", "params"
    if "args" not in data:
        for alt_key in ("parameters", "input", "arguments", "params", "inputs"):
            if alt_key in data and isinstance(data[alt_key], dict):
                data["args"] = data[alt_key]
                break

    # Some models forget "args" entirely but put path/content at top level
    if "args" not in data and "tool" in data:
        known_top = {"tool", "reasoning", "args", "action", "name", "tool_name",
                      "function", "type", "parameters", "input", "arguments", "params", "inputs"}
        extra = {k: v for k, v in data.items() if k not in known_top}
        if extra:
            data["args"] = extra

    # Normalize "reason" → "reasoning"
    if "reasoning" not in data and "reason" in data:
        data["reasoning"] = data["reason"]
    if "reasoning" not in data and "thought" in data:
        data["reasoning"] = data["thought"]
    if "reasoning" not in data and "thinking" in data:
        data["reasoning"] = data["thinking"]

    # Normalize subtask decomposition responses
    if "subtasks" in data and isinstance(data["subtasks"], list):
        for st in data["subtasks"]:
            if isinstance(st, dict):
                # Normalize "dependencies" → "depends_on"
                if "depends_on" not in st:
                    for alt in ("dependencies", "deps", "requires", "after"):
                        if alt in st and isinstance(st[alt], list):
                            st["depends_on"] = st[alt]
                            break
                # Ensure depends_on is always a list
                if "depends_on" in st and not isinstance(st["depends_on"], list):
                    st["depends_on"] = [st["depends_on"]] if st["depends_on"] else []

    return data


def _extract_json(raw: str) -> str:
    """Pull a JSON object from LLM output that may include markdown fences."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    start = raw.find("{")
    if start == -1:
        start = raw.find("[")
        if start == -1:
            return raw

    decoder = json.JSONDecoder()
    try:
        _, end_idx = decoder.raw_decode(raw, start)
        return raw[start:end_idx]
    except (json.JSONDecodeError, ValueError):
        pass

    depth = 0
    end = start
    opener = raw[start]
    closer = "}" if opener == "{" else "]"
    for i in range(start, len(raw)):
        if raw[i] == opener:
            depth += 1
        elif raw[i] == closer:
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return raw[start:end]


def _try_parse(raw: str, schema: Type[T]) -> T:
    """Extract JSON from raw text, repair, normalize, and validate against schema."""
    json_str = _extract_json(raw)

    # Try direct parse first
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try with repairs
        repaired = _repair_json(json_str)
        data = json.loads(repaired)

    if isinstance(data, dict):
        data = _normalize_data(data, schema)

    return schema.model_validate(data)


def call_llm_structured(
    system_prompt: str,
    user_prompt: str,
    schema: Type[T],
    *,
    temperature: Optional[float] = None,
) -> tuple[T, str]:
    """Call the LLM chain and parse the response into *schema*.

    Returns ``(parsed_object, model_name_used)``.
    Raises ``LLMError`` if all models and reparse attempts fail.

    Robust with smaller models: tries format="json" first, falls back to
    free-form if the model doesn't support it. Applies JSON repair,
    tool name normalization, and field name aliasing.
    """
    temp = temperature if temperature is not None else config.LLM_TEMPERATURE
    errors: list[str] = []

    for model in _MODEL_CHAIN:
        for attempt in range(config.MAX_REPARSE_ATTEMPTS):
            # Try with format="json" on first attempt, without on retry
            use_json_format = (attempt == 0)
            try:
                client_kwargs: dict[str, Any] = {"host": config.OLLAMA_BASE_URL}
                if config.OLLAMA_API_KEY:
                    client_kwargs["headers"] = {"Authorization": f"Bearer {config.OLLAMA_API_KEY}"}
                client = ollama.Client(**client_kwargs)
                chat_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "options": {
                        "temperature": temp,
                        "num_ctx": config.LLM_NUM_CTX,
                    },
                }
                if use_json_format:
                    chat_kwargs["format"] = "json"

                response = client.chat(**chat_kwargs)
                raw = response.message.content or ""
                parsed = _try_parse(raw, schema)
                return parsed, model

            except (json.JSONDecodeError, ValidationError) as exc:
                errors.append(f"{model} attempt {attempt}: parse/validation — {exc}")
                continue

            except Exception as exc:
                errors.append(f"{model} attempt {attempt}: {type(exc).__name__} — {exc}")
                break  # move to next model on connection/timeout errors

    raise LLMError(
        f"All models failed after {len(errors)} attempts:\n"
        + "\n".join(errors[-6:])
    )


def call_llm_raw(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: Optional[float] = None,
) -> tuple[str, str]:
    """Call the LLM chain and return raw text (no schema parsing).

    Returns ``(raw_text, model_name_used)``.
    """
    temp = temperature if temperature is not None else config.LLM_TEMPERATURE
    errors: list[str] = []

    for model in _MODEL_CHAIN:
        try:
            client_kwargs = {"host": config.OLLAMA_BASE_URL}
            if config.OLLAMA_API_KEY:
                client_kwargs["headers"] = {"Authorization": f"Bearer {config.OLLAMA_API_KEY}"}
            client = ollama.Client(**client_kwargs)
            response = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={
                    "temperature": temp,
                    "num_ctx": config.LLM_NUM_CTX,
                },
            )
            raw = response.message.content or ""
            if raw.strip():
                return raw.strip(), model
            errors.append(f"{model}: empty response")

        except Exception as exc:
            errors.append(f"{model}: {type(exc).__name__} — {exc}")

    raise LLMError(
        f"All models failed:\n" + "\n".join(errors[-6:])
    )


class LLMError(Exception):
    """Raised when all models in the chain fail."""
