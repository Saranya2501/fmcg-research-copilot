"""Exact response caching in the chat SQLite database (no extra service)."""

import hashlib
import json
import logging
import time
from dataclasses import asdict

from chat.chat_models import ChatResponse


logger = logging.getLogger(__name__)



def cache_key(question: str, history: list[dict], filters: dict, config: dict) -> str:
    # Exclude timestamps, conversation IDs, and trace links, which don't affect answers.
    context = [{"role": m["role"], "content": m["content"],
                "citations": m.get("citations", []),
                "agent_context": m.get("response", {}).get("agent_context", {})} for m in history]
    payload = {"schema": 1, "question": question.strip(), "history": context,
               "filters": filters, "config": config}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS response_cache (
        cache_key TEXT PRIMARY KEY, response_json TEXT NOT NULL,
        created_at REAL NOT NULL, expires_at REAL NOT NULL)""")


def lookup(db, key: str, *, now: float | None = None) -> ChatResponse | None:
    now = time.time() if now is None else now
    row = db.execute("SELECT response_json, expires_at FROM response_cache WHERE cache_key = ?", (key,)).fetchone()
    if row is None:
        return None
    if row[1] <= now:
        db.execute("DELETE FROM response_cache WHERE cache_key = ?", (key,))
        return None
    try:
        result = ChatResponse(**json.loads(row[0]))
        if not result.successful or not result.cacheable or not result.answer.strip():
            raise ValueError("Invalid cached response")
        return result
    except (TypeError, ValueError, AttributeError):
        logger.exception("Invalid cached response; discarding entry.")
        db.execute("DELETE FROM response_cache WHERE cache_key = ?", (key,))
        return None


def store(db, key: str, response: ChatResponse, ttl: int, *, now: float | None = None):
    if ttl < 1:
        raise ValueError("Cache expiry must be positive")
    if not response.successful or not response.cacheable or not response.answer.strip():
        return
    now = time.time() if now is None else now
    db.execute("DELETE FROM response_cache WHERE expires_at <= ?", (now,))
    db.execute("INSERT OR REPLACE INTO response_cache VALUES (?, ?, ?, ?)",
               (key, json.dumps(asdict(response), allow_nan=False), now, now + ttl))


def clear(db):
    db.execute("DELETE FROM response_cache")
