"""Common adapter interface.

An adapter turns one source file into a stream of searchable Units. Each Unit
carries exactly one embeddable payload (text, image or audio), a source locator
that points back into the original file, and optionally a preview image.
Adapters never call the model; the indexer batches units into the model service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from PIL import Image

from ..config import Settings


class AdapterError(Exception):
    """A file could not be processed (corrupt, unsupported codec, empty...)."""


@dataclass
class Unit:
    kind: str                      # e.g. "image", "page", "page_text", "frame", "audio", "text", "rows"
    locator: dict[str, Any]        # structured source locator (see schemas.Locator)
    modality: str                  # "text" | "image" | "audio" — what gets embedded
    text: str | None = None        # extracted source text (shown to user, used for keyword ranking)
    embed_text: str | None = None  # text payload when modality == "text" (defaults to text)
    image: Image.Image | None = None
    audio: np.ndarray | None = None  # mono float32 at audio_rate
    audio_rate: int = 16000
    preview: Image.Image | None = None  # saved as JPEG thumbnail if provided
    extra: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> Any:
        if self.modality == "text":
            return self.embed_text if self.embed_text is not None else (self.text or "")
        if self.modality == "image":
            return self.image
        if self.modality == "audio":
            return self.audio
        raise ValueError(f"unknown modality {self.modality}")


class Adapter:
    family: str = ""
    formats: dict[str, str] = {}   # extension (lowercase, with dot) -> format label
    needs: tuple[str, ...] = ()    # model modalities required ("image", "audio")

    def availability(self) -> str | None:
        """Return None when usable, otherwise a human-readable reason."""
        return None

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        raise NotImplementedError


def thumbnail(img: Image.Image, max_side: int = 640) -> Image.Image:
    t = img.convert("RGB")
    t.thumbnail((max_side, max_side))
    return t


def chunk_text(text: str, max_chars: int) -> list[tuple[int, int, str]]:
    """Split text into paragraph-aligned chunks. Returns (start_line, end_line, chunk), 1-based lines."""
    lines = text.splitlines()
    chunks: list[tuple[int, int, str]] = []
    buf: list[str] = []
    start = 1
    size = 0
    for i, line in enumerate(lines, start=1):
        if not buf:
            start = i
        # Hard-wrap pathological long lines (at whitespace when possible) so one chunk never explodes.
        while len(line) > max_chars:
            cut = line.rfind(" ", max_chars // 2, max_chars)
            cut = cut if cut > 0 else max_chars
            head, line = line[:cut], line[cut:].lstrip()
            if buf:
                chunks.append((start, i, "\n".join(buf).strip()))
                buf, size = [], 0
            chunks.append((i, i, head.strip()))
            start = i
        buf.append(line)
        size += len(line) + 1
        boundary = not line.strip()
        if size >= max_chars or (boundary and size >= max_chars * 0.6):
            chunks.append((start, i, "\n".join(buf).strip()))
            buf, size = [], 0
    if buf:
        chunks.append((start, len(lines), "\n".join(buf).strip()))
    return [c for c in chunks if c[2]]
