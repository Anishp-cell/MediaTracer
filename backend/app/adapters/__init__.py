from __future__ import annotations

from pathlib import Path

from .base import Adapter, AdapterError, Unit
from .image import ImageAdapter
from .media import AudioAdapter, VideoAdapter
from .office import DocxAdapter, PptxAdapter
from .pdf import PdfAdapter
from .spreadsheet import CsvAdapter, XlsxAdapter
from .text import TextAdapter

ADAPTERS: list[Adapter] = [
    ImageAdapter(),
    PdfAdapter(),
    VideoAdapter(),
    AudioAdapter(),
    DocxAdapter(),
    PptxAdapter(),
    TextAdapter(),
    CsvAdapter(),
    XlsxAdapter(),
]

_BY_EXT = {ext: a for a in ADAPTERS for ext in a.formats}


def adapter_for(path: Path | str) -> Adapter | None:
    return _BY_EXT.get(Path(path).suffix.lower())


def supported_extensions() -> list[str]:
    return sorted(_BY_EXT)


__all__ = ["ADAPTERS", "Adapter", "AdapterError", "Unit", "adapter_for", "supported_extensions"]
