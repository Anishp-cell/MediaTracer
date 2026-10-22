"""MediaTrace FastAPI application."""
from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from . import schemas
from .adapters import ADAPTERS
from .config import Settings, settings as default_settings
from .db import Database
from .indexer import Indexer, Registration
from .model_service import ModelNotReady, ModelService
from .search import VectorIndex

log = logging.getLogger("mediatrace")

MATCH_TYPES = {
    "image": "Visual match", "page": "Page image match", "page_text": "Page text match",
    "frame": "Video frame match", "video_audio": "Video sound match", "audio": "Audio match",
    "text": "Text match", "table": "Table match", "slide": "Slide text match",
    "embedded_image": "Embedded picture match", "rows": "Spreadsheet rows match",
}
# Cosine-similarity bands (strong, moderate) per embedded modality, used only to
# label candidates — ranking hints, not probabilities. Set from the score
# calibration in docs/EVALUATION.md (scripts/evaluate.py, small demo corpus):
# "strong" ~ at/above the highest non-relevant score seen, "moderate" ~ above the
# 95th percentile of non-relevant scores. Unrelated items score ~0.5–0.7 with this
# model, so lower values are labelled weak. Override with MEDIATRACE_STRENGTH_BANDS
# as JSON, e.g. {"text": [0.7, 0.62], "image": [0.74, 0.65], "audio": [0.7, 0.66]}.
STRENGTH_BANDS = {"text": (0.70, 0.62), "image": (0.74, 0.65), "audio": (0.70, 0.66)}
if os.environ.get("MEDIATRACE_STRENGTH_BANDS"):
    STRENGTH_BANDS.update({k: tuple(v) for k, v in json.loads(os.environ["MEDIATRACE_STRENGTH_BANDS"]).items()})

mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("image/webp", ".webp")


def fmt_time(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def location_label(loc: dict) -> str:
    t = loc.get("type")
    if t == "pdf_page":
        return f"Page {loc['page']} of {loc['page_count']}"
    if t == "slide":
        s = f"Slide {loc['slide']} of {loc['slide_count']}"
        if loc.get("slide_title"):
            s += f" · {loc['slide_title']}"
        return s + (" · picture" if loc.get("embedded_image") else "")
    if t in ("video", "audio"):
        return f"{fmt_time(loc['start'])}–{fmt_time(loc['end'])}"
    if t == "sheet":
        where = f"Sheet {loc['sheet']}, " if loc.get("sheet") else ""
        return f"{where}rows {loc['row_start']}–{loc['row_end']} ({loc['cell_range']})"
    if t == "text":
        s = f"Lines {loc['line_start']}–{loc['line_end']}"
        return s + (f" · {loc['section']}" if loc.get("section") else "")
    if t == "docx":
        if loc.get("table"):
            return f"Table {loc['table']}, rows {loc['row_start']}–{loc['row_end']}"
        s = f"Paragraphs {loc['paragraph_start']}–{loc['paragraph_end']}"
        if loc.get("embedded_image"):
            s = f"Picture at paragraph {loc['paragraph_start']}"
        return s + (f" · {loc['section']}" if loc.get("section") else "")
    if t == "image":
        return f"Image · {loc.get('width')}×{loc.get('height')}"
    return ""


def open_url(file_id: str, loc: dict) -> str:
    base = f"/api/files/{file_id}/original"
    if loc.get("type") == "pdf_page":
        return f"{base}#page={loc['page']}"
    if loc.get("type") in ("video", "audio"):
        return f"/api/files/{file_id}/stream#t={loc['start']},{loc['end']}"
    return base


def strength(modality: str, semantic: float) -> str:
    strong, moderate = STRENGTH_BANDS.get(modality, (0.74, 0.65))
    return "strong" if semantic >= strong else "moderate" if semantic >= moderate else "weak"


class Services:
    def __init__(self, settings: Settings, load_model: bool = True, model: ModelService | None = None):
        settings.ensure_dirs()
        self.settings = settings
        self.db = Database(settings.db_path)
        self.model = model or ModelService(settings)
        self.index = VectorIndex(self.db, settings.model_id)
        self.index.reload()
        self.indexer = Indexer(settings, self.db, self.model, self.index)
        if load_model and self.model.state == "not_loaded":
            self.model.start_background_load()
        self.indexer.resume_interrupted()

    def close(self) -> None:
        self.indexer.shutdown()
        self.db.close()


def get_services(request: Request) -> Services:
    return request.app.state.services


# Module-level so FastAPI can resolve it from string annotations (PEP 563).
S = Annotated[Services, Depends(get_services)]


def create_app(settings: Settings | None = None, load_model: bool = True, model: ModelService | None = None) -> FastAPI:
    settings = settings or default_settings
    if not logging.getLogger("mediatrace").handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger("mediatrace").addHandler(handler)
        logging.getLogger("mediatrace").setLevel(logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = Services(settings, load_model=load_model, model=model)
        yield
        app.state.services.close()

    app = FastAPI(title="MediaTrace", version="0.1.0", lifespan=lifespan,
                  description="Local-first multimodal semantic search powered by EmbeddingGemma 2.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    def file_or_404(s: Services, file_id: str) -> dict:
        f = s.db.get_file(file_id)
        if f is None:
            raise HTTPException(404, "File not found")
        return f

    def file_info(f: dict) -> schemas.FileInfo:
        return schemas.FileInfo(
            id=f["id"], filename=f["filename"], family=f["family"], format=f["format"], origin=f["origin"],
            size_bytes=f["size_bytes"], sha256=f["sha256"], status=f["status"], error=f["error"],
            item_count=f["item_count"], created_at=f["created_at"], indexed_at=f["indexed_at"],
            modified_at=f["mtime"], model_id=f["model_id"],
            source_path=f["source_path"] if f["origin"] == "local" else None,
        )

    # ------------------------------------------------------------------ status
    @app.get("/api/health", response_model=schemas.Health)
    def health(s: S):
        files = s.db.list_files()
        return schemas.Health(
            status="ok" if s.model.ready else "degraded",
            model=schemas.ModelStatus(**s.model.status()),
            indexed_files=sum(1 for f in files if f["status"] == "indexed"),
            indexed_items=s.index.size,
        )

    @app.get("/api/capabilities", response_model=schemas.Capabilities)
    def capabilities(s: S):
        out = []
        for a in ADAPTERS:
            reason = a.availability()
            if reason is None and s.model.state == "ready":
                missing = [m for m in a.needs if m not in s.model.modalities]
                if missing:
                    why = "; ".join(s.model.modality_errors.get(m, "encoder not available") for m in missing)
                    reason = f"Model cannot embed {', '.join(missing)} ({why})"
            elif reason is None and s.model.state == "error":
                reason = "Embedding model failed to load"
            out.append(schemas.AdapterCapability(family=a.family, formats=a.formats, enabled=reason is None,
                                                 reason=reason))
        return schemas.Capabilities(
            adapters=out,
            accepted_extensions=[e for a, c in zip(ADAPTERS, out) if c.enabled for e in a.formats],
            max_upload_mb=settings.max_upload_mb,
            image_query="image" in s.model.modalities or s.model.state != "ready",
            video_refine=next(c.enabled for a, c in zip(ADAPTERS, out) if a.family == "video"),
        )

    # ---------------------------------------------------------------- indexing
    async def save_upload(upload: UploadFile, dest_dir: Path, limit: int) -> Path:
        fd, tmp = tempfile.mkstemp(dir=dest_dir, prefix=".upload-", suffix=Path(upload.filename or "").suffix)
        size = 0
        try:
            with open(fd, "wb") as out:
                while chunk := await upload.read(1 << 20):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, f"{upload.filename}: exceeds {settings.max_upload_mb} MB limit")
                    out.write(chunk)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return Path(tmp)

    @app.post("/api/index", response_model=schemas.IndexResponse)
    async def index_uploads(s: S, files: list[UploadFile] = File(...)):
        if not files:
            raise HTTPException(400, "No files provided")
        regs = []
        limit = settings.max_upload_mb * 1024 * 1024
        for up in files:
            name = Path(up.filename or "").name
            if not name:
                regs.append(schemas.Registration(file_id=None, filename="(unnamed)", action="rejected",
                                                 reason="Missing filename"))
                continue
            reason = s.indexer.check_type(name)
            if reason:  # reject before writing anything to disk
                regs.append(schemas.Registration(file_id=None, filename=name, action="rejected", reason=reason))
                continue
            try:
                tmp = await save_upload(up, settings.uploads_dir, limit)
            except HTTPException as e:
                regs.append(schemas.Registration(file_id=None, filename=name, action="rejected", reason=e.detail))
                continue
            # Hashing large files is blocking work; keep it off the event loop.
            r = await run_in_threadpool(s.indexer.register_upload, name, tmp)
            regs.append(schemas.Registration(**r.__dict__))
        to_index = [r.file_id for r in regs if r.action in ("new", "updated")]
        job_id = s.indexer.submit(to_index) if to_index else None
        return schemas.IndexResponse(job_id=job_id, files=regs)

    @app.post("/api/index/local", response_model=schemas.IndexResponse)
    def index_local(body: schemas.LocalIndexRequest, s: S):
        regs = []
        for raw in body.paths:
            p = Path(raw).expanduser()
            if p.is_dir():
                regs.extend(s.indexer.register_folder(p, body.recursive))
            elif p.is_file():
                regs.append(s.indexer.register_local(p))
            else:
                regs.append(Registration(None, raw, "rejected", "Path does not exist"))
        out = [schemas.Registration(file_id=r.file_id, filename=r.filename, action=r.action, reason=r.reason)
               for r in regs]
        to_index = [r.file_id for r in out if r.action in ("new", "updated")]
        job_id = s.indexer.submit(to_index) if to_index else None
        return schemas.IndexResponse(job_id=job_id, files=out)

    @app.post("/api/files/rescan", response_model=schemas.IndexResponse)
    def rescan_local(s: S):
        """Re-check every locally indexed file; re-index only those whose content changed."""
        out = []
        for f in s.db.list_files():
            if f["origin"] != "local" or f["status"] in ("queued", "processing"):
                continue  # in-flight files are already being (re)indexed
            p = Path(f["source_path"])
            if not p.is_file():
                s.db.update_file(f["id"], status="failed", error="Source file no longer exists")
                out.append(schemas.Registration(file_id=f["id"], filename=f["filename"], action="rejected",
                                                reason="Source file no longer exists"))
                continue
            r = s.indexer.register_local(p)
            out.append(schemas.Registration(**r.__dict__))
        s.index.reload()
        to_index = [r.file_id for r in out if r.action in ("new", "updated")]
        job_id = s.indexer.submit(to_index) if to_index else None
        return schemas.IndexResponse(job_id=job_id, files=out)

    @app.get("/api/jobs", response_model=list[schemas.Job])
    def list_jobs(s: S, limit: int = Query(20, ge=1, le=100)):
        return [schemas.Job(**j) for j in s.db.list_jobs(limit)]

    @app.get("/api/jobs/{job_id}", response_model=schemas.Job)
    def get_job(job_id: str, s: S):
        j = s.db.get_job(job_id)
        if j is None:
            raise HTTPException(404, "Job not found")
        return schemas.Job(**j)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, s: S):
        if not s.indexer.cancel(job_id):
            raise HTTPException(409, "Job is not running")
        return {"cancelled": True}

    # ------------------------------------------------------------------- files
    @app.get("/api/files", response_model=list[schemas.FileInfo])
    def list_files(s: S):
        return [file_info(f) for f in s.db.list_files()]

    @app.get("/api/files/{file_id}", response_model=schemas.FileInfo)
    def get_file(file_id: str, s: S):
        return file_info(file_or_404(s, file_id))

    @app.delete("/api/files/{file_id}")
    def remove_file(file_id: str, s: S, delete_uploaded_copy: bool = False):
        f = file_or_404(s, file_id)
        if f["status"] == "processing":
            raise HTTPException(409, "File is being indexed; cancel the job or wait for it to finish")
        s.indexer.remove_file(file_id, delete_uploaded_copy=delete_uploaded_copy)
        return {"removed": True}

    @app.post("/api/files/{file_id}/reindex", response_model=schemas.IndexResponse)
    def reindex_file(file_id: str, s: S):
        f = file_or_404(s, file_id)
        if f["status"] in ("queued", "processing"):
            raise HTTPException(409, "File is already queued or being indexed")
        s.db.update_file(file_id, status="queued", error=None)
        job_id = s.indexer.submit([file_id])
        return schemas.IndexResponse(job_id=job_id, files=[schemas.Registration(
            file_id=file_id, filename=f["filename"], action="updated")])

    def _source(s: Services, file_id: str) -> tuple[dict, Path]:
        f = file_or_404(s, file_id)
        p = Path(f["source_path"])
        if not p.is_file():
            raise HTTPException(410, "Original file is no longer available")
        return f, p

    @app.get("/api/files/{file_id}/original")
    def original(file_id: str, s: S, download: bool = False):
        f, p = _source(s, file_id)
        media = mimetypes.guess_type(f["filename"])[0] or "application/octet-stream"
        return FileResponse(p, media_type=media, filename=f["filename"],
                            content_disposition_type="attachment" if download else "inline")

    @app.get("/api/files/{file_id}/stream")
    def stream(file_id: str, s: S):
        """Range-capable playback of audio/video originals (FileResponse honours Range headers)."""
        f, p = _source(s, file_id)
        if f["family"] not in ("video", "audio"):
            raise HTTPException(400, "Streaming is only available for audio and video")
        media = mimetypes.guess_type(f["filename"])[0] or "application/octet-stream"
        return FileResponse(p, media_type=media, content_disposition_type="inline", filename=f["filename"])

    @app.get("/api/files/{file_id}/preview")
    def file_preview(file_id: str, s: S):
        file_or_404(s, file_id)
        for it in s.db.items_for_file(file_id):
            if it["preview"]:
                return FileResponse(settings.previews_dir / it["preview"], media_type="image/jpeg")
        raise HTTPException(404, "No preview available")

    @app.get("/api/files/{file_id}/items")
    def file_items(file_id: str, s: S):
        file_or_404(s, file_id)
        return s.db.items_for_file(file_id)

    @app.get("/api/items/{item_id}")
    def get_item(item_id: str, s: S):
        it = s.db.get_item(item_id)
        if it is None:
            raise HTTPException(404, "Item not found")
        it["location_label"] = location_label(it["locator"])
        return it

    @app.get("/api/items/{item_id}/preview")
    def item_preview(item_id: str, s: S):
        it = s.db.get_item(item_id)
        if it is None or not it["preview"]:
            raise HTTPException(404, "No preview available")
        p = settings.previews_dir / it["preview"]
        if not p.is_file():
            raise HTTPException(404, "Preview missing")
        return FileResponse(p, media_type="image/jpeg")

    # ------------------------------------------------------------------ search
    def build_results(s: Services, hits, took_ms: float, query: str, mode: str, families) -> schemas.SearchResponse:
        top = hits[0].score if hits else 0.0
        results = []
        for rank, h in enumerate(hits, start=1):
            m = h.meta
            text = m.get("text")
            results.append(schemas.SearchResult(
                rank=rank, item_id=m["id"], file_id=m["file_id"], filename=m["filename"], family=m["family"],
                kind=m["kind"], modality=m["modality"], match_type=MATCH_TYPES.get(m["kind"], "Match"),
                locator=m["locator"], location_label=location_label(m["locator"]),
                text=text[:600] if text else None,
                preview_url=f"/api/items/{m['id']}/preview" if m.get("preview") else None,
                original_url=f"/api/files/{m['file_id']}/original",
                open_url=open_url(m["file_id"], m["locator"]),
                score=round(h.score, 4), semantic_score=round(h.semantic, 4), keyword_score=round(h.keyword, 4),
                relative=round(h.score / top, 4) if top > 0 else 0.0,
                strength=strength(m["modality"], h.semantic),
                also_matched=sorted(set(h.also_matched)),
            ))
        notice = None
        if s.index.size == 0:
            notice = "Your collection is empty. Add files to start searching."
        elif not results:
            notice = "Nothing indexed matches these filters."
        elif all(r.strength == "weak" for r in results):
            notice = ("Only weak candidates were found. This does not prove the content is absent — "
                      "try rephrasing or describing it differently.")
        return schemas.SearchResponse(query=query, mode=mode, families=families, results=results,
                                      searched_items=s.index.size, took_ms=round(took_ms, 1), notice=notice)

    @app.post("/api/search", response_model=schemas.SearchResponse)
    def search(body: schemas.SearchRequest, s: S):
        q = body.query.strip()
        if not q:
            raise HTTPException(422, "Query is empty")
        if s.index.size == 0:
            return build_results(s, [], 0.0, q, body.mode, body.families)
        t0 = time.perf_counter()
        try:
            qvec = s.model.embed_queries([q])[0]
        except ModelNotReady as e:
            raise HTTPException(503, f"Embedding model not ready: {e}")
        hits = s.index.search(qvec, q, body.families, body.limit, body.mode, max_per_file=body.max_per_file)
        return build_results(s, hits, (time.perf_counter() - t0) * 1000, q, body.mode, body.families)

    @app.post("/api/search/image", response_model=schemas.SearchResponse)
    async def search_by_image(
        s: S,
        image: UploadFile = File(...),
        families: str | None = Form(None),
        limit: int = Form(20),
    ):
        fams = [f for f in (families or "").split(",") if f] or None
        data = await image.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(413, "Reference image too large")
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                img = im.convert("RGB")
        except (UnidentifiedImageError, OSError):
            raise HTTPException(415, "Reference file is not a supported image")
        label = f"[image] {Path(image.filename or 'reference').name}"
        if s.index.size == 0:
            return build_results(s, [], 0.0, label, "semantic", fams)
        t0 = time.perf_counter()
        try:
            # GPU work must not block the event loop (other requests, job polling).
            qvec = (await run_in_threadpool(s.model.embed_query_image, img))[0]
        except ModelNotReady as e:
            raise HTTPException(503, f"Embedding model not ready: {e}")
        except RuntimeError as e:  # e.g. the image encoder failed its load-time check
            raise HTTPException(503, str(e))
        hits = s.index.search(qvec, None, fams, max(1, min(limit, 100)), "semantic")
        return build_results(s, hits, (time.perf_counter() - t0) * 1000, label, "semantic", fams)

    @app.post("/api/items/{item_id}/refine", response_model=schemas.RefineResponse)
    def refine(item_id: str, body: schemas.RefineRequest, s: S):
        """Fine-grained second pass around a coarse video-frame hit."""
        import numpy as np

        from .adapters.media import sample_frames

        it = s.db.get_item(item_id)
        if it is None:
            raise HTTPException(404, "Item not found")
        if it["kind"] != "frame":
            raise HTTPException(400, "Refinement is only available for video frame results")
        f, p = _source(s, it["file_id"])
        loc = it["locator"]
        interval = loc.get("sample_interval", settings.video_sample_seconds)
        start = max(loc["time"] - interval, 0.0)
        end = loc["time"] + interval
        if loc.get("duration"):
            end = min(end, loc["duration"])
        try:
            frames = sample_frames(p, start, end, body.step)
        except Exception as e:  # PyAV decode/open errors on a damaged file
            raise HTTPException(422, f"Could not decode video around this timestamp: {e}")
        if not frames:
            raise HTTPException(422, "No frames could be decoded around this timestamp")
        try:
            q = s.model.embed_queries([body.query])[0]
            vecs = s.model.embed_images([im for _, im in frames])
        except ModelNotReady as e:
            raise HTTPException(503, f"Embedding model not ready: {e}")
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        scores = vecs @ q
        best = int(np.argmax(scores))
        return schemas.RefineResponse(
            item_id=item_id, coarse_time=loc["time"], best_time=round(frames[best][0], 3),
            best_score=round(float(scores[best]), 4),
            samples=[{"time": round(t, 3), "score": round(float(sc), 4)} for (t, _), sc in zip(frames, scores)],
        )

    return app


app = create_app()
