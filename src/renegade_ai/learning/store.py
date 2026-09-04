from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    result TEXT,
    total_reward REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    state_key TEXT NOT NULL,
    state_json TEXT NOT NULL,
    action TEXT NOT NULL,
    reward REAL NOT NULL,
    next_state_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(episode_id, step)
);

CREATE INDEX IF NOT EXISTS idx_transitions_state ON transitions(state_key);
CREATE INDEX IF NOT EXISTS idx_transitions_action ON transitions(action);
"""


class ExperienceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def start_episode(self, mode: str = "run") -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO episodes(started_at, mode) VALUES (?, ?)", (now, mode)
            )
            return int(cursor.lastrowid)

    def add_transition(
        self,
        episode_id: int,
        step: int,
        state_key: str,
        state: dict[str, Any],
        action: str,
        reward: float,
        next_state_key: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO transitions(
                    episode_id, step, state_key, state_json, action, reward,
                    next_state_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    step,
                    state_key,
                    json.dumps(state, sort_keys=True),
                    action,
                    float(reward),
                    next_state_key,
                    now,
                ),
            )

    def finish_episode(self, episode_id: int, result: str, total_reward: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE episodes
                SET finished_at = ?, result = ?, total_reward = ?
                WHERE id = ?
                """,
                (now, result, float(total_reward), episode_id),
            )
