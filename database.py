import json
import sqlite3
from config import DB_PATH
from logger import log

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            agent TEXT NOT NULL,
            content TEXT NOT NULL,
            sprint INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """
    )
    conn.commit()
    conn.close()
    log("DB", "✅ Database initialized")

def save_message(role: str, agent: str, content: str, sprint: int = 0):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (role, agent, content, sprint) VALUES (?, ?, ?, ?)",
        (role, agent, content, sprint),
    )
    conn.commit()
    conn.close()

def get_messages(agent: str, limit: int = 20) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE agent = ? ORDER BY id DESC LIMIT ?",
        (agent, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def save_state(key: str, value):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
        (key, json.dumps(value)),
    )
    conn.commit()
    conn.close()

def load_state(key: str, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return json.loads(row["value"])
    return default