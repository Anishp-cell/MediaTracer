"""Adapter tests: real parsing/decoding, exact source locators, graceful failures. No model needed."""
from __future__ import annotations

import pytest

from app.adapters import AdapterError, adapter_for
from app.adapters.base import chunk_text


def units(path, settings):
    return list(adapter_for(path).iter_units(path, settings))


def test_image_units(samples, settings):
    (u,) = units(samples["png"], settings)
    assert u.modality == "image" and u.kind == "image"
    assert u.locator == {"type": "image", "width": 320, "height": 240}
    assert u.preview is not None


def test_pdf_pages_and_text(samples, settings):
    us = units(samples["pdf"], settings)
    pages = [u for u in us if u.kind == "page"]
    texts = [u for u in us if u.kind == "page_text"]
    assert [u.locator["page"] for u in pages] == [1, 2, 3]
    assert all(u.locator["page_count"] == 3 for u in us)
    lentil = [u for u in texts if "lentil" in u.text]
    assert lentil and lentil[0].locator["page"] == 1
    accuracy = [u for u in texts if "accuracy" in u.text]
    assert accuracy and accuracy[0].locator["page"] == 3


def test_markdown_lines_and_sections(samples, settings):
    us = units(samples["md"], settings)
    assert us[0].locator["line_start"] == 1
    lines = samples["md"].read_text(encoding="utf-8").splitlines()
    for u in us:
        start, end = u.locator["line_start"], u.locator["line_end"]
        span = "\n".join(lines[start - 1 : end])
        if start == end and len(lines[start - 1]) > settings.text_chunk_chars:
            assert u.text in span  # piece of a wrapped long line, still on the stated line
        else:
            assert u.text.startswith(lines[start - 1].strip()[:20])
        assert not u.text.startswith(("ler", "r text"))  # never cut mid-word
    install = [u for u in us if "pip install" in u.text]
    assert install and install[0].locator.get("section") in ("Title", "Install")


def test_csv_rows_and_cells(samples, settings):
    us = units(samples["csv"], settings)
    assert us[0].locator["row_start"] == 2 and us[0].locator["header_row"] == 1
    assert us[0].locator["cell_range"].startswith("A2:C")
    assert "product: Item 1" in us[0].text
    assert us[-1].locator["row_end"] == 21


def test_xlsx_sheet_locator(samples, settings):
    (u,) = units(samples["xlsx"], settings)
    assert u.locator["sheet"] == "Revenue"
    assert u.locator["cell_range"] == "A2:C3"
    assert "Region: North" in u.text


def test_docx_text_picture_table(samples, settings):
    us = units(samples["docx"], settings)
    kinds = {u.kind for u in us}
    assert {"text", "embedded_image", "table"} <= kinds
    deadline = next(u for u in us if u.kind == "text" and "deadline" in u.text)
    assert deadline.locator["section"] == "Schedule"
    assert "page" not in deadline.locator  # DOCX pages are never invented


def test_pptx_slides_and_picture_bbox(samples, settings):
    us = units(samples["pptx"], settings)
    slide1 = next(u for u in us if u.kind == "slide" and u.locator["slide"] == 1)
    assert "accuracy" in slide1.text.lower()
    pic = next(u for u in us if u.kind == "embedded_image")
    assert pic.locator["slide"] == 2 and len(pic.locator["bbox"]) == 4
    assert all(0 <= v <= 1 for v in pic.locator["bbox"])


def test_audio_windows(samples, settings):
    us = units(samples["wav"], settings)
    assert all(u.modality == "audio" for u in us)
    starts = [u.locator["start"] for u in us]
    assert starts[:3] == [0.0, 2.5, 5.0]
    assert us[0].locator["end"] == 5.0
    assert abs(us[-1].locator["end"] - 9.0) < 0.05
    assert us[0].audio.dtype.name == "float32" and us[0].audio.ndim == 1


def test_silent_audio_rejected(samples, settings):
    with pytest.raises(AdapterError):
        units(samples["silent_wav"], settings)


def test_video_frames_have_real_timestamps(samples, settings):
    us = units(samples["video"], settings)
    frames = [u for u in us if u.kind == "frame"]
    times = [u.locator["time"] for u in frames]
    assert times[0] == 0.0
    assert all(abs(b - a - settings.video_sample_seconds) < 0.2 for a, b in zip(times, times[1:]))
    # Scene colours: 0-4 s red, 4-8 s green, 8-12 s blue.
    for u in frames:
        r, g, b = u.image.resize((1, 1)).getpixel((0, 0))
        expected = "rgb"[min(int(u.locator["time"] // 4), 2)]
        assert max(("r", r), ("g", g), ("b", b), key=lambda x: x[1])[0] == expected
    audio = [u for u in us if u.kind == "video_audio"]
    assert audio and audio[0].locator["type"] == "video"


@pytest.mark.parametrize("key", ["corrupt_pdf", "fake_jpg", "empty_txt"])
def test_corrupt_inputs_raise_adapter_error(samples, settings, key):
    with pytest.raises(AdapterError):
        units(samples[key], settings)


def test_chunk_text_preserves_line_numbers():
    text = "\n".join(f"line {i}" for i in range(1, 301))
    chunks = chunk_text(text, 200)
    assert chunks[0][0] == 1
    assert chunks[-1][1] == 300
    for start, end, body in chunks:
        assert body.splitlines()[0] == f"line {start}"
        assert body.splitlines()[-1] == f"line {end}"


def test_unsupported_extension():
    assert adapter_for("archive.xyz") is None
