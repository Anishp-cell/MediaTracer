"""Build the reproducible MediaTrace demo / evaluation corpus.

    python scripts/make_demo_corpus.py [--out data/demo_corpus]

Real photographs are downloaded at run time from COCO val2017 (CC BY 4.0) and a
LibriSpeech sample (CC BY 4.0); they are never committed to the repository.
Documents, spreadsheets, charts, diagrams, synthetic sounds and the test videos
are generated here so every page, slide, row and timestamp is known exactly.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import urllib.request
import zlib
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

COCO = "http://images.cocodataset.org/val2017/{}.jpg"
PHOTOS = {
    "bear.jpg": "000000000285",
    "living_room.jpg": "000000000139",
    "bedroom.jpg": "000000000632",
    "teddy_bears.jpg": "000000000776",
    "tennis_group.jpg": "000000001000",
    "two_cats.jpg": "000000039769",
}
VIDEO_SCENES = [("000000000724", "stop sign"), ("000000000785", "skier"), ("000000000872", "baseball")]
SPEECH_URL = "https://huggingface.co/datasets/Narsil/asr_dummy/resolve/main/1.flac"
SCENE_SECONDS = 4
FPS = 12


def fetch(url: str, cache: Path) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "MediaTrace-demo/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# ----------------------------------------------------------------- drawings
def cnn_diagram() -> Image.Image:
    img = Image.new("RGB", (1400, 560), "white")
    d = ImageDraw.Draw(img)
    f, fs = font(30), font(22)
    blocks = [("Input\n224x224x3", 60, 330, "#94a3b8"), ("Conv 3x3\n64", 260, 300, "#60a5fa"),
              ("Max Pool", 440, 240, "#a78bfa"), ("Conv 3x3\n128", 600, 220, "#60a5fa"),
              ("Max Pool", 780, 170, "#a78bfa"), ("Fully\nConnected", 950, 140, "#f59e0b"),
              ("Softmax\n10 classes", 1150, 110, "#22c55e")]
    for label, x, h, color in blocks:
        top = 280 - h // 2
        d.rectangle([x, top, x + 140, top + h], fill=color, outline="black", width=3)
        d.multiline_text((x + 70, 280), label, fill="black", font=fs, anchor="mm", align="center")
    for (_, x, _, _), (_, nx, _, _) in zip(blocks, blocks[1:]):
        d.line([x + 145, 280, nx - 8, 280], fill="black", width=4)
        d.polygon([(nx - 8, 270), (nx - 8, 290), (nx + 2, 280)], fill="black")
    d.text((700, 40), "Convolutional neural network architecture", fill="black", font=f, anchor="mm")
    return img


def accuracy_chart() -> Image.Image:
    img = Image.new("RGB", (1200, 700), "white")
    d = ImageDraw.Draw(img)
    f, fs = font(32), font(24)
    d.text((600, 40), "Model accuracy comparison (%)", fill="black", font=f, anchor="mm")
    models = [("ResNet-50", 76.1), ("ViT-B/16", 81.8), ("EfficientNet-B3", 81.6), ("MobileNetV3", 75.2)]
    base_y, left = 600, 140
    d.line([left, 100, left, base_y], fill="black", width=3)
    d.line([left, base_y, 1140, base_y], fill="black", width=3)
    for i, (name, acc) in enumerate(models):
        x = left + 60 + i * 240
        h = (acc - 60) / 30 * 450
        d.rectangle([x, base_y - h, x + 140, base_y], fill=["#2563eb", "#16a34a", "#f59e0b", "#dc2626"][i])
        d.text((x + 70, base_y - h - 24), f"{acc}", fill="black", font=fs, anchor="mm")
        d.text((x + 70, base_y + 30), name, fill="black", font=fs, anchor="mm")
    return img


def revenue_chart() -> Image.Image:
    img = Image.new("RGB", (1000, 600), "white")
    d = ImageDraw.Draw(img)
    f, fs = font(30), font(22)
    d.text((500, 36), "Quarterly revenue 2025 (USD thousands)", fill="black", font=f, anchor="mm")
    vals = [("Q1", 410), ("Q2", 455), ("Q3", 520), ("Q4", 610)]
    pts = [(150 + i * 230, 520 - (v - 350) * 1.5) for i, (_, v) in enumerate(vals)]
    d.line(pts, fill="#0f766e", width=6)
    for (q, v), (x, y) in zip(vals, pts):
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill="#0f766e")
        d.text((x, y - 30), str(v), fill="black", font=fs, anchor="mm")
        d.text((x, 560), q, fill="black", font=fs, anchor="mm")
    return img


# --------------------------------------------------------- minimal PDF writer
def _pdf_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, pages: list[dict]) -> None:
    """pages: [{"text": [(x, y, size, str), ...], "images": [(PIL.Image, x, y, w, h), ...]}] in points (612x792)."""
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id = add(b"")  # placeholder
    page_ids = []
    for page in pages:
        xobjs, ops = {}, []
        for n, (img, x, y, w, h) in enumerate(page.get("images", [])):
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=88)
            data = buf.getvalue()
            iid = add(
                f"<< /Type /XObject /Subtype /Image /Width {img.width} /Height {img.height} /ColorSpace /DeviceRGB "
                f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"
            )
            xobjs[f"Im{n}"] = iid
            ops.append(f"q {w} 0 0 {h} {x} {y} cm /Im{n} Do Q")
        for x, y, size, text in page.get("text", []):
            ops.append(f"BT /F1 {size} Tf {x} {y} Td ({_pdf_str(text)}) Tj ET")
        content = zlib.compress("\n".join(ops).encode("cp1252"))
        cid = add(f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode() + content + b"\nendstream")
        xo = " ".join(f"/{k} {v} 0 R" for k, v in xobjs.items())
        pid = add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] /Contents {cid} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> /XObject << {xo} >> >> >>".encode()
        )
        page_ids.append(pid)
    objs[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode()
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def wrap(text: str, width: int = 88) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def text_block(paragraphs: list[str], top: int = 720, size: int = 11) -> list[tuple]:
    out, y = [], top
    for p in paragraphs:
        for line in wrap(p):
            out.append((60, y, size, line))
            y -= size + 5
        y -= 8
    return out


# ------------------------------------------------------------------- audio
def synth_beeps(rate=16000, seconds=8.0) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    gate = ((t % 0.5) < 0.18).astype(np.float32)
    return (0.4 * np.sin(2 * np.pi * 1000 * t) * gate).astype(np.float32)


def synth_clapping(rate=16000, seconds=8.0, seed=7) -> np.ndarray:
    """Many short, randomly timed noise bursts with fast decay — an applause-like texture."""
    rng = np.random.default_rng(seed)
    n = int(rate * seconds)
    out = np.zeros(n, dtype=np.float32)
    clap_len = int(0.03 * rate)
    env = np.exp(-np.linspace(0, 6, clap_len)).astype(np.float32)
    for start in rng.integers(0, n - clap_len, size=int(seconds * 60)):
        out[start : start + clap_len] += rng.normal(0, 0.25, clap_len).astype(np.float32) * env
    return np.clip(out, -1, 1)


def write_wav(path: Path, samples: np.ndarray, rate=16000) -> None:
    import wave

    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def decode_audio(data: bytes, rate=16000) -> np.ndarray:
    import av

    with av.open(io.BytesIO(data)) as c:
        res = av.AudioResampler(format="flt", layout="mono", rate=rate)
        chunks = [f.to_ndarray().reshape(-1) for fr in c.decode(c.streams.audio[0]) for f in res.resample(fr)]
        chunks += [f.to_ndarray().reshape(-1) for f in res.resample(None)]
    return np.concatenate(chunks).astype(np.float32)


# ------------------------------------------------------------------- video
def pick_video_codec():
    import av

    for codec, ext, acodec in (("libx264", ".mp4", "aac"), ("h264", ".mp4", "aac"), ("libopenh264", ".mp4", "aac"),
                               ("libvpx-vp9", ".webm", "libopus"), ("libvpx", ".webm", "libvorbis")):
        try:
            av.codec.Codec(codec, "w")
            return codec, ext, acodec
        except Exception:
            continue
    raise RuntimeError("No browser-playable video encoder available in this PyAV build")


def write_video(path: Path, scenes: list[Image.Image], audio: np.ndarray | None, rate=16000) -> None:
    import av

    codec, _, acodec = pick_video_codec()
    W, H = 640, 480
    with av.open(str(path), "w") as out:
        vs = out.add_stream(codec, rate=FPS)
        vs.width, vs.height, vs.pix_fmt = W, H, "yuv420p"
        a_stream = None
        if audio is not None:
            a_stream = out.add_stream(acodec, rate=48000 if acodec == "libopus" else 44100)
            a_stream.codec_context.layout = "mono"
        for scene in scenes:
            base = scene.convert("RGB").resize((int(W * 1.15), int(H * 1.15)))
            for i in range(SCENE_SECONDS * FPS):
                # Slow pan so frames are not identical.
                dx = int((base.width - W) * i / (SCENE_SECONDS * FPS))
                frame = av.VideoFrame.from_image(base.crop((dx, 0, dx + W, H)))
                for p in vs.encode(frame):
                    out.mux(p)
        for p in vs.encode():
            out.mux(p)
        if a_stream is not None:
            arate = a_stream.codec_context.sample_rate
            fmt = a_stream.codec_context.format.name
            frame_size = a_stream.codec_context.frame_size or None
            try:  # encoders such as AAC require frames of exactly frame_size samples
                res = av.AudioResampler(format=fmt, layout="mono", rate=arate, frame_size=frame_size)
            except TypeError:  # older PyAV without frame_size support
                res = av.AudioResampler(format=fmt, layout="mono", rate=arate)
            step = rate  # 1 s chunks
            pts = 0
            for s in range(0, len(audio), step):
                chunk = audio[s : s + step].astype(np.float32).reshape(1, -1)
                af = av.AudioFrame.from_ndarray(chunk, format="flt", layout="mono")
                af.sample_rate = rate
                af.pts = None
                for rf in res.resample(af):
                    rf.pts = pts
                    rf.time_base = Fraction(1, arate)
                    pts += rf.samples
                    for p in a_stream.encode(rf):
                        out.mux(p)
            for p in a_stream.encode():
                out.mux(p)


# -------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "demo_corpus"))
    args = ap.parse_args()
    out = Path(args.out)
    cache = out / ".download_cache"
    for sub in ("images", "documents", "spreadsheets", "video", "audio"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    print("Photos (COCO val2017, CC BY 4.0)")
    for name, coco_id in PHOTOS.items():
        (out / "images" / name).write_bytes(fetch(COCO.format(coco_id), cache / f"{coco_id}.jpg"))
    revenue_chart().save(out / "images" / "revenue_chart.png")

    print("PDF")
    write_pdf(out / "documents" / "research_paper.pdf", [
        {"text": [(60, 740, 18, "Efficient Visual Retrieval with Shared Embeddings")] + text_block([
            "Abstract. We study semantic retrieval of photographs and scanned documents using a shared embedding "
            "space. Users describe what they remember and the system returns ranked evidence with provenance.",
            "1 Introduction. Personal media collections grow quickly and filenames rarely describe their content. "
            "Keyword search fails when the user remembers the meaning of a passage but not its wording.",
            "The remainder of this paper describes the network architecture (Section 2) and reports an accuracy "
            "comparison against common baselines (Section 3).",
        ], top=700)},
        {"text": [(60, 740, 16, "2 Network architecture")] + text_block([
            "Figure 1 shows the convolutional backbone used for the visual encoder: two convolution blocks, each "
            "followed by max pooling, and a fully connected classification head with a softmax output.",
        ], top=715) + [(60, 330, 10, "Figure 1: Convolutional neural network architecture.")],
         "images": [(cnn_diagram(), 50, 360, 512, 205)]},
        {"text": [(60, 740, 16, "3 Results")] + text_block([
            "Figure 2 compares top-1 accuracy on the validation set. ViT-B/16 achieves the best accuracy at 81.8 "
            "percent, closely followed by EfficientNet-B3.",
        ], top=715) + [(60, 330, 10, "Figure 2: Model accuracy comparison.")],
         "images": [(accuracy_chart(), 76, 360, 460, 268)]},
    ])

    print("DOCX / PPTX / XLSX / CSV / TXT / MD")
    import docx
    from docx.shared import Inches

    d = docx.Document()
    d.add_heading("Project Atlas — weekly meeting notes", 0)
    d.add_heading("Attendees", 1)
    d.add_paragraph("Priya, Tomas, Wen and Alex attended. Sam sent apologies.")
    d.add_heading("Schedule", 1)
    d.add_paragraph("The final report deadline is Friday at 5 pm. Tomas will collect the figures by Wednesday so "
                    "that the draft can be reviewed on Thursday morning.")
    d.add_heading("Office move", 1)
    d.add_paragraph("Facilities shared the photo below of the new meeting room furniture.")
    buf = io.BytesIO()
    Image.open(out / "images" / "living_room.jpg").save(buf, "JPEG")
    buf.seek(0)
    d.add_picture(buf, width=Inches(4))
    d.add_heading("Budget", 1)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Item", "Cost (USD)"
    for item, cost in (("Laptops", "12,400"), ("Cloud credits", "3,000"), ("Conference travel", "5,250")):
        row = t.add_row()
        row.cells[0].text, row.cells[1].text = item, cost
    d.save(out / "documents" / "meeting_notes.docx")

    from pptx import Presentation
    from pptx.util import Inches as PI

    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[0])
    s1.shapes.title.text = "Quarterly Review"
    s1.placeholders[1].text = "Research group update"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Model accuracy comparison"
    rows = [("Model", "Top-1 accuracy"), ("ResNet-50", "76.1%"), ("ViT-B/16", "81.8%"), ("MobileNetV3", "75.2%")]
    tbl = s2.shapes.add_table(len(rows), 2, PI(1), PI(1.8), PI(8), PI(2.4)).table
    for r, (a, b) in enumerate(rows):
        tbl.cell(r, 0).text, tbl.cell(r, 1).text = a, b
    s3 = prs.slides.add_slide(prs.slide_layouts[5])
    s3.shapes.title.text = "Field trip photos"
    s3.shapes.add_picture(str(out / "images" / "bear.jpg"), PI(2), PI(1.8), width=PI(6))
    s3.notes_slide.notes_text_frame.text = "We saw wildlife near the river on the second day."
    prs.save(out / "documents" / "quarterly_review.pptx")

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Revenue 2025"
    ws.append(["Region", "Q1", "Q2", "Q3", "Q4", "Total"])
    for region, q in (("North", [120, 132, 150, 171]), ("South", [98, 104, 121, 140]),
                      ("East", [110, 118, 131, 160]), ("West", [82, 101, 118, 139])):
        ws.append([region, *q, sum(q)])
    hc = wb.create_sheet("Headcount")
    hc.append(["Team", "Engineers", "Designers", "Managers"])
    for row in (("Search", 6, 1, 1), ("Platform", 4, 0, 1), ("Mobile", 3, 2, 1)):
        hc.append(list(row))
    wb.save(out / "spreadsheets" / "revenue_2025.xlsx")

    with open(out / "spreadsheets" / "inventory.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "product", "category", "units_in_stock", "warehouse"])
        products = [("A-100", "Wireless headphones", "Audio", 42, "Pune"), ("A-101", "Bluetooth speaker", "Audio", 17, "Pune"),
                    ("C-200", "USB-C charger", "Accessories", 230, "Mumbai"), ("C-201", "Laptop sleeve", "Accessories", 64, "Mumbai"),
                    ("K-300", "Mechanical keyboard", "Peripherals", 12, "Delhi"), ("K-301", "Ergonomic mouse", "Peripherals", 88, "Delhi")]
        w.writerows(products)

    (out / "documents" / "setup_notes.md").write_text(
        "# MediaTrace setup notes\n\n## Installation\n\nCreate a virtual environment, install PyTorch with CUDA "
        "support and then install the backend requirements.\n\n## Troubleshooting\n\nIf the GPU is not detected, "
        "check that the NVIDIA driver is recent and that torch.cuda.is_available() returns True.\n\n## Recipes\n\n"
        "Grandma's lentil soup: simmer red lentils with onion, garlic, cumin and tomatoes for 25 minutes.\n",
        encoding="utf-8")
    (out / "documents" / "todo.txt").write_text(
        "Buy groceries: milk, eggs, spinach\nRenew passport before the trip to Lisbon\nCall the dentist on Monday\n"
        "Return library books\n", encoding="utf-8")

    print("Audio")
    write_wav(out / "audio" / "alarm_beeps.wav", synth_beeps())
    write_wav(out / "audio" / "clapping_synthetic.wav", synth_clapping())
    speech = fetch(SPEECH_URL, cache / "librispeech_1.flac")
    (out / "audio" / "speech_librispeech.flac").write_bytes(speech)

    print("Video")
    codec, ext, _ = pick_video_codec()
    scenes = [Image.open(io.BytesIO(fetch(COCO.format(cid), cache / f"{cid}.jpg"))) for cid, _ in VIDEO_SCENES]
    write_video(out / "video" / f"street_sports{ext}", scenes, None)
    teddy = Image.open(out / "images" / "teddy_bears.jpg")
    speech_arr = decode_audio(speech)[: 16000 * 8]
    write_video(out / "video" / f"teddy_story{ext}", [teddy, teddy], speech_arr)

    labels = {
        "video_codec": codec,
        "scene_seconds": SCENE_SECONDS,
        "queries": [
            {"query": "a brown bear", "relevant": [{"file": "bear.jpg"}, {"file": "quarterly_review.pptx", "slide": 3}]},
            {"query": "a bedroom with a blue bed", "relevant": [{"file": "bedroom.jpg"}]},
            {"query": "stuffed teddy bears", "relevant": [{"file": "teddy_bears.jpg"}, {"file": f"teddy_story{ext}"}]},
            {"query": "two cats sleeping on a pink couch", "relevant": [{"file": "two_cats.jpg"}]},
            {"query": "children standing on a tennis court", "relevant": [{"file": "tennis_group.jpg"}]},
            {"query": "a living room with a television", "relevant": [{"file": "living_room.jpg"}, {"file": "meeting_notes.docx"}]},
            {"query": "a stop sign at a street corner", "relevant": [{"file": f"street_sports{ext}", "t": [0, 4]}]},
            {"query": "a person skiing on a snowy slope", "relevant": [{"file": f"street_sports{ext}", "t": [4, 8]}]},
            {"query": "a baseball player running", "relevant": [{"file": f"street_sports{ext}", "t": [8, 12]}]},
            {"query": "diagram of convolutional neural network layers", "relevant": [{"file": "research_paper.pdf", "page": 2}]},
            {"query": "bar chart comparing model accuracy", "relevant": [{"file": "research_paper.pdf", "page": 3}, {"file": "quarterly_review.pptx", "slide": 2}]},
            {"query": "when is the final report deadline", "relevant": [{"file": "meeting_notes.docx"}]},
            {"query": "quarterly revenue by region", "relevant": [{"file": "revenue_2025.xlsx", "sheet": "Revenue 2025"}, {"file": "revenue_chart.png"}]},
            {"query": "how many wireless headphones are in stock", "relevant": [{"file": "inventory.csv"}]},
            {"query": "a man reading a book aloud", "relevant": [{"file": "speech_librispeech.flac"}, {"file": f"teddy_story{ext}", "modality": "audio"}]},
            {"query": "a repeating electronic alarm beep", "relevant": [{"file": "alarm_beeps.wav"}]},
            {"query": "a crowd clapping and applauding", "relevant": [{"file": "clapping_synthetic.wav"}],
             "note": "synthetic applause-like noise bursts, not a real recording"},
            {"query": "how to fix the GPU not being detected", "relevant": [{"file": "setup_notes.md"}]},
            {"query": "lentil soup recipe", "relevant": [{"file": "setup_notes.md"}]},
        ],
    }
    (out / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    n = sum(1 for p in out.rglob("*") if p.is_file() and ".download_cache" not in p.parts and p.name != "labels.json")
    print(f"Wrote {n} files to {out} (video codec: {codec})")


if __name__ == "__main__":
    sys.exit(main())
