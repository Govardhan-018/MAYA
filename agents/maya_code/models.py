"""LLM client with fallback chain for Maya Code Agent.

Tries MODEL_PRIMARY → MODEL_FALLBACK → MODEL_FALLBACK_2 in order.
Every call returns both the parsed result and which model served it.
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
    """
    temp = temperature if temperature is not None else config.LLM_TEMPERATURE
    errors: list[str] = []

    for model in _MODEL_CHAIN:
        for attempt in range(config.MAX_REPARSE_ATTEMPTS):
            try:
                client = ollama.Client(host=config.OLLAMA_BASE_URL)
                response = client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    format="json",
                    options={
                        "temperature": temp,
                        "num_ctx": config.LLM_NUM_CTX,
                    },
                )
                raw = response.message.content or ""
                json_str = _extract_json(raw)
                data = json.loads(json_str)
                parsed = schema.model_validate(data)
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
            client = ollama.Client(host=config.OLLAMA_BASE_URL)
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
