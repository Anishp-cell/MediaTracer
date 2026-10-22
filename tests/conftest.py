"""Shared fixtures.

Tests marked `model` use the real google/embeddinggemma-2 (loaded once per
session). Run only the fast suite with:  pytest -m "not model"
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import make_demo_corpus as demo  # noqa: E402
from app.config import Settings  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "model: needs the real EmbeddingGemma 2 model (slow)")


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path / "data")
    s.ensure_dirs()
    return s


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, Path]:
    """Small, fully synthetic files with known structure for every adapter."""
    d = tmp_path_factory.mktemp("samples")
    out: dict[str, Path] = {}

    red = Image.new("RGB", (320, 240), "white")
    ImageDraw.Draw(red).ellipse([80, 40, 240, 200], fill="red")
    out["png"] = d / "red_circle.png"
    red.save(out["png"])
    out["jpg"] = d / "chart.jpg"
    demo.accuracy_chart().save(out["jpg"])

    out["pdf"] = d / "paper.pdf"
    demo.write_pdf(out["pdf"], [
        {"text": demo.text_block(["Page one talks about lentil soup and kitchen recipes."])},
        {"text": demo.text_block(["Page two shows the network architecture."]), "images": [(demo.cnn_diagram(), 50, 360, 512, 205)]},
        {"text": demo.text_block(["Page three compares model accuracy."]), "images": [(demo.accuracy_chart(), 76, 360, 460, 268)]},
    ])

    out["md"] = d / "notes.md"
    out["md"].write_text("# Title\n\nIntro line.\n\n## Install\n\nRun pip install.\n" + "filler text. " * 200, encoding="utf-8")
    out["txt"] = d / "todo.txt"
    out["txt"].write_text("milk\neggs\nrenew passport\n", encoding="utf-8")
    out["csv"] = d / "inventory.csv"
    rows = ["sku,product,units"] + [f"S{i},Item {i},{i * 3}" for i in range(1, 21)]
    out["csv"].write_text("\n".join(rows) + "\n", encoding="utf-8")

    import docx
    doc = docx.Document()
    doc.add_heading("Schedule", 1)
    doc.add_paragraph("The final report deadline is Friday.")
    buf = io.BytesIO()
    red.save(buf, "PNG")
    buf.seek(0)
    doc.add_picture(buf)
    t = doc.add_table(rows=2, cols=2)
    t.rows[0].cells[0].text, t.rows[1].cells[0].text = "Item", "Laptops"
    out["docx"] = d / "notes.docx"
    doc.save(out["docx"])

    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[5])
    s1.shapes.title.text = "Model accuracy comparison"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Photos"
    s2.shapes.add_picture(str(out["png"]), Inches(1), Inches(2), width=Inches(4))
    out["pptx"] = d / "deck.pptx"
    prs.save(out["pptx"])

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Revenue"
    ws.append(["Region", "Q1", "Q2"])
    ws.append(["North", 10, 12])
    ws.append(["South", 7, 9])
    out["xlsx"] = d / "revenue.xlsx"
    wb.save(out["xlsx"])

    out["wav"] = d / "beeps.wav"
    demo.write_wav(out["wav"], demo.synth_beeps(seconds=9.0))
    out["silent_wav"] = d / "silence.wav"
    demo.write_wav(out["silent_wav"], np.zeros(16000 * 3, dtype=np.float32))

    codec, ext, _ = demo.pick_video_codec()
    scenes = [Image.new("RGB", (640, 480), c) for c in ("red", "green", "blue")]
    out["video"] = d / f"scenes{ext}"
    demo.write_video(out["video"], scenes, demo.synth_beeps(seconds=12.0))

    out["corrupt_pdf"] = d / "corrupt.pdf"
    out["corrupt_pdf"].write_bytes(b"%PDF-1.4 garbage")
    out["fake_jpg"] = d / "fake.jpg"
    out["fake_jpg"].write_text("not an image")
    out["empty_txt"] = d / "empty.txt"
    out["empty_txt"].write_text("")
    return out


@pytest.fixture(scope="session")
def model(tmp_path_factory):
    from app.model_service import ModelService

    m = ModelService(Settings(data_dir=tmp_path_factory.mktemp("model_data")))
    m.load()
    if not m.ready:
        pytest.skip(f"EmbeddingGemma 2 unavailable: {m.error}")
    return m
