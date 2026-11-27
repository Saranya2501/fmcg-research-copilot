"""Repository for conversations, messages, and user sessions."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from storage.database import history_db

def create_conversation(*, user_session_id=None) -> str:
    conversation_id = str(uuid4())
    with history_db() as db:
        db.execute("INSERT INTO conversations (id,title,created_at,user_session_id) VALUES (?, ?, ?, ?)",
                   (conversation_id, "New chat", datetime.now(timezone.utc).isoformat(),user_session_id))
    return conversation_id


def create_user_session(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Enter a name between 1 and 80 characters.")
    identifier = str(uuid4())
    with history_db() as db:
        db.execute("INSERT INTO user_sessions (id,name,created_at) VALUES (?,?,?)",
                   (identifier, name, datetime.now(timezone.utc).isoformat()))
    return identifier


def session_usage(identifier: str) -> dict:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    with history_db() as db:
        rows = db.execute("""SELECT m.response_json FROM messages m
            JOIN conversations c ON c.id=m.conversation_id
            WHERE c.user_session_id=? AND m.role='assistant'""", (identifier,))
        for row in rows:
            usage = json.loads(row[0]).get("usage") or {}
            for key in totals:
                totals[key] += int(usage.get(key) or 0)
    return totals


def conversation_title(content: str) -> str:
    words = content.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")


def save_message(conversation_id: str, role: str, content: str, *, trace_id=None,
                 trace_url=None, citations=None, cache_status=None, latency_ms=None, response=None) -> None:
    with history_db() as db:
        if role == "user":
            db.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND NOT EXISTS (SELECT 1 FROM messages WHERE conversation_id = ? AND role = 'user')",
                (conversation_title(content), conversation_id, conversation_id),
            )
        db.execute("""INSERT INTO messages
                   (conversation_id, role, content, created_at, trace_id, trace_url, citations, cache_status, latency_ms, response_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (conversation_id, role, content, datetime.now(timezone.utc).isoformat(),
                    trace_id, trace_url, json.dumps(citations or []), cache_status, latency_ms,json.dumps(response or {})))


def load_messages(conversation_id: str) -> list[dict]:
    with history_db() as db:
        messages = [dict(row) for row in db.execute(
            "SELECT id, role, content, created_at, trace_id, trace_url, citations, cache_status, latency_ms, response_json FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        )]
        for message in messages:
            message["citations"] = json.loads(message["citations"])
            message["response"] = json.loads(message.pop("response_json"))
        return messages


def require_conversation_owner(conversation_id: str, user_session_id: str) -> None:
    """Reject access to conversations outside the current user session."""
    with history_db() as db:
        owned = db.execute(
            "SELECT 1 FROM conversations WHERE id=? AND user_session_id=?",
            (conversation_id, user_session_id),
        ).fetchone()
    if not owned:
        raise ValueError("Conversation does not belong to this session.")


def find_user_session(identifier):
    with history_db() as db:
        return db.execute("SELECT name FROM user_sessions WHERE id=?", (identifier,)).fetchone()


def find_resume_conversation(identifier, conversation_id):
    with history_db() as db:
        selected = db.execute(
            "SELECT id FROM conversations WHERE id=? AND user_session_id=?",
            (conversation_id, identifier),
        ).fetchone()
        if selected is None:
            selected = db.execute(
                "SELECT id FROM conversations WHERE user_session_id=? ORDER BY created_at DESC LIMIT 1",
                (identifier,),
            ).fetchone()
        return selected['id'] if selected else None


def list_conversations(identifier):
    with history_db() as db:
        return [dict(row) for row in db.execute(
            """SELECT c.*, (SELECT content FROM messages
                WHERE conversation_id=c.id AND role='user' ORDER BY id LIMIT 1) AS first_message
                FROM conversations c WHERE c.user_session_id=?
                AND EXISTS (SELECT 1 FROM messages WHERE conversation_id=c.id AND role='user')
                ORDER BY created_at DESC""", (identifier,),
        )]
