"""Active chat management — stores the current conversation on disk."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from memory.config import ACTIVE_CHAT_DIR, ensure_dirs
from memory.schemas import Chat, ChatMessage, MessageRole


def _estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


class ActiveChat:
    """Manages a single active chat session persisted to disk."""

    def __init__(self) -> None:
        self._chat: Optional[Chat] = None

    @property
    def chat(self) -> Optional[Chat]:
        return self._chat

    @property
    def chat_id(self) -> Optional[str]:
        return self._chat.chat_id if self._chat else None

    @property
    def message_count(self) -> int:
        return self._chat.message_count if self._chat else 0

    @property
    def estimated_tokens(self) -> int:
        return self._chat.estimated_tokens if self._chat else 0

    def create_new(self, metadata: Optional[dict[str, Any]] = None) -> str:
        chat_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self._chat = Chat(
            chat_id=chat_id,
            metadata=metadata or {},
        )
        self._save()
        return chat_id

    def add_message(self, role: str, content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        if self._chat is None:
            self.create_new()
        assert self._chat is not None

        msg = ChatMessage(
            role=MessageRole(role),
            content=content,
            metadata=metadata or {},
        )
        self._chat.messages.append(msg)
        self._chat.message_count = len(self._chat.messages)
        self._chat.estimated_tokens += _estimate_tokens(content)
        self._chat.updated_at = datetime.now(tz=timezone.utc)
        self._save()

    def get_recent_messages(self, limit: int = 10) -> list[dict[str, Any]]:
        if self._chat is None:
            return []
        msgs = self._chat.messages[-limit:]
        return [
            {
                "role": m.role.value,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in msgs
        ]

    def get_all_messages(self) -> list[ChatMessage]:
        if self._chat is None:
            return []
        return list(self._chat.messages)

    def get_messages_as_text(self, limit: Optional[int] = None) -> str:
        if self._chat is None:
            return ""
        msgs = self._chat.messages
        if limit:
            msgs = msgs[-limit:]
        lines: list[str] = []
        for m in msgs:
            lines.append(f"{m.role.value}: {m.content}")
        return "\n".join(lines)

    def load_existing(self, chat_id: str) -> bool:
        path = self._chat_path(chat_id)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        self._chat = Chat.model_validate(data)
        return True

    def load_latest(self) -> bool:
        ensure_dirs()
        files = sorted(ACTIVE_CHAT_DIR.glob("*.json"), reverse=True)
        if not files:
            return False
        data = json.loads(files[0].read_text(encoding="utf-8"))
        self._chat = Chat.model_validate(data)
        return True

    def export_for_archive(self) -> Optional[dict[str, Any]]:
        if self._chat is None:
            return None
        return self._chat.model_dump(mode="json")

    def clear(self) -> None:
        if self._chat:
            path = self._chat_path(self._chat.chat_id)
            if path.exists():
                path.unlink()
        self._chat = None

    def _save(self) -> None:
        if self._chat is None:
            return
        ensure_dirs()
        path = self._chat_path(self._chat.chat_id)
        path.write_text(
            json.dumps(self._chat.model_dump(mode="json"), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _chat_path(chat_id: str) -> Path:
        return ACTIVE_CHAT_DIR / f"{chat_id}.json"
