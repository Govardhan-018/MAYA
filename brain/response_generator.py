"""Response generator — converts task results into natural conversation.

Uses the large response model (gpt-oss:120b) with cloud-first + local fallback.
For the no-agent path, passes through the planner's direct_response.
"""

from __future__ import annotations

import json
import textwrap
import traceback
from typing import Any, Optional

import ollama

from brain.schemas.plan_schema import TaskResult, TaskStatus
from brain.utils.config import (
    OLLAMA_BASE_URL,
    RESPONSE_LOCAL_FALLBACK,
    RESPONSE_MAX_RETRIES,
    RESPONSE_MODEL,
    RESPONSE_NUM_CTX,
    RESPONSE_TEMPERATURE,
)
from brain.utils.logger import log_brain


import os
_PERSONA = os.getenv("MAYA_PERSONA", "helpful, professional, and friendly")

_SYSTEM_PROMPT = textwrap.dedent(f"""\
You are MAYA, an AI voice assistant. Your personality is: {_PERSONA}
Always stay strictly in character and adjust your tone and vocabulary to match.

You are responding to a user who spoke a voice command. Your response will be
read aloud via text-to-speech.

RULES:
1. Be concise but informative — this is spoken output, not a document.
2. Summarise data naturally; do not dump raw JSON.
3. If some tasks failed, mention it briefly and focus on what succeeded.
4. Use a warm, conversational tone.
5. Do NOT use markdown formatting, bullet lists, or code blocks.
6. Do NOT mention internal details (task IDs, agent names, JSON).
7. If there are no results, say so honestly.
8. Keep your response under 200 words unless the data warrants more.
""")


def _build_prompt(
    command: str,
    results: list[TaskResult],
    conversation_context: Optional[str] = None,
) -> str:
    """Assemble the prompt for the response generator LLM."""
    parts: list[str] = []

    if conversation_context:
        parts.append(f"RECENT CONVERSATION:\n{conversation_context}\n")

    parts.append(f"USER SAID: {command}\n")

    if results:
        parts.append("TASK RESULTS:\n")
        for r in results:
            entry: dict[str, Any] = {
                "agent": r.agent,
                "action": r.action,
                "status": r.status.value,
            }
            if r.status == TaskStatus.COMPLETED and r.output is not None:
                output = r.output
                output_str = json.dumps(output, ensure_ascii=False, default=str)
                if len(output_str) > 4000:
                    output_str = output_str[:4000] + "... [truncated]"
                entry["output"] = output_str
            elif r.error:
                entry["error"] = r.error
            parts.append(json.dumps(entry, ensure_ascii=False, default=str))
            parts.append("\n")

    parts.append(
        "\nGenerate a natural, spoken response for MAYA to say aloud."
    )
    return "\n".join(parts)


def _call_ollama(
    prompt: str,
    model: str,
    *,
    temperature: float = RESPONSE_TEMPERATURE,
    num_ctx: int = RESPONSE_NUM_CTX,
) -> str:
    client = ollama.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": temperature, "num_ctx": num_ctx},
    )
    return response.message.content or ""


class ResponseGenerator:
    """Generates natural-language responses from task results."""

    def generate(
        self,
        command: str,
        results: list[TaskResult],
        conversation_context: Optional[str] = None,
    ) -> str:
        """Build a spoken response for the user.

        Tries the primary response model, then falls back to local.
        """
        prompt = _build_prompt(command, results, conversation_context)

        log_brain("response_start", model=RESPONSE_MODEL, command=command)

        response = self._try_model(RESPONSE_MODEL, prompt)
        if response is not None:
            return response

        if RESPONSE_LOCAL_FALLBACK != RESPONSE_MODEL:
            log_brain("response_fallback", model=RESPONSE_LOCAL_FALLBACK)
            response = self._try_model(RESPONSE_LOCAL_FALLBACK, prompt)
            if response is not None:
                return response

        log_brain("response_all_failed")
        return self._build_fallback_response(results)

    def generate_direct(
        self,
        command: str,
        direct_response: Optional[str] = None,
        conversation_context: Optional[str] = None,
    ) -> str:
        """Handle the no-agent path. If the planner supplied a direct_response,
        use it. Otherwise, run the response model on the command alone."""
        if direct_response:
            return direct_response

        prompt_parts: list[str] = []
        if conversation_context:
            prompt_parts.append(f"RECENT CONVERSATION:\n{conversation_context}\n")
        prompt_parts.append(f"USER SAID: {command}\n")
        prompt_parts.append("Respond naturally as MAYA, a helpful AI assistant.")

        prompt = "\n".join(prompt_parts)

        log_brain("direct_response_start", model=RESPONSE_MODEL)

        response = self._try_model(RESPONSE_MODEL, prompt)
        if response is not None:
            return response

        if RESPONSE_LOCAL_FALLBACK != RESPONSE_MODEL:
            response = self._try_model(RESPONSE_LOCAL_FALLBACK, prompt)
            if response is not None:
                return response

        return direct_response or "I'm here, but I'm having trouble responding right now."

    def _try_model(self, model: str, prompt: str) -> Optional[str]:
        """Attempt generation with *model*, returning None on exhausted retries."""
        for attempt in range(RESPONSE_MAX_RETRIES + 1):
            try:
                text = _call_ollama(prompt, model)
                if text.strip():
                    log_brain(
                        "response_success",
                        model=model,
                        attempt=attempt,
                        length=len(text),
                    )
                    return text.strip()
            except Exception as exc:
                log_brain(
                    "response_attempt_failed",
                    model=model,
                    attempt=attempt,
                    error=str(exc),
                    traceback=traceback.format_exc(),
                )
        return None

    def _build_fallback_response(self, results: list[TaskResult]) -> str:
        """Deterministic fallback when all LLM attempts fail."""
        completed = [r for r in results if r.status == TaskStatus.COMPLETED]
        failed = [r for r in results if r.status == TaskStatus.FAILED]

        if not completed and not failed:
            return "I processed your request but have no results to share."

        parts: list[str] = []
        if completed:
            parts.append(
                f"I completed {len(completed)} "
                f"{'task' if len(completed) == 1 else 'tasks'} successfully."
            )
        if failed:
            parts.append(
                f"{len(failed)} {'task' if len(failed) == 1 else 'tasks'} failed."
            )
        return " ".join(parts)
