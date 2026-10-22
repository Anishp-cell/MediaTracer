"""SQLite persistence for sources, searchable items and indexing jobs."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id           TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    family       TEXT NOT NULL,
    format       TEXT NOT NULL,
    origin       TEXT NOT NULL,          -- 'upload' or 'local'
    source_path  TEXT NOT NULL UNIQUE,   -- absolute path of the original
    size_bytes   INTEGER NOT NULL,
    mtime        REAL,
    sha256       TEXT NOT NULL,
    status       TEXT NOT NULL,          -- queued | processing | indexed | failed
    error        TEXT,
    item_count   INTEGER NOT NULL DEFAULT 0,
    model_id     TEXT,
    created_at   REAL NOT NULL,
    indexed_at   REAL
);
CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256);

CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    file_id     TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,           -- image | page | page_text | frame | audio | text | slide | rows ...
    modality    TEXT NOT NULL,           -- what was embedded: text | image | audio
    locator     TEXT NOT NULL,           -- JSON source locator
    text        TEXT,                    -- extracted text (never model-generated)
    preview     TEXT,                    -- preview filename inside previews dir
    embedding   BLOB NOT NULL,           -- float32 vector
    dim         INTEGER NOT NULL,
    model_id    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_file ON items(file_id);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL,           -- queued | running | completed | failed | cancelled
    file_ids    TEXT NOT NULL,           -- JSON list
    total       INTEGER NOT NULL,
    done        INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    skipped     INTEGER NOT NULL DEFAULT 0,
    current     TEXT,
    progress    REAL NOT NULL DEFAULT 0,
    message     TEXT,
    errors      TEXT NOT NULL DEFAULT '[]',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
"""


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        # Jobs that were running when the process died can never finish.
        now = time.time()
        self._conn.execute(
            "UPDATE jobs SET status='failed', message='Interrupted by server restart', updated_at=? "
            "WHERE status IN ('queued','running')",
            (now,),
        )
        self._conn.execute(
            "UPDATE files SET status='failed', error='Interrupted by server restart' "
            "WHERE status IN ('queued','processing')"
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ helpers
    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    def _one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, tuple(params))

    # -------------------------------------------------------------------- files
    def insert_file(self, **fields: Any) -> str:
        fields.setdefault("id", new_id())
        fields.setdefault("created_at", time.time())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self._exec(f"INSERT INTO files ({cols}) VALUES ({marks})", fields.values())
        return fields["id"]

    def update_file(self, file_id: str, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE files SET {sets} WHERE id=?", [*fields.values(), file_id])

    def get_file(self, file_id: str) -> dict | None:
        return self._one("SELECT * FROM files WHERE id=?", (file_id,))

    def file_by_path(self, source_path: str) -> dict | None:
        return self._one("SELECT * FROM files WHERE source_path=?", (source_path,))

    def file_by_hash(self, sha256: str, origin: str) -> dict | None:
        return self._one(
            "SELECT * FROM files WHERE sha256=? AND origin=? ORDER BY created_at LIMIT 1", (sha256, origin)
        )

    def upload_by_name(self, filename: str) -> dict | None:
        return self._one(
            "SELECT * FROM files WHERE filename=? AND origin='upload' ORDER BY created_at DESC LIMIT 1",
            (filename,),
        )

    def list_files(self) -> list[dict]:
        return self._all("SELECT * FROM files ORDER BY created_at DESC")

    def delete_file(self, file_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM items WHERE file_id=?", (file_id,))
            self._conn.execute("DELETE FROM files WHERE id=?", (file_id,))

    # -------------------------------------------------------------------- items
    def replace_items(self, file_id: str, rows: list[dict]) -> None:
        """Atomically swap a file's items so a failed re-index never leaves a half state."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute("DELETE FROM items WHERE file_id=?", (file_id,))
                self._conn.executemany(
                    "INSERT INTO items (id, file_id, seq, kind, modality, locator, text, preview, embedding, dim, model_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            r["id"], file_id, r["seq"], r["kind"], r["modality"], json.dumps(r["locator"]),
                            r.get("text"), r.get("preview"),
                            np.asarray(r["embedding"], dtype=np.float32).tobytes(), int(len(r["embedding"])),
                            r["model_id"],
                        )
                        for r in rows
                    ],
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def get_item(self, item_id: str) -> dict | None:
        row = self._one(
            "SELECT id, file_id, seq, kind, modality, locator, text, preview, dim, model_id FROM items WHERE id=?",
            (item_id,),
        )
        if row:
            row["locator"] = json.loads(row["locator"])
        return row

    def items_for_file(self, file_id: str) -> list[dict]:
        rows = self._all(
            "SELECT id, file_id, seq, kind, modality, locator, text, preview FROM items WHERE file_id=? ORDER BY seq",
            (file_id,),
        )
        for r in rows:
            r["locator"] = json.loads(r["locator"])
        return rows

    def load_vectors(self, model_id: str) -> tuple[list[dict], np.ndarray]:
        """Return (item metadata, matrix) for every searchable item produced by model_id.

        Files being re-indexed stay searchable on their previous items until the
        new items replace them atomically; failed files are excluded.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT i.id, i.file_id, i.kind, i.modality, i.locator, i.text, i.preview, i.embedding, i.dim, "
                "f.family, f.filename FROM items i JOIN files f ON f.id = i.file_id "
                "WHERE i.model_id=? AND f.status IN ('indexed','queued','processing') ORDER BY f.id, i.seq",
                (model_id,),
            ).fetchall()
        meta, vecs = [], []
        for r in rows:
            vecs.append(np.frombuffer(r["embedding"], dtype=np.float32, count=r["dim"]))
            meta.append(
                {
                    "id": r["id"], "file_id": r["file_id"], "kind": r["kind"], "modality": r["modality"],
                    "locator": json.loads(r["locator"]), "text": r["text"], "preview": r["preview"],
                    "family": r["family"], "filename": r["filename"],
                }
            )
        matrix = np.vstack(vecs) if vecs else np.zeros((0, 0), dtype=np.float32)
        return meta, matrix

    # --------------------------------------------------------------------- jobs
    def create_job(self, file_ids: list[str]) -> str:
        job_id = new_id()
        now = time.time()
        self._exec(
            "INSERT INTO jobs (id, status, file_ids, total, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (job_id, "queued", json.dumps(file_ids), len(file_ids), now, now),
        )
        return job_id

    def update_job(self, job_id: str, **fields: Any) -> None:
        if "errors" in fields:
            fields["errors"] = json.dumps(fields["errors"])
        fields["updated_at"] = time.time()
        sets = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE jobs SET {sets} WHERE id=?", [*fields.values(), job_id])

    def get_job(self, job_id: str) -> dict | None:
        row = self._one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row:
            row["file_ids"] = json.loads(row["file_ids"])
            row["errors"] = json.loads(row["errors"])
        return row

    def list_jobs(self, limit: int = 20) -> list[dict]:
        rows = self._all("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["file_ids"] = json.loads(r["file_ids"])
            r["errors"] = json.loads(r["errors"])
        return rows
