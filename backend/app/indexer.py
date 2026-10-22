"""Background indexing: registration (fingerprints), job queue, unit embedding."""
from __future__ import annotations

import hashlib
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .adapters import AdapterError, Unit, adapter_for, supported_extensions
from .config import Settings
from .db import Database, new_id
from .model_service import ModelService
from .search import VectorIndex

log = logging.getLogger("mediatrace.indexer")

INTERRUPTED = "Interrupted by server restart"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class Registration:
    file_id: str | None
    filename: str
    action: str  # new | updated | unchanged | duplicate | rejected
    reason: str | None = None


class JobCancelled(Exception):
    pass


class Indexer:
    def __init__(self, settings: Settings, db: Database, model: ModelService, index: VectorIndex):
        self.settings = settings
        self.db = db
        self.model = model
        self.index = index
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._cancel: set[str] = set()
        self._worker = threading.Thread(target=self._loop, name="indexer", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------ registration
    def check_type(self, filename: str) -> str | None:
        adapter = adapter_for(filename)
        if adapter is None:
            return f"Unsupported file type. Supported: {', '.join(supported_extensions())}"
        reason = adapter.availability()
        if reason:
            return f"{Path(filename).suffix} support is unavailable: {reason}"
        return None

    def register_upload(self, filename: str, tmp_path: Path) -> Registration:
        """Take ownership of an uploaded temp file. Same content -> reuse; same name, new content -> update."""
        filename = Path(filename).name or "upload"
        reason = self.check_type(filename)
        if reason:
            tmp_path.unlink(missing_ok=True)
            return Registration(None, filename, "rejected", reason)
        digest = sha256_file(tmp_path)
        size = tmp_path.stat().st_size
        if size == 0:
            tmp_path.unlink(missing_ok=True)
            return Registration(None, filename, "rejected", "File is empty")

        dup = self.db.file_by_hash(digest, "upload")
        if dup and dup["status"] == "indexed" and dup["model_id"] == self.model.model_id:
            tmp_path.unlink(missing_ok=True)
            return Registration(dup["id"], filename, "duplicate", f"Identical content already indexed as {dup['filename']}")

        adapter = adapter_for(filename)
        existing = self.db.upload_by_name(filename)
        if existing:
            if existing["status"] in ("queued", "processing"):
                # Replacing the file under a running adapter would corrupt that index pass.
                tmp_path.unlink(missing_ok=True)
                return Registration(existing["id"], filename, "rejected",
                                    "A previous version is still being indexed; upload again when it finishes")
            dest = Path(existing["source_path"])
            try:
                os.replace(tmp_path, dest)
            except OSError as e:  # e.g. the original is open for playback on Windows
                tmp_path.unlink(missing_ok=True)
                return Registration(existing["id"], filename, "rejected", f"Could not replace stored copy: {e}")
            self.db.update_file(existing["id"], sha256=digest, size_bytes=size, mtime=time.time(),
                                status="queued", error=None)
            return Registration(existing["id"], filename, "updated")

        file_id = new_id()
        dest = self.settings.uploads_dir / f"{file_id}{Path(filename).suffix.lower()}"
        try:
            os.replace(tmp_path, dest)
        except OSError as e:
            tmp_path.unlink(missing_ok=True)
            return Registration(None, filename, "rejected", f"Could not store upload: {e}")
        self.db.insert_file(
            id=file_id, filename=filename, family=adapter.family, format=adapter.formats[Path(filename).suffix.lower()],
            origin="upload", source_path=str(dest), size_bytes=size, mtime=time.time(), sha256=digest, status="queued",
        )
        return Registration(file_id, filename, "new")

    def register_local(self, path: Path) -> Registration:
        """Index a file in place (never copied, never modified, never deleted)."""
        path = path.resolve()
        name = path.name
        if not path.is_file():
            return Registration(None, name, "rejected", "Not a file")
        reason = self.check_type(name)
        if reason:
            return Registration(None, name, "rejected", reason)
        st = path.stat()
        if st.st_size == 0:
            return Registration(None, name, "rejected", "File is empty")
        if st.st_size > self.settings.max_upload_mb * 1024 * 1024:
            return Registration(None, name, "rejected", f"File exceeds {self.settings.max_upload_mb} MB limit")
        existing = self.db.file_by_path(str(path))
        if existing and existing["status"] == "indexed" and existing["model_id"] == self.model.model_id:
            if existing["size_bytes"] == st.st_size and existing["mtime"] == st.st_mtime:
                return Registration(existing["id"], name, "unchanged")
            digest = sha256_file(path)
            if digest == existing["sha256"]:
                self.db.update_file(existing["id"], mtime=st.st_mtime)
                return Registration(existing["id"], name, "unchanged")
        else:
            digest = sha256_file(path)
        if existing:
            self.db.update_file(existing["id"], sha256=digest, size_bytes=st.st_size, mtime=st.st_mtime,
                                status="queued", error=None)
            return Registration(existing["id"], name, "updated")
        adapter = adapter_for(name)
        file_id = self.db.insert_file(
            filename=name, family=adapter.family, format=adapter.formats[path.suffix.lower()], origin="local",
            source_path=str(path), size_bytes=st.st_size, mtime=st.st_mtime, sha256=digest, status="queued",
        )
        return Registration(file_id, name, "new")

    def register_folder(self, folder: Path, recursive: bool = True) -> list[Registration]:
        folder = folder.resolve()
        exts = set(supported_extensions())
        pattern = "**/*" if recursive else "*"
        out = []
        for p in sorted(folder.glob(pattern)):
            rel = p.relative_to(folder).parts
            if any(part.startswith(".") for part in rel):
                continue  # hidden files/folders (caches, .git, ...) are not user media
            if p.is_file() and p.suffix.lower() in exts:
                out.append(self.register_local(p))
        return out

    # -------------------------------------------------------------------- jobs
    def submit(self, file_ids: list[str]) -> str:
        job_id = self.db.create_job(file_ids)
        self._queue.put(job_id)
        return job_id

    def cancel(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job or job["status"] not in ("queued", "running"):
            return False
        self._cancel.add(job_id)
        return True

    def resume_interrupted(self) -> str | None:
        ids = [f["id"] for f in self.db.list_files() if f["status"] == "failed" and f["error"] == INTERRUPTED]
        if not ids:
            return None
        for i in ids:
            self.db.update_file(i, status="queued", error=None)
        return self.submit(ids)

    def shutdown(self) -> None:
        self._queue.put(None)

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            try:
                self._run_job(job_id)
            except Exception as e:  # never let the worker die
                log.exception("Job %s crashed", job_id)
                msg = f"{type(e).__name__}: {e}"
                self.db.update_job(job_id, status="failed", message=msg, current=None)
                job = self.db.get_job(job_id) or {"file_ids": []}
                for fid in job["file_ids"]:
                    f = self.db.get_file(fid)
                    if f and f["status"] in ("queued", "processing"):
                        self.db.update_file(fid, status="failed", error=msg)
            finally:
                self._cancel.discard(job_id)

    def _wait_for_model(self, job_id: str) -> bool:
        while self.model.state in ("not_loaded", "loading"):
            if self.model.state == "not_loaded":
                self.model.start_background_load()
            self.db.update_job(job_id, message="Waiting for the embedding model to load...")
            if job_id in self._cancel:
                return False
            time.sleep(1)
        return self.model.ready

    def _run_job(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job is None:
            return
        if job_id in self._cancel:
            self.db.update_job(job_id, status="cancelled", message="Cancelled")
            return
        self.db.update_job(job_id, status="running")
        if not self._wait_for_model(job_id):
            msg = "Cancelled" if job_id in self._cancel else f"Model unavailable: {self.model.error}"
            for fid in job["file_ids"]:
                self.db.update_file(fid, status="failed", error=msg)
            self.db.update_job(job_id, status="cancelled" if job_id in self._cancel else "failed", message=msg)
            return
        total = len(job["file_ids"])
        done = failed = 0
        errors: list[dict] = []
        for n, fid in enumerate(job["file_ids"]):
            f = self.db.get_file(fid)
            if f is None:
                continue
            self.db.update_job(job_id, current=f["filename"], progress=n / max(total, 1),
                               message=f"Indexing {f['filename']}")
            try:
                count = self.index_file(fid, job_id=job_id, job_base=n / total, job_span=1 / total)
                done += 1
                log.info("Indexed %s (%d items)", f["filename"], count)
            except JobCancelled:
                self.db.update_file(fid, status="failed", error="Indexing cancelled")
                for rest in job["file_ids"][n + 1 :]:
                    self.db.update_file(rest, status="failed", error="Indexing cancelled")
                self.db.update_job(job_id, status="cancelled", done=done, failed=failed, errors=errors,
                                   message="Cancelled", current=None)
                self.index.reload()
                return
            except Exception as e:
                failed += 1
                msg = str(e) if isinstance(e, AdapterError) else f"{type(e).__name__}: {e}"
                errors.append({"file_id": fid, "filename": f["filename"], "error": msg})
                self.db.update_file(fid, status="failed", error=msg)
                self.index.reload()  # drop any previous version of this file from search
                log.warning("Failed to index %s: %s", f["filename"], msg)
            self.db.update_job(job_id, done=done, failed=failed, errors=errors)
        status = "completed" if failed == 0 else ("failed" if done == 0 else "completed")
        msg = f"Indexed {done} of {total} file(s)" + (f", {failed} failed" if failed else "")
        self.db.update_job(job_id, status=status, progress=1.0, current=None, message=msg)

    # ---------------------------------------------------------------- one file
    def _unit_progress(self, unit: Unit) -> float | None:
        loc = unit.locator
        if loc.get("page") and loc.get("page_count"):
            return loc["page"] / loc["page_count"]
        if loc.get("slide") and loc.get("slide_count"):
            return loc["slide"] / loc["slide_count"]
        if loc.get("duration") and loc.get("end") is not None:
            frac = min(loc["end"] / loc["duration"], 1.0)
            # Video: frames are the first pass, the audio track the second.
            if loc.get("type") == "video":
                return frac / 2 if unit.modality == "image" else 0.5 + frac / 2
            return frac
        return None

    def index_file(self, file_id: str, job_id: str | None = None, job_base: float = 0.0, job_span: float = 1.0) -> int:
        f = self.db.get_file(file_id)
        if f is None:
            raise AdapterError("File record not found")
        path = Path(f["source_path"])
        if not path.is_file():
            raise AdapterError("Source file no longer exists")
        adapter = adapter_for(path.name if f["origin"] == "local" else f["filename"])
        if adapter is None:
            raise AdapterError("Unsupported file type")
        reason = adapter.availability()
        if reason:
            raise AdapterError(reason)
        missing = [m for m in adapter.needs if m not in self.model.modalities]
        if missing:
            raise AdapterError(f"Loaded model lacks required encoder(s): {', '.join(missing)}")

        self.db.update_file(file_id, status="processing", error=None)
        rows: list[dict] = []
        pending: dict[str, list[Unit]] = {"text": [], "image": [], "audio": []}
        written_previews: list[Path] = []
        batch = max(1, self.settings.embed_batch_size)
        seq = 0

        def flush(modality: str) -> None:
            nonlocal seq
            units = pending[modality]
            if not units:
                return
            if job_id and job_id in self._cancel:
                raise JobCancelled()
            vecs = self.model.embed_units(modality, [u.payload() for u in units])
            for u, v in zip(units, vecs):
                item_id = new_id()
                preview_name = None
                if u.preview is not None:
                    preview_name = f"{item_id}.jpg"
                    dest = self.settings.previews_dir / preview_name
                    u.preview.save(dest, "JPEG", quality=82)
                    written_previews.append(dest)
                rows.append({
                    "id": item_id, "seq": seq, "kind": u.kind, "modality": u.modality, "locator": u.locator,
                    "text": u.text, "preview": preview_name, "embedding": v, "model_id": self.model.model_id,
                })
                seq += 1
            pending[modality] = []
            if job_id:
                p = self._unit_progress(units[-1])
                if p is not None:
                    self.db.update_job(job_id, progress=job_base + job_span * min(p, 1.0))

        try:
            for unit in adapter.iter_units(path, self.settings):
                pending[unit.modality].append(unit)
                if len(pending[unit.modality]) >= batch:
                    flush(unit.modality)
            for m in pending:
                flush(m)
            if not rows:
                raise AdapterError("No searchable content found")
            old_previews = [r["preview"] for r in self.db.items_for_file(file_id) if r["preview"]]
            self.db.replace_items(file_id, rows)
        except BaseException:
            for p in written_previews:
                p.unlink(missing_ok=True)
            raise
        for name in old_previews:
            (self.settings.previews_dir / name).unlink(missing_ok=True)
        self.db.update_file(file_id, status="indexed", error=None, item_count=len(rows), indexed_at=time.time(),
                            model_id=self.model.model_id)
        self.index.reload()
        return len(rows)

    # ------------------------------------------------------------------ remove
    def remove_file(self, file_id: str, delete_uploaded_copy: bool = False) -> bool:
        f = self.db.get_file(file_id)
        if f is None:
            return False
        previews = [r["preview"] for r in self.db.items_for_file(file_id) if r["preview"]]
        self.db.delete_file(file_id)
        for name in previews:
            (self.settings.previews_dir / name).unlink(missing_ok=True)
        # Only MediaTrace's own upload copy can be deleted; local originals are never touched.
        if delete_uploaded_copy and f["origin"] == "upload":
            p = Path(f["source_path"])
            if self.settings.uploads_dir.resolve() in p.resolve().parents:
                p.unlink(missing_ok=True)
        self.index.reload()
        return True
