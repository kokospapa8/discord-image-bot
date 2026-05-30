"""
Conversation context logger with session management.

Triggers:
  1. Every Miffy response → append to JSONL + in-memory buffer
  2. Bot shutdown       → session_end flush
  3. 30min inactivity   → session_end flush, timer reset
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

log = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))
_CONTEXT_FILE = Path("/app/data/context.jsonl")
_SESSION_TIMEOUT = 30 * 60  # seconds
_MEMORY_LIMIT = 100          # max entries kept in memory


class ConversationLogger:
    def __init__(self) -> None:
        self._buffer: list[dict] = []
        self._last_activity: float = time.time()
        self._task: asyncio.Task | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._task = asyncio.create_task(self._monitor())
        log.info("conversation: logger started")

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self._write({"ts": self._now(), "event": "session_end", "reason": "shutdown"})
        log.info("conversation: session ended (shutdown)")

    # ── public API ────────────────────────────────────────────────────────────

    def log_message(self, message: "discord.Message") -> None:
        """Log an incoming user message."""
        self._append({
            "ts": self._now(),
            "guild_id": message.guild.id if message.guild else None,
            "channel_id": message.channel.id,
            "author_id": message.author.id,
            "author": message.author.display_name,
            "content": message.content[:500],
            "miffy": False,
        })
        self._last_activity = time.time()

    def log_response(self, channel_id: int, guild_id: int | None, text: str) -> None:
        """Log Miffy's response."""
        self._append({
            "ts": self._now(),
            "guild_id": guild_id,
            "channel_id": channel_id,
            "author": "미피",
            "content": text[:500],
            "miffy": True,
        })
        self._last_activity = time.time()

    def recent_str(self, channel_id: int, n: int = 15) -> str:
        """Last N messages from a channel, formatted for Claude."""
        entries = [e for e in self._buffer if e.get("channel_id") == channel_id]
        lines = [
            f"{'미피' if e.get('miffy') else e.get('author', '?')}: {e.get('content', '')}"
            for e in entries[-n:]
        ]
        return "\n".join(lines)

    # ── internals ─────────────────────────────────────────────────────────────

    def _append(self, entry: dict) -> None:
        self._buffer.append(entry)
        if len(self._buffer) > _MEMORY_LIMIT:
            self._buffer = self._buffer[-_MEMORY_LIMIT:]
        self._write(entry)

    def _write(self, entry: dict) -> None:
        try:
            _CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _CONTEXT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            log.warning("conversation: write failed: %s", exc)

    @staticmethod
    def _now() -> str:
        return datetime.now(_KST).isoformat()

    async def _monitor(self) -> None:
        """Flush session_end after 30 min of inactivity."""
        try:
            while True:
                await asyncio.sleep(60)
                if time.time() - self._last_activity >= _SESSION_TIMEOUT:
                    self._write({"ts": self._now(), "event": "session_end", "reason": "inactivity"})
                    log.info("conversation: session ended (inactivity)")
                    self._last_activity = time.time()
        except asyncio.CancelledError:
            pass


logger = ConversationLogger()
