"""Streamlit entry point for the FMCG Competitive Research Copilot."""

import math
import os
import time
import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from tracing import trace_identity, trace_step, update_observation
import response_cache
from response_cache import ChatResponse

logger = logging.getLogger(__name__)


@contextmanager
def history_db():
    path = Path(os.getenv("CHAT_HISTORY_DB", str(Path(__file__).parent / "data" / "chat_history.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id, id)")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            for name, sql_type in (("trace_id", "TEXT"), ("trace_url", "TEXT"),
                                   ("citations", "TEXT NOT NULL DEFAULT '[]'"),
                                   ("cache_status", "TEXT"), ("latency_ms", "REAL")):
                if name not in columns:
                    connection.execute(f"ALTER TABLE messages ADD COLUMN {name} {sql_type}")
            response_cache.initialize(connection)
            yield connection
    finally:
        connection.close()


def create_conversation() -> str:
    conversation_id = str(uuid4())
    with history_db() as db:
        db.execute("INSERT INTO conversations VALUES (?, ?, ?)", (conversation_id, "New chat", datetime.now(timezone.utc).isoformat()))
    return conversation_id


def conversation_title(content: str) -> str:
    words = content.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")


def save_message(conversation_id: str, role: str, content: str, *, trace_id=None,
                 trace_url=None, citations=None, cache_status=None, latency_ms=None) -> None:
    with history_db() as db:
        if role == "user":
            db.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND NOT EXISTS (SELECT 1 FROM messages WHERE conversation_id = ? AND role = 'user')",
                (conversation_title(content), conversation_id, conversation_id),
            )
        db.execute("""INSERT INTO messages
                   (conversation_id, role, content, created_at, trace_id, trace_url, citations, cache_status, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (conversation_id, role, content, datetime.now(timezone.utc).isoformat(),
                    trace_id, trace_url, json.dumps(citations or []), cache_status, latency_ms))


def load_messages(conversation_id: str) -> list[dict]:
    with history_db() as db:
        messages = [dict(row) for row in db.execute(
            "SELECT role, content, created_at, trace_id, trace_url, citations, cache_status, latency_ms FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        )]
        for message in messages:
            message["citations"] = json.loads(message["citations"])
        return messages


def check_rate_limit(timestamps: list[float], now: float, limit: int, window: int) -> tuple[list[float], int]:
    """Return the active requests and seconds until another request is allowed."""
    active = [stamp for stamp in timestamps if now - stamp < window]
    if len(active) >= limit:
        return active, max(1, math.ceil(active[-limit] + window - now))
    return active + [now], 0


def positive_setting(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def response_config() -> dict:
    generation = json.loads(os.getenv("CHAT_GENERATION_CONFIG", "{}"))
    if not isinstance(generation, dict):
        raise ValueError("CHAT_GENERATION_CONFIG must be a JSON object")
    allowed = {"temperature", "top_p", "top_k", "max_tokens", "seed", "stop",
               "frequency_penalty", "presence_penalty", "enable_thinking"}
    if set(generation) - allowed:
        raise ValueError("CHAT_GENERATION_CONFIG contains unsupported parameters")
    return {
        "backend": "preview",  # Change alongside the P4 adapter, never through a UI toggle.
        "model": os.getenv("CHAT_MODEL_ID", "Qwen3-8B"),
        "provider": os.getenv("CHAT_MODEL_PROVIDER", "unconnected"),
        "prompt_version": os.getenv("CHAT_PROMPT_VERSION", "preview-v1"),
        "corpus_version": os.getenv("CHAT_CORPUS_VERSION", "unavailable"),
        "pipeline_version": os.getenv("CHAT_PIPELINE_VERSION", "preview-v1"),
        "generation": generation,  # P2/P4 must use these actual settings when connected.
    }


def generate_response(question: str, history: list[dict], filters: dict, config: dict) -> ChatResponse:
    # P4 adapter belongs here; successful real answers must explicitly opt in to caching.
    return ChatResponse(
        answer="I'm ready to help with your research. This is a preview of the chat; "
               "the research agent still needs to be connected before I can look up "
               "filings and provide an answer with citations.",
        cacheable=False,
    )


def process_chat_turn(question: str, conversation_id: str, *, filters: dict | None = None,
                      bypass_cache: bool = False) -> str:
    started = time.perf_counter()
    history = load_messages(conversation_id)
    config, filters = response_config(), filters or {}
    ttl = positive_setting("CHAT_CACHE_TTL_SECONDS", 3600)
    enabled = os.getenv("CHAT_CACHE_ENABLED", "true").lower() == "true"
    status = ("bypass_preview" if config["backend"] == "preview" else
              "bypass_requested" if bypass_cache else "disabled" if not enabled else "miss")
    use_cache = status == "miss"
    key = response_cache.cache_key(question, history, filters, config)
    details = {"mode": config["backend"], "agent_connected": config["backend"] == "agent",
               "config": config, "cache_status": status, "cache_hit": False}
    with trace_step("process-chat-turn", question=question, conversation_id=conversation_id, metadata=details) as turn:
        save_message(conversation_id, "user", question)
        result = None
        if use_cache:
            try:
                with history_db() as db:
                    result = response_cache.lookup(db, key)
                status = "hit" if result else "miss"
            except sqlite3.Error:
                status = "error"
                logger.warning("Response cache read failed; generating an answer.")
        if result is None:
            name = "respond-preview" if config["backend"] == "preview" else "generate-response"
            with trace_step(name, question=question, conversation_id=conversation_id, metadata=details) as response:
                result = generate_response(question, history, filters, config)
                update_observation(response, output=result.answer)
            if use_cache and result.successful and result.cacheable:
                try:
                    with history_db() as db:
                        response_cache.store(db, key, result, ttl)
                except (sqlite3.Error, TypeError, ValueError):
                    logger.warning("Response cache write failed; answer will still be returned.")
        latency = round((time.perf_counter() - started) * 1000, 2)
        update_observation(turn, output=result.answer, metadata={**details, "cache_status": status,
                           "cache_hit": status == "hit", "latency_ms": latency},
                           **({"level": "ERROR", "status_message": "Response unsuccessful"} if not result.successful else {}))
        trace_id, trace_url = trace_identity(turn)
        save_message(conversation_id, "assistant", result.answer, trace_id=trace_id,
                     trace_url=trace_url, citations=result.citations, cache_status=status, latency_ms=latency)
    return result.answer


def main() -> None:
    st.set_page_config(page_title="FMCG Research Copilot", page_icon="📊")
    if "active_conversation_id" not in st.session_state:
        st.session_state.active_conversation_id = create_conversation()
        # Preserve any messages from a session started before persistence was added.
        for message in st.session_state.get("messages", []):
            save_message(st.session_state.active_conversation_id, message["role"], message["content"])
    if "request_timestamps" not in st.session_state:
        st.session_state.request_timestamps = []
    try:
        limit = positive_setting("CHAT_RATE_LIMIT", 5)
        window = positive_setting("CHAT_RATE_WINDOW_SECONDS", 60)
        positive_setting("CHAT_CACHE_TTL_SECONDS", 3600)
        response_config()
    except ValueError as exc:
        st.error(f"Invalid chat configuration: {exc}")
        st.stop()

    with st.sidebar:
        st.subheader("📊 FMCG Copilot")
        if st.button("New chat", use_container_width=True):
            st.session_state.active_conversation_id = create_conversation()
        with history_db() as db:
            conversations = [dict(row) for row in db.execute(
                "SELECT c.*, (SELECT content FROM messages WHERE conversation_id = c.id AND role = 'user' ORDER BY id LIMIT 1) AS first_message FROM conversations c WHERE EXISTS (SELECT 1 FROM messages WHERE conversation_id = c.id AND role = 'user') ORDER BY created_at DESC"
            )]
        st.caption("CHAT HISTORY")
        if not conversations:
            st.caption("Your conversations will appear here.")
        for conversation in conversations:
            title = conversation_title(conversation["first_message"]) if conversation["first_message"] else "New chat"
            if st.button(
                title,
                key=f"history_{conversation['id']}",
                type="primary" if conversation["id"] == st.session_state.active_conversation_id else "secondary",
                use_container_width=True,
            ):
                st.session_state.active_conversation_id = conversation["id"]
                st.rerun()

    st.session_state.messages = load_messages(st.session_state.active_conversation_id)

    st.title("FMCG Research Copilot")
    st.caption("Preview · Research agent not yet connected")

    if not st.session_state.messages:
        with st.chat_message("assistant"):
            st.markdown(
                "What would you like to research?\n\n"
                "For example: What were HUL's advertising expenses in FY24?"
            )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                if message.get("cache_status") == "hit":
                    st.caption("Cached response")
                if message.get("trace_url"):
                    st.link_button("View trace ↗", message["trace_url"])

    question = st.chat_input("Ask about a company, financial year, or competitor…", max_chars=5000)
    if question and question.strip():
        timestamps, retry_after = check_rate_limit(
            st.session_state.request_timestamps, time.monotonic(), limit, window
        )
        st.session_state.request_timestamps = timestamps
        if retry_after:
            st.warning(f"Message limit reached. Try again in {retry_after} seconds.")
            return
        question = question.strip()
        with st.chat_message("user"):
            st.markdown(question)

        reply = process_chat_turn(question, st.session_state.active_conversation_id)
        with st.chat_message("assistant"):
            st.markdown(reply)
        st.rerun()


if __name__ == "__main__":
    main()
