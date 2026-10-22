"""Runtime configuration. Every value can be overridden with a MEDIATRACE_* env var."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"MEDIATRACE_{name}", default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(PROJECT_ROOT / "data"))))
    model_id: str = _env("MODEL_ID", "google/embeddinggemma-2")
    # "auto" picks CUDA when available, otherwise CPU.
    device: str = _env("DEVICE", "auto")
    allowed_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in _env("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    )
    max_upload_mb: int = int(_env("MAX_UPLOAD_MB", "512"))
    # Video: one searchable frame every N seconds.
    video_sample_seconds: float = float(_env("VIDEO_SAMPLE_SECONDS", "2.0"))
    video_max_frames: int = int(_env("VIDEO_MAX_FRAMES", "600"))
    # Audio: fixed windows with overlap.
    audio_window_seconds: float = float(_env("AUDIO_WINDOW_SECONDS", "5.0"))
    audio_hop_seconds: float = float(_env("AUDIO_HOP_SECONDS", "2.5"))
    # Documents
    pdf_render_scale: float = float(_env("PDF_RENDER_SCALE", "1.5"))
    text_chunk_chars: int = int(_env("TEXT_CHUNK_CHARS", "900"))
    sheet_rows_per_chunk: int = int(_env("SHEET_ROWS_PER_CHUNK", "15"))
    embed_batch_size: int = int(_env("EMBED_BATCH_SIZE", "8"))

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def previews_dir(self) -> Path:
        return self.index_dir / "previews"

    @property
    def db_path(self) -> Path:
        return self.index_dir / "mediatrace.sqlite3"

    def ensure_dirs(self) -> None:
        for d in (self.uploads_dir, self.index_dir, self.previews_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
