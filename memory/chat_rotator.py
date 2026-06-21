"""Chat rotation — archives full chats and starts fresh ones seamlessly."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from memory.active_chat import ActiveChat
from memory.chat_summarizer import ChatSummarizer
from memory.config import ARCHIVE_DIR, MAX_MESSAGES, MAX_TOKENS, ensure_dirs
from memory.schemas import ChatSummary


class ChatRotator:
    """Monitors chat size and rotates when thresholds are exceeded."""

    def __init__(
        self,
        active_chat: ActiveChat,
        summarizer: ChatSummarizer,
        *,
        max_messages: int = MAX_MESSAGES,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self._active_chat = active_chat
        self._summarizer = summarizer
        self._max_messages = max_messages
        self._max_tokens = max_tokens

    def needs_rotation(self) -> bool:
        return (
            self._active_chat.message_count >= self._max_messages
            or self._active_chat.estimated_tokens >= self._max_tokens
        )

    def rotate(self) -> tuple[Optional[ChatSummary], str]:
        """Rotate the active chat.

        Returns (summary_of_old_chat, new_chat_id).
        """
        old_chat = self._active_chat.chat
        summary: Optional[ChatSummary] = None

        if old_chat and old_chat.messages:
            self._archive_chat(old_chat.chat_id)

            summary = self._summarizer.summarize_chat(
                old_chat.chat_id, old_chat.messages
            )

        self._active_chat.clear()
        new_id = self._active_chat.create_new()

        return summary, new_id

    def check_and_rotate(self) -> Optional[tuple[ChatSummary, str]]:
        """Rotate if thresholds exceeded. Returns None if no rotation needed."""
        if not self.needs_rotation():
            return None
        summary, new_id = self.rotate()
        return (summary, new_id) if summary else None

    def _archive_chat(self, chat_id: str) -> None:
        ensure_dirs()
        data = self._active_chat.export_for_archive()
        if data is None:
            return
        path = ARCHIVE_DIR / f"{chat_id}.json"
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
