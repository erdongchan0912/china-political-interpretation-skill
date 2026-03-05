#!/usr/bin/env python3
"""
SQLite-backed task storage.

Replaces the in-memory ``tasks`` dict so that analysis history survives
backend restarts.  Zero external dependencies (sqlite3 is in stdlib).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_JSON_FIELDS = ("result", "error", "files", "urls")


class TaskStore:
    """Thread-safe SQLite task store."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Initialise schema on the creating thread
        self._ensure_table(self._conn())

    # ------------------------------------------------------------------
    # Connection handling (one connection per thread for safety)
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id        TEXT PRIMARY KEY,
                status         TEXT NOT NULL DEFAULT 'pending',
                progress       INTEGER NOT NULL DEFAULT 0,
                current_stage  TEXT NOT NULL DEFAULT '等待开始',
                message        TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                topic          TEXT,
                force_browser  INTEGER DEFAULT 0,
                force_ocr      INTEGER DEFAULT 0,
                result         TEXT,
                error          TEXT,
                files          TEXT DEFAULT '[]',
                urls           TEXT DEFAULT '[]'
            )
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, task_id: str) -> dict[str, Any]:
        """Insert a new task and return it as a dict."""
        now = datetime.now(timezone.utc).isoformat()
        task: dict[str, Any] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0,
            "current_stage": "等待开始",
            "message": "",
            "created_at": now,
            "updated_at": now,
            "topic": None,
            "force_browser": False,
            "force_ocr": False,
            "result": None,
            "error": None,
            "files": [],
            "urls": [],
        }
        conn = self._conn()
        conn.execute(
            """INSERT INTO tasks
               (task_id, status, progress, current_stage, message,
                created_at, updated_at, result, error, files, urls)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id, "pending", 0, "等待开始", "",
                now, now, None, None, "[]", "[]",
            ),
        )
        conn.commit()
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        """Return task dict or None."""
        row = self._conn().execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def contains(self, task_id: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return row is not None

    def update(self, task_id: str, **kwargs: Any) -> None:
        """Update arbitrary fields for a task."""
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()

        sets: list[str] = []
        vals: list[Any] = []
        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            if key in _JSON_FIELDS:
                vals.append(json.dumps(value, ensure_ascii=False) if value is not None else None)
            elif isinstance(value, bool):
                vals.append(int(value))
            else:
                vals.append(value)
        vals.append(task_id)

        conn = self._conn()
        conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?",
            vals,
        )
        conn.commit()

    def delete(self, task_id: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()

    def list_all(self) -> list[dict[str, Any]]:
        """Return a summary list of all tasks (newest first)."""
        rows = self._conn().execute(
            "SELECT * FROM tasks ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def append_files(self, task_id: str, new_files: list[dict]) -> None:
        """Append uploaded files list without overwriting."""
        task = self.get(task_id)
        if task is None:
            return
        existing: list = task.get("files") or []
        existing.extend(new_files)
        self.update(task_id, files=existing)

    def append_urls(self, task_id: str, new_urls: list[dict]) -> None:
        """Append URLs list without overwriting."""
        task = self.get(task_id)
        if task is None:
            return
        existing: list = task.get("urls") or []
        existing.extend(new_urls)
        self.update(task_id, urls=existing)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for field in _JSON_FIELDS:
            raw = d.get(field)
            if isinstance(raw, str):
                try:
                    d[field] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass
        # Convert integer booleans back
        for bool_field in ("force_browser", "force_ocr"):
            if bool_field in d:
                d[bool_field] = bool(d[bool_field])
        return d
