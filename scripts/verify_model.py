"""Verify real EmbeddingGemma 2 inference through MediaTrace's own ModelService.

    .venv\\Scripts\\python scripts\\verify_model.py

Runs offline from the local Hugging Face cache. Prints device/dtype/VRAM, the
modalities that passed the load-time forward-pass probe, and ranking checks.
Exit code 0 only if text works; image/audio results are reported as found.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app.config import Settings  # noqa: E402
from app.model_service import ModelService  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    import torch

    tmp = Path(tempfile.mkdtemp(prefix="mediatrace-verify-"))
    svc = ModelService(Settings(data_dir=tmp))
    t0 = time.time()
    svc.load()
    st = svc.status()
    print(json.dumps(st, indent=2))
    if not svc.ready:
        print("Model failed to load.")
        return 1
    if torch.cuda.is_available():
        print(f"CUDA memory allocated after load: {torch.cuda.memory_allocated() / 2**30:.2f} GB "
              f"(peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GB)")
    print(f"load wall time {time.time() - t0:.1f}s\n")

    results = {}
    print("Text")
    q = svc.embed_queries(["when is the report due?", "how do I cook lentils?"])
    d = svc.embed_texts(["The final report deadline is Friday at 5 pm.",
                         "Simmer red lentils with onion and cumin for 25 minutes."])
    sim = q @ d.T
    results["text"] = all([
        check("shape (2,768) float32", q.shape == (2, 768) and q.dtype == np.float32),
        check("finite + unit norm", bool(np.isfinite(q).all() and np.allclose(np.linalg.norm(q, axis=1), 1, atol=1e-3))),
        check("query 1 -> deadline doc", sim[0, 0] > sim[0, 1], f"{sim[0, 0]:.3f} vs {sim[0, 1]:.3f}"),
        check("query 2 -> lentil doc", sim[1, 1] > sim[1, 0], f"{sim[1, 1]:.3f} vs {sim[1, 0]:.3f}"),
    ])
    t = time.perf_counter()
    for _ in range(10):
        svc.embed_queries(["a quick latency probe"])
    print(f"  query embedding latency: {(time.perf_counter() - t) * 100:.1f} ms (mean of 10)")

    if "image" in svc.modalities:
        print(f"\nImage (input form: {svc.input_forms.get('image')})")
        red = Image.new("RGB", (320, 240), "white")
        ImageDraw.Draw(red).ellipse([80, 40, 240, 200], fill="red")
        import make_demo_corpus as demo
        chart = demo.accuracy_chart()
        iv = svc.embed_images([red, chart])
        qv = svc.embed_queries(["a red circle on a white background", "a bar chart comparing model accuracy"])
        s = qv @ iv.T
        results["image"] = all([
            check("shape/finite", iv.shape == (2, 768) and bool(np.isfinite(iv).all())),
            check("red circle query -> circle image", s[0, 0] > s[0, 1], f"{s[0, 0]:.3f} vs {s[0, 1]:.3f}"),
            check("chart query -> chart image", s[1, 1] > s[1, 0], f"{s[1, 1]:.3f} vs {s[1, 0]:.3f}"),
        ])
    else:
        print(f"\nImage: UNAVAILABLE — {svc.modality_errors.get('image')}")
        results["image"] = False

    if "audio" in svc.modalities:
        print(f"\nAudio (input form: {svc.input_forms.get('audio')})")
        import make_demo_corpus as demo
        beeps = demo.synth_beeps(seconds=5.0)
        rng = np.random.default_rng(1)
        hum = (0.3 * np.sin(2 * np.pi * 60 * np.arange(80000) / 16000) + 0.01 * rng.standard_normal(80000)).astype(np.float32)
        av_ = svc.embed_audio([beeps, hum])
        qa = svc.embed_queries(["a repeating electronic beeping alarm", "a low electrical hum"])
        s = qa @ av_.T
        results["audio"] = all([
            check("shape/finite", av_.shape == (2, 768) and bool(np.isfinite(av_).all())),
            check("beep query -> beep clip", s[0, 0] > s[0, 1], f"{s[0, 0]:.3f} vs {s[0, 1]:.3f}"),
        ])
        check("hum query -> hum clip (informational)", s[1, 1] > s[1, 0], f"{s[1, 1]:.3f} vs {s[1, 0]:.3f}")
    else:
        print(f"\nAudio: UNAVAILABLE — {svc.modality_errors.get('audio')}")
        results["audio"] = False

    if torch.cuda.is_available():
        print(f"\nCUDA peak memory: {torch.cuda.max_memory_allocated() / 2**30:.2f} GB")
    print("\nSummary:", json.dumps(results))
    return 0 if results.get("text") else 1


if __name__ == "__main__":
    sys.exit(main())
