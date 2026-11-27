"""SQLite connection lifecycle and backwards-compatible schema migrations."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from storage import response_cache

@contextmanager
def history_db():
    path = Path(os.getenv("CHAT_HISTORY_DB", str(Path(__file__).resolve().parents[1] / "data" / "chat_history.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL)")
            if 'mode' not in {row[1] for row in connection.execute('PRAGMA table_info(conversations)')}:
                connection.execute("ALTER TABLE conversations ADD COLUMN mode TEXT NOT NULL DEFAULT 'research'")
            connection.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id, id)")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            for name, sql_type in (("trace_id", "TEXT"), ("trace_url", "TEXT"),
                                   ("citations", "TEXT NOT NULL DEFAULT '[]'"),
                                   ("cache_status", "TEXT"), ("latency_ms", "REAL"),
                                   ("response_json", "TEXT NOT NULL DEFAULT '{}'")):
                if name not in columns:
                    connection.execute(f"ALTER TABLE messages ADD COLUMN {name} {sql_type}")
            connection.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)""")
            if 'user_session_id' not in {row[1] for row in connection.execute('PRAGMA table_info(conversations)')}:
                connection.execute("ALTER TABLE conversations ADD COLUMN user_session_id TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS conversations_session ON conversations(user_session_id)")
            response_cache.initialize(connection)
            yield connection
    finally:
        connection.close()
