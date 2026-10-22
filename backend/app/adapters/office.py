"""DOCX and PPTX adapters.

DOCX has no stored page layout, so locators use the nearest heading and
paragraph numbers rather than invented page numbers. PPTX slides are not
rendered (no LibreOffice dependency); slide text and embedded pictures are
indexed with their real slide numbers and picture bounding boxes.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Iterator

from PIL import Image, UnidentifiedImageError

from ..config import Settings
from .base import Adapter, AdapterError, Unit, thumbnail

MIN_PICTURE_SIDE = 64  # skip icons/bullets


def _open_picture(blob: bytes) -> Image.Image | None:
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im.load()
            img = im.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return None  # e.g. EMF/WMF vector images Pillow cannot decode
    if min(img.size) < MIN_PICTURE_SIDE:
        return None
    return img


class DocxAdapter(Adapter):
    family = "document"
    formats = {".docx": "Word"}
    needs = ("image",)

    def availability(self) -> str | None:
        try:
            import docx  # noqa: F401
        except ImportError:
            return "python-docx is not installed"
        return None

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        import docx
        from docx.opc.exceptions import PackageNotFoundError

        try:
            document = docx.Document(str(path))
        except (PackageNotFoundError, KeyError, ValueError) as e:
            raise AdapterError("Could not open DOCX: not a valid Word (.docx) package") from e

        section: str | None = None
        buf: list[str] = []
        buf_start = 1
        buf_section: str | None = None
        produced = 0

        def flush(end_para: int) -> Iterator[Unit]:
            nonlocal buf
            if buf:
                text = "\n".join(buf).strip()
                if text:
                    loc = {"type": "docx", "paragraph_start": buf_start, "paragraph_end": end_para}
                    if buf_section:
                        loc["section"] = buf_section
                    yield Unit(kind="text", modality="text", locator=loc, text=text)
            buf = []

        paragraphs = document.paragraphs
        for i, para in enumerate(paragraphs, start=1):
            style = (para.style.name or "") if para.style is not None else ""
            text = para.text.strip()
            if text and (style.startswith("Heading") or style == "Title"):
                for u in flush(i - 1):
                    produced += 1
                    yield u
                section = text
            if text:
                if not buf:
                    buf_start, buf_section = i, section
                buf.append(text)
                if sum(len(b) for b in buf) >= settings.text_chunk_chars:
                    for u in flush(i):
                        produced += 1
                        yield u
            # Inline pictures anchored in this paragraph.
            for blip in para._p.xpath(".//a:blip"):
                rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                part = document.part.related_parts.get(rid) if rid else None
                img = _open_picture(part.blob) if part is not None and hasattr(part, "blob") else None
                if img is None:
                    continue
                loc = {"type": "docx", "paragraph_start": i, "paragraph_end": i, "embedded_image": True}
                if section:
                    loc["section"] = section
                produced += 1
                yield Unit(kind="embedded_image", modality="image", locator=loc, image=img, preview=thumbnail(img))
        for u in flush(len(paragraphs)):
            produced += 1
            yield u

        # Tables are indexed row-group by row-group with their table number.
        for t_idx, table in enumerate(document.tables, start=1):
            rows = [[c.text.strip() for c in r.cells] for r in table.rows]
            rows = [r for r in rows if any(r)]
            for start in range(0, len(rows), settings.sheet_rows_per_chunk):
                block = rows[start : start + settings.sheet_rows_per_chunk]
                text = "\n".join(" | ".join(r) for r in block)
                produced += 1
                yield Unit(
                    kind="table",
                    modality="text",
                    locator={"type": "docx", "table": t_idx, "row_start": start + 1, "row_end": start + len(block)},
                    text=text,
                )
        if produced == 0:
            raise AdapterError("Document contains no text or pictures")


class PptxAdapter(Adapter):
    family = "document"
    formats = {".pptx": "PowerPoint"}
    needs = ("image",)

    def availability(self) -> str | None:
        try:
            import pptx  # noqa: F401
        except ImportError:
            return "python-pptx is not installed"
        return None

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        from pptx.exc import PackageNotFoundError

        try:
            prs = Presentation(str(path))
        except (PackageNotFoundError, KeyError, ValueError) as e:
            raise AdapterError("Could not open PPTX: not a valid PowerPoint (.pptx) package") from e
        sw, sh = prs.slide_width or 1, prs.slide_height or 1
        n_slides = len(prs.slides)
        produced = 0

        def walk(shapes):
            for shp in shapes:
                if shp.shape_type == MSO_SHAPE_TYPE.GROUP:
                    yield from walk(shp.shapes)
                else:
                    yield shp

        for s_idx, slide in enumerate(prs.slides, start=1):
            texts: list[str] = []
            title = None
            if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
                title = slide.shapes.title.text_frame.text.strip() or None
            for shp in walk(slide.shapes):
                if getattr(shp, "has_text_frame", False) and shp.has_text_frame:
                    t = shp.text_frame.text.strip()
                    if t:
                        texts.append(t)
                if getattr(shp, "has_table", False) and shp.has_table:
                    for row in shp.table.rows:
                        cells = [c.text.strip() for c in row.cells]
                        if any(cells):
                            texts.append(" | ".join(cells))
                if shp.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    try:
                        img = _open_picture(shp.image.blob)
                    except (AttributeError, KeyError, ValueError):
                        img = None
                    if img is not None:
                        bbox = None
                        if None not in (shp.left, shp.top, shp.width, shp.height):
                            bbox = [round(shp.left / sw, 4), round(shp.top / sh, 4),
                                    round(shp.width / sw, 4), round(shp.height / sh, 4)]
                        loc = {"type": "slide", "slide": s_idx, "slide_count": n_slides, "embedded_image": True}
                        if bbox:
                            loc["bbox"] = bbox  # normalised [x, y, w, h] on the slide
                        if title:
                            loc["slide_title"] = title
                        produced += 1
                        yield Unit(kind="embedded_image", modality="image", locator=loc, image=img,
                                   preview=thumbnail(img))
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip() if slide.notes_slide.notes_text_frame else ""
                if notes:
                    texts.append(f"Speaker notes: {notes}")
            body = "\n".join(texts).strip()
            if body:
                loc = {"type": "slide", "slide": s_idx, "slide_count": n_slides}
                if title:
                    loc["slide_title"] = title
                produced += 1
                yield Unit(kind="slide", modality="text", locator=loc, text=body[: settings.text_chunk_chars * 3])
        if produced == 0:
            raise AdapterError("Presentation contains no text or pictures")
