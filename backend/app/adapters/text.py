from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..config import Settings
from .base import Adapter, AdapterError, Unit, chunk_text

HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):  # UTF-16 with BOM (e.g. Notepad "Unicode")
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError as e:
            raise AdapterError("Could not decode UTF-16 text file") from e
    if b"\x00" in raw[:4096]:
        raise AdapterError("File looks binary, not text")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


class TextAdapter(Adapter):
    family = "document"
    formats = {".txt": "Text", ".md": "Markdown", ".markdown": "Markdown"}

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        text = read_text_file(path)
        if not text.strip():
            raise AdapterError("File is empty")
        is_md = path.suffix.lower() in (".md", ".markdown")
        lines = text.splitlines()
        # Heading in effect for every line (Markdown only).
        section_at: list[str | None] = []
        current: str | None = None
        for line in lines:
            if is_md:
                m = HEADING.match(line)
                if m:
                    current = m.group(2)
            section_at.append(current)
        for start, end, chunk in chunk_text(text, settings.text_chunk_chars):
            locator = {"type": "text", "line_start": start, "line_end": end}
            section = section_at[start - 1] if is_md and start - 1 < len(section_at) else None
            if section:
                locator["section"] = section
            yield Unit(kind="text", modality="text", locator=locator, text=chunk)
