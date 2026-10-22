"""Real EmbeddingGemma 2 inference: shapes, finiteness, normalisation, cross-modal ranking."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

pytestmark = pytest.mark.model


def _check(v: np.ndarray, n: int):
    assert v.shape == (n, 768)
    assert v.dtype == np.float32
    assert np.isfinite(v).all()
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-3)


def test_model_configuration(model):
    import torch

    assert model.dtype in ("bfloat16", "float32")  # never float16
    if torch.cuda.is_available():
        assert model.device == "cuda"
    assert {"text", "image", "audio"} <= model.modalities


def test_text_image_audio_embeddings(model, samples):
    _check(model.embed_queries(["a red circle", "a bar chart"]), 2)
    _check(model.embed_texts(["The deadline is Friday."]), 1)
    img = Image.open(samples["png"]).convert("RGB")
    _check(model.embed_images([img]), 1)
    from app.adapters import adapter_for
    from app.config import Settings

    clip = next(adapter_for(samples["wav"]).iter_units(samples["wav"], Settings())).audio
    _check(model.embed_audio([clip]), 1)


def test_cross_modal_ranking(model, samples):
    red = Image.open(samples["png"]).convert("RGB")
    chart = Image.open(samples["jpg"]).convert("RGB")
    imgs = model.embed_images([red, chart])
    q = model.embed_queries(["a red circle on a white background", "a bar chart comparing model accuracy"])
    sim = q @ imgs.T
    assert sim[0, 0] > sim[0, 1]
    assert sim[1, 1] > sim[1, 0]


def test_text_retrieval_ranking(model):
    docs = model.embed_texts(["The final report deadline is Friday at 5 pm.",
                              "Simmer red lentils with onion and cumin for 25 minutes."])
    q = model.embed_queries(["when is the report due?"])
    assert (q @ docs.T)[0, 0] > (q @ docs.T)[0, 1]
