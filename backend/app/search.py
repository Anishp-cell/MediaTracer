"""Retrieval: cosine similarity over a NumPy matrix + optional BM25 keyword signal.

Scores are ranking signals, not probabilities. Semantic-only ranking is always
available; hybrid mode adds `keyword_weight * normalised_bm25` and reports both
components per result so the ranking stays transparent.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .db import Database

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    "a an and are as at be by find for from in is it of on or show me my the that this to where which with "
    "photo image picture video audio file document find moment section someone".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def locator_key(meta: dict) -> tuple:
    """Hits sharing this key point at the same place in the same source and are collapsed."""
    loc = meta["locator"]
    t = loc.get("type")
    if t == "pdf_page":
        return (meta["file_id"], "page", loc.get("page"))
    if t == "slide":
        return (meta["file_id"], "slide", loc.get("slide"), loc.get("bbox") and tuple(loc["bbox"]))
    if t == "video":
        return (meta["file_id"], meta["modality"], loc.get("start"))
    return (meta["file_id"], meta["id"])


@dataclass
class Hit:
    meta: dict
    score: float
    semantic: float
    keyword: float
    also_matched: list[str]


class VectorIndex:
    def __init__(self, db: Database, model_id: str):
        self.db = db
        self.model_id = model_id
        self._lock = threading.RLock()
        self.meta: list[dict] = []
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self._families = np.zeros(0, dtype=object)
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avg_len = 1.0

    def reload(self) -> None:
        meta, matrix = self.db.load_vectors(self.model_id)
        tf = []
        df: Counter = Counter()
        lengths = []
        for m in meta:
            toks = tokenize(f"{m['filename']} {m.get('text') or ''}")
            c = Counter(toks)
            tf.append(c)
            df.update(c.keys())
            lengths.append(len(toks))
        with self._lock:
            self.meta, self.matrix = meta, matrix
            self._families = np.array([m["family"] for m in meta], dtype=object)
            self._tf, self._df = tf, df
            self._avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0

    @property
    def size(self) -> int:
        return len(self.meta)

    def _bm25(self, q_tokens: list[str], idx: np.ndarray, k1: float = 1.2, b: float = 0.75) -> np.ndarray:
        n = max(len(self.meta), 1)
        out = np.zeros(len(idx), dtype=np.float32)
        if not q_tokens:
            return out
        for j, i in enumerate(idx):
            tf = self._tf[i]
            if not tf:
                continue
            dl = sum(tf.values())
            s = 0.0
            for t in q_tokens:
                f = tf.get(t)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self._avg_len))
            out[j] = s
        return out

    def search(
        self,
        qvec: np.ndarray,
        query_text: str | None,
        families: list[str] | None,
        limit: int,
        mode: str = "semantic",
        keyword_weight: float = 0.15,
        max_per_file: int = 3,
    ) -> list[Hit]:
        with self._lock:
            if not self.meta:
                return []
            idx = np.arange(len(self.meta))
            if families:
                idx = idx[np.isin(self._families, families)]
            if idx.size == 0:
                return []
            sem = self.matrix[idx] @ qvec.astype(np.float32)
            kw = np.zeros_like(sem)
            if mode == "hybrid" and query_text:
                raw = self._bm25(tokenize(query_text), idx)
                if raw.max() > 0:
                    kw = raw / raw.max()
            score = sem + (keyword_weight * kw if mode == "hybrid" else 0)
            order = np.argsort(-score)

            hits: list[Hit] = []
            seen: dict[tuple, Hit] = {}
            per_file: Counter = Counter()
            for o in order:
                i = int(idx[o])
                m = self.meta[i]
                key = locator_key(m)
                if key in seen:
                    seen[key].also_matched.append(m["kind"])
                    continue
                if per_file[m["file_id"]] >= max_per_file:
                    continue
                h = Hit(meta=m, score=float(score[o]), semantic=float(sem[o]), keyword=float(kw[o]), also_matched=[])
                seen[key] = h
                per_file[m["file_id"]] += 1
                hits.append(h)
                if len(hits) >= limit:
                    break
            return hits
