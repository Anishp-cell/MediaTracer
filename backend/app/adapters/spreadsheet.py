"""CSV / XLSX: rows are grouped into blocks that keep the header, so each
searchable unit reads like a small table with exact sheet/row/cell references."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable, Iterator

from ..config import Settings
from .base import Adapter, AdapterError, Unit
from .text import read_text_file


def col_letter(n: int) -> str:
    """1 -> A, 27 -> AA."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _blocks(rows: Iterable[tuple[int, list[str]]], sheet: str | None, rows_per_chunk: int) -> Iterator[Unit]:
    """rows: (1-based spreadsheet row number, cell values). First non-empty row is the header."""
    header: list[str] | None = None
    header_row = 0
    block: list[tuple[int, list[str]]] = []

    def emit() -> Unit:
        width = max(len(header or []), *(len(r) for _, r in block))
        lines = []
        for rn, vals in block:
            cells = []
            for c, v in enumerate(vals):
                if not v:
                    continue
                name = header[c] if header and c < len(header) and header[c] else col_letter(c + 1)
                cells.append(f"{name}: {v}")
            lines.append(f"Row {rn}: " + "; ".join(cells))
        prefix = f"Sheet {sheet}. " if sheet else ""
        cols = f"Columns: {', '.join(h for h in header if h)}.\n" if header else ""
        first, last = block[0][0], block[-1][0]
        loc = {
            "type": "sheet",
            "row_start": first,
            "row_end": last,
            "header_row": header_row or None,
            "cell_range": f"A{first}:{col_letter(max(width, 1))}{last}",
        }
        if sheet:
            loc["sheet"] = sheet
        return Unit(kind="rows", modality="text", locator=loc, text=prefix + cols + "\n".join(lines))

    for rn, vals in rows:
        if not any(vals):
            continue
        if header is None:
            header, header_row = vals, rn
            continue
        block.append((rn, vals))
        if len(block) >= rows_per_chunk:
            yield emit()
            block = []
    if block:
        yield emit()
    elif header is not None and header_row:
        # A sheet with only a header row is still searchable.
        loc = {"type": "sheet", "row_start": header_row, "row_end": header_row, "header_row": header_row,
               "cell_range": f"A{header_row}:{col_letter(len(header))}{header_row}"}
        if sheet:
            loc["sheet"] = sheet
        yield Unit(kind="rows", modality="text", locator=loc,
                   text=(f"Sheet {sheet}. " if sheet else "") + "Columns: " + ", ".join(h for h in header if h))


class CsvAdapter(Adapter):
    family = "spreadsheet"
    formats = {".csv": "CSV"}

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        text = read_text_file(path)
        if not text.strip():
            raise AdapterError("CSV is empty")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        try:
            rows = [(i, [c.strip() for c in r]) for i, r in enumerate(reader, start=1)]
        except csv.Error as e:
            raise AdapterError(f"Malformed CSV: {e}") from e
        units = list(_blocks(rows, None, settings.sheet_rows_per_chunk))
        if not units:
            raise AdapterError("CSV has no data rows")
        yield from units


class XlsxAdapter(Adapter):
    family = "spreadsheet"
    formats = {".xlsx": "Excel"}

    def availability(self) -> str | None:
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            return "openpyxl is not installed"
        return None

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        import openpyxl
        from openpyxl.utils.exceptions import InvalidFileException
        from zipfile import BadZipFile

        try:
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        except (InvalidFileException, BadZipFile, KeyError, OSError) as e:
            raise AdapterError(f"Could not open XLSX: {e}") from e
        produced = 0
        try:
            for ws in wb.worksheets:
                def rows(ws=ws):
                    for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                        yield r_idx, [_fmt(v) for v in row]
                for unit in _blocks(rows(), ws.title, settings.sheet_rows_per_chunk):
                    produced += 1
                    yield unit
        finally:
            wb.close()
        if produced == 0:
            raise AdapterError("Workbook has no data")
