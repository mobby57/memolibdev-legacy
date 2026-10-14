"""conversation.py - Multi-tour persistant (SQLite)."""
from __future__ import annotations
import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Turn:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    mission_id: str | None = None
    proposal_id: str | None = None


class Conversation:
    """Conversation multi-tour persistee en SQLite."""

    def __init__(self, db_path: Path, conversation_id: str | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        if conversation_id is None:
            self.conversation_id = self._create()
        else:
            self.conversation_id = conversation_id
        self.turns: list[Turn] = self._load()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                mission_id TEXT,
                proposal_id TEXT)""")

    def _create(self) -> str:
        cid = secrets.token_urlsafe(12)
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT INTO conversations (id, created_at) VALUES (?, ?)",
                      (cid, datetime.now().isoformat()))
        return cid

    def _load(self) -> list[Turn]:
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute(
                "SELECT role, content, timestamp, mission_id, proposal_id "
                "FROM turns WHERE conversation_id = ? ORDER BY id",
                (self.conversation_id,)).fetchall()
        return [Turn(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    def add(self, role: str, content: str, mission_id: str | None = None,
            proposal_id: str | None = None) -> Turn:
        t = Turn(role, content, mission_id=mission_id, proposal_id=proposal_id)
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                "INSERT INTO turns (conversation_id, role, content, timestamp, "
                "mission_id, proposal_id) VALUES (?, ?, ?, ?, ?, ?)",
                (self.conversation_id, t.role, t.content, t.timestamp,
                 t.mission_id, t.proposal_id))
        self.turns.append(t)
        return t

    def to_messages(self, max_turns: int = 20) -> list[dict]:
        recent = self.turns[-max_turns:]
        return [{"role": t.role, "content": t.content} for t in recent]

    def summary_for_context(self, max_chars: int = 2000) -> str:
        lines = []
        for t in self.turns[-10:]:
            role = "Utilisateur" if t.role == "user" else "Assistant"
            snippet = t.content[:200].replace("\n", " ")
            lines.append(f"{role}: {snippet}")
        return "\n".join(lines)[-max_chars:]

    def clear(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("DELETE FROM turns WHERE conversation_id = ?",
                      (self.conversation_id,))
        self.turns = []
