"""The single place that talks to google/embeddinggemma-2.

The model is loaded once (in a background thread at startup) and shared.
All modality-specific input formats of the Sentence Transformers multimodal
API are encapsulated here; callers pass plain text, PIL images or 16 kHz mono
float32 audio arrays and always get back L2-normalised float32 vectors.
Every modality is verified with a real forward pass at load time.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import wave
from typing import Any, Sequence

import numpy as np

from .config import Settings

log = logging.getLogger("mediatrace.model")

EXPECTED_DIM = 768
AUDIO_RATE = 16000  # model card: mono 16 kHz audio


class ModelNotReady(RuntimeError):
    pass


class ModelService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_id = settings.model_id
        self.state = "not_loaded"  # not_loaded | loading | ready | error
        self.error: str | None = None
        self.device: str | None = None
        self.dtype: str | None = None
        self.gpu_name: str | None = None
        self.load_seconds: float | None = None
        self.modalities: set[str] = set()
        self.modality_errors: dict[str, str] = {}
        self.input_forms: dict[str, str] = {}
        self._tmp_files: list[str] = []
        self._model = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    # ----------------------------------------------------------------- loading
    def _select_device(self):
        import torch

        wanted = self.settings.device
        if wanted == "cpu" or not torch.cuda.is_available():
            if wanted == "cuda":
                raise RuntimeError("MEDIATRACE_DEVICE=cuda but torch.cuda.is_available() is False")
            return "cpu", torch.float32
        major, minor = torch.cuda.get_device_capability(0)
        archs = torch.cuda.get_arch_list()
        if f"sm_{major}{minor}" not in archs and f"compute_{major}{minor}" not in archs:
            msg = f"GPU sm_{major}{minor} not supported by this PyTorch build ({archs})"
            if wanted == "cuda":
                raise RuntimeError(msg)
            log.warning("%s; falling back to CPU", msg)
            return "cpu", torch.float32
        self.gpu_name = torch.cuda.get_device_name(0)
        # Model card: bfloat16 or float32 only. float16 is never used.
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
        return "cuda", dtype

    def load(self) -> None:
        with self._load_lock:
            if self.state == "ready":
                return
            self.state, self.error = "loading", None
            t0 = time.time()
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                device, dtype = self._select_device()
                assert dtype != torch.float16
                model = SentenceTransformer(
                    self.model_id,
                    device=device,
                    model_kwargs={"torch_dtype": dtype},
                )
                self.device, self.dtype = device, str(dtype).replace("torch.", "")
                self._probe(model)
                self._model = model
                self.load_seconds = round(time.time() - t0, 1)
                self.state = "ready"
                log.info("Loaded %s on %s (%s) in %.1fs; modalities=%s; input forms=%s", self.model_id, device,
                         self.dtype, self.load_seconds, sorted(self.modalities), self.input_forms)
            except Exception as e:  # surfaced via /api/health
                log.exception("Model load failed")
                self._model = None
                # Never report modalities/forms from a partial or earlier attempt.
                self.modalities, self.modality_errors, self.input_forms = set(), {}, {}
                self.load_seconds = None
                self._cleanup_tmp()
                self.state, self.error = "error", f"{type(e).__name__}: {e}"

    def start_background_load(self) -> threading.Thread:
        t = threading.Thread(target=self.load, name="model-loader", daemon=True)
        t.start()
        return t

    # ----------------------------------------------------------------- probing
    def _probe(self, model) -> None:
        """Verify each modality with a real forward pass before declaring it usable.

        The model card examples pass media as file paths/URLs. When the path form
        works, the in-memory form is used only if it reproduces the path-form
        embedding (cosine > 0.99). When the path form cannot run (e.g. no audio
        file decoder installed), the documented in-memory form is used alone.
        """
        text = self._encode_with(model, "encode_query", ["self test"])
        if text.shape != (1, EXPECTED_DIM):
            raise RuntimeError(f"Unexpected text embedding shape {text.shape}")
        self.modalities = {"text"}
        self.modality_errors = {}
        self.input_forms = {}

        # In-memory forms documented by the installed Sentence Transformers
        # (sentence_transformers/base/modality.py: a PIL image, and
        # {"array": waveform, "sampling_rate": 16000} for audio).
        candidates = (
            ("image", _probe_image(), lambda x: {"image": x}),
            ("audio", _probe_audio(), lambda x: {"audio": audio_input(x, AUDIO_RATE)}),
        )
        for modality, sample, to_memory in candidates:
            ref, ref_err = None, None
            try:  # documented file-path form (needs a file decoder, e.g. librosa for audio)
                ref = self._encode_with(model, "encode_document", [self._as_path_input(modality, sample)])
            except Exception as e:
                ref_err = f"{type(e).__name__}: {e}"
                log.info("%s path-form input unavailable: %s", modality, ref_err)
            try:
                mem = self._encode_with(model, "encode_document", [to_memory(sample)])
            except Exception as e:
                mem, mem_err = None, f"{type(e).__name__}: {e}"
                log.info("%s in-memory input rejected: %s", modality, mem_err)
            if mem is not None and (ref is None or float(mem[0] @ ref[0]) > 0.99):
                chosen = "memory"  # matches the path form, or path form unavailable
            elif ref is not None:
                chosen = "path"
            else:
                self.modality_errors[modality] = ref_err or mem_err
                log.warning("%s modality unavailable: %s", modality, self.modality_errors[modality])
                continue
            self.input_forms[modality] = chosen
            self.modalities.add(modality)

    def _as_path_input(self, modality: str, payload) -> dict:
        """Write a payload to a temp file and return the documented path-style input."""
        tmp_dir = self.settings.index_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=tmp_dir, suffix=".png" if modality == "image" else ".wav")
        os.close(fd)
        self._tmp_files.append(name)
        if modality == "image":
            payload.convert("RGB").save(name, "PNG")
            return {"image": name}
        _write_wav(name, payload, AUDIO_RATE)
        return {"audio": name}

    def _cleanup_tmp(self) -> None:
        while self._tmp_files:
            try:
                os.unlink(self._tmp_files.pop())
            except OSError:
                pass

    def _media_inputs(self, modality: str, payloads: Sequence) -> list:
        if self.input_forms.get(modality, "path") == "memory":
            if modality == "image":
                return [{"image": p} for p in payloads]
            return [{"audio": audio_input(p, AUDIO_RATE)} for p in payloads]
        return [self._as_path_input(modality, p) for p in payloads]

    # ---------------------------------------------------------------- encoding
    @property
    def ready(self) -> bool:
        return self.state == "ready" and self._model is not None

    def _require(self):
        if not self.ready:
            raise ModelNotReady(self.error or f"Model is {self.state}")
        return self._model

    @staticmethod
    def _validate(vecs: Any, n: int) -> np.ndarray:
        arr = np.asarray(vecs, dtype=np.float32)
        if arr.ndim != 2 or arr.shape != (n, EXPECTED_DIM):
            raise RuntimeError(f"Expected ({n}, {EXPECTED_DIM}) embeddings, got {arr.shape}")
        if not np.isfinite(arr).all():
            raise RuntimeError("Model produced non-finite embeddings")
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        if (norms < 1e-6).any():
            raise RuntimeError("Model produced zero-length embeddings")
        return arr / norms

    def _encode_with(self, model, fn_name: str, inputs: list, convert=None) -> np.ndarray:
        """Batch, encode, validate. `convert` maps a batch of raw payloads to model inputs."""
        import torch

        fn = getattr(model, fn_name)
        batch = max(1, self.settings.embed_batch_size)
        out: list[np.ndarray] = []
        with self._encode_lock, torch.inference_mode():
            i = 0
            while i < len(inputs):
                chunk = inputs[i : i + batch]
                try:
                    model_inputs = convert(chunk) if convert else chunk
                    vecs = fn(model_inputs, batch_size=len(chunk), convert_to_numpy=True, show_progress_bar=False)
                except torch.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    if batch == 1:
                        raise
                    batch = max(1, batch // 2)
                    log.warning("CUDA OOM; retrying with batch size %d", batch)
                    continue
                finally:
                    self._cleanup_tmp()
                out.append(self._validate(vecs, len(chunk)))
                i += len(chunk)
        return np.vstack(out) if out else np.zeros((0, EXPECTED_DIM), dtype=np.float32)

    def _encode(self, fn_name: str, inputs: list, convert=None) -> np.ndarray:
        return self._encode_with(self._require(), fn_name, inputs, convert)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        """Natural-language search queries (uses the model's `query` task prompt)."""
        return self._encode("encode_query", list(texts))

    def embed_query_image(self, image) -> np.ndarray:
        """A reference image used as a query (image-to-anything search)."""
        self._require_modality("image")
        return self._encode("encode_query", [image], lambda b: self._media_inputs("image", b))

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        """Document text chunks (uses the `document` task prompt)."""
        return self._encode("encode_document", list(texts))

    def embed_images(self, images: Sequence) -> np.ndarray:
        """Photos, rendered PDF pages, embedded pictures and sampled video frames."""
        self._require_modality("image")
        return self._encode("encode_document", list(images), lambda b: self._media_inputs("image", b))

    def embed_audio(self, clips: Sequence[np.ndarray]) -> np.ndarray:
        """16 kHz mono float32 audio windows."""
        self._require_modality("audio")
        return self._encode("encode_document", list(clips), lambda b: self._media_inputs("audio", b))

    def _require_modality(self, m: str) -> None:
        self._require()
        if m not in self.modalities:
            reason = self.modality_errors.get(m, "encoder not available")
            raise RuntimeError(f"Model cannot embed {m}: {reason}")

    def embed_units(self, modality: str, payloads: list) -> np.ndarray:
        if modality == "text":
            return self.embed_texts(payloads)
        if modality == "image":
            return self.embed_images(payloads)
        if modality == "audio":
            return self.embed_audio(payloads)
        raise ValueError(modality)

    def status(self) -> dict:
        return {
            "model_id": self.model_id,
            "state": self.state,
            "error": self.error,
            "device": self.device,
            "dtype": self.dtype,
            "gpu": self.gpu_name,
            "modalities": sorted(self.modalities),
            "modality_errors": self.modality_errors,
            "input_forms": self.input_forms,
            "load_seconds": self.load_seconds,
            "embedding_dim": EXPECTED_DIM,
        }


def audio_input(samples: np.ndarray, rate: int) -> dict:
    """In-memory audio candidate form (only used if the probe proves it equals the path form)."""
    return {"array": np.asarray(samples, dtype=np.float32), "sampling_rate": rate}


def _write_wav(path: str, samples: np.ndarray, rate: int) -> None:
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def _probe_image():
    from PIL import Image

    x = np.linspace(0, 255, 96, dtype=np.uint8)
    arr = np.stack([np.tile(x, (96, 1)), np.tile(x[:, None], (1, 96)), np.full((96, 96), 128, np.uint8)], axis=-1)
    return Image.fromarray(arr, "RGB")


def _probe_audio() -> np.ndarray:
    t = np.arange(AUDIO_RATE) / AUDIO_RATE
    rng = np.random.default_rng(0)
    return (0.3 * np.sin(2 * np.pi * 440 * t) + 0.02 * rng.standard_normal(AUDIO_RATE)).astype(np.float32)
