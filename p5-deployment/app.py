"""Streamlit entry point for the FMCG Competitive Research Copilot."""

import math
import os
import time
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from tracing import trace_step, update_observation


@contextmanager
def history_db():
    path = Path(os.getenv("CHAT_HISTORY_DB", str(Path(__file__).parent / "data" / "chat_history.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id, id)")
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


def save_message(conversation_id: str, role: str, content: str) -> None:
    with history_db() as db:
        if role == "user":
            db.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND NOT EXISTS (SELECT 1 FROM messages WHERE conversation_id = ? AND role = 'user')",
                (conversation_title(content), conversation_id, conversation_id),
            )
        db.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                   (conversation_id, role, content, datetime.now(timezone.utc).isoformat()))


def load_messages(conversation_id: str) -> list[dict]:
    with history_db() as db:
        return [dict(row) for row in db.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        )]


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


def process_chat_turn(question: str, conversation_id: str) -> str:
    with trace_step("process-chat-turn", question=question, conversation_id=conversation_id) as turn:
        save_message(conversation_id, "user", question)
        with trace_step("respond-preview", question=question, conversation_id=conversation_id) as response:
            reply = (
                "I'm ready to help with your research. This is a preview of the chat; "
                "the research agent still needs to be connected before I can look up "
                "filings and provide an answer with citations."
            )
            update_observation(response, output=reply)
        save_message(conversation_id, "assistant", reply)
        update_observation(turn, output=reply)
    return reply


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
    except ValueError as exc:
        st.error(f"Invalid rate limit configuration: {exc}")
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
