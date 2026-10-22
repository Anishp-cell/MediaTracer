"""PDF: every page is indexed twice — as a rendered page image (finds charts,
diagrams and scanned pages) and as selectable-text chunks (finds passages).
Both carry the real 1-based page number."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..config import Settings
from .base import Adapter, AdapterError, Unit, chunk_text, thumbnail


class PdfAdapter(Adapter):
    family = "document"
    formats = {".pdf": "PDF"}
    needs = ("image",)

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        try:
            doc = pdfium.PdfDocument(str(path))
        except pdfium.PdfiumError as e:
            raise AdapterError(f"Could not open PDF: {e}") from e
        try:
            reader = PdfReader(str(path))
        except (PdfReadError, OSError, ValueError) as e:
            reader = None  # text extraction is optional; rendering still works
        try:
            n_pages = len(doc)
            if n_pages == 0:
                raise AdapterError("PDF has no pages")
            for idx in range(n_pages):
                page_no = idx + 1
                text = ""
                if reader is not None and idx < len(reader.pages):
                    try:
                        text = (reader.pages[idx].extract_text() or "").strip()
                    except Exception:  # pypdf can fail on odd encodings; page image still indexed
                        text = ""
                page = doc[idx]
                try:
                    img = page.render(scale=settings.pdf_render_scale).to_pil().convert("RGB")
                finally:
                    page.close()
                preview = thumbnail(img, 900)
                yield Unit(
                    kind="page",
                    modality="image",
                    locator={"type": "pdf_page", "page": page_no, "page_count": n_pages},
                    text=text[:2000] or None,
                    image=img,
                    preview=preview,
                )
                for start, end, chunk in chunk_text(text, settings.text_chunk_chars):
                    yield Unit(
                        kind="page_text",
                        modality="text",
                        locator={"type": "pdf_page", "page": page_no, "page_count": n_pages},
                        text=chunk,
                        preview=preview,
                    )
        finally:
            doc.close()
