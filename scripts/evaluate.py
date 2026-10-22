"""Reproducible retrieval evaluation on the demo corpus.

    python scripts/make_demo_corpus.py
    python scripts/evaluate.py [--corpus data/demo_corpus] [--fresh]

Uses the real google/embeddinggemma-2 model and a separate index under data/eval.
Writes docs/EVALUATION.md and data/eval/results.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.main import Services  # noqa: E402

K = 5


def matches(hit: dict, target: dict) -> bool:
    if hit["filename"] != target["file"]:
        return False
    loc = hit["locator"]
    if "page" in target and loc.get("page") != target["page"]:
        return False
    if "slide" in target and loc.get("slide") != target["slide"]:
        return False
    if "sheet" in target and loc.get("sheet") != target["sheet"]:
        return False
    if "modality" in target and hit["modality"] != target["modality"]:
        return False
    if "t" in target:
        lo, hi = target["t"]
        t = loc.get("time", loc.get("start"))
        if t is None or not (lo <= t < hi):
            return False
    return True


def wait_job(svc: Services, job_id: str) -> dict:
    while True:
        j = svc.db.get_job(job_id)
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "demo_corpus"))
    ap.add_argument("--fresh", action="store_true", help="delete the eval index first")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    labels = json.loads((corpus / "labels.json").read_text(encoding="utf-8"))

    eval_dir = ROOT / "data" / "eval"
    if args.fresh and eval_dir.exists():
        shutil.rmtree(eval_dir)
    settings = Settings(data_dir=eval_dir)
    svc = Services(settings, load_model=False)
    t0 = time.time()
    svc.model.load()
    if not svc.model.ready:
        print("Model failed to load:", svc.model.error)
        return 1
    load_s = time.time() - t0
    print(f"Model ready in {load_s:.1f}s on {svc.model.device} ({svc.model.dtype}); modalities={sorted(svc.model.modalities)}")

    # ---------------------------------------------------------------- index
    files = sorted(p for p in corpus.rglob("*") if p.is_file() and ".download_cache" not in p.parts
                   and p.name != "labels.json")
    t0 = time.time()
    regs = [svc.indexer.register_local(p) for p in files]
    ids = [r.file_id for r in regs if r.action in ("new", "updated")]
    per_file = {}
    if ids:
        job = wait_job(svc, svc.indexer.submit(ids))
        print(job["message"])
    index_s = time.time() - t0
    for f in svc.db.list_files():
        per_file[f["filename"]] = {"status": f["status"], "items": f["item_count"], "error": f["error"]}

    # Re-registration must reuse the index for unchanged files.
    t0 = time.time()
    again = [svc.indexer.register_local(p) for p in files]
    reuse_s = time.time() - t0
    reuse = {a: sum(1 for r in again if r.action == a) for a in {r.action for r in again}}

    # ------------------------------------------------------------- queries
    svc.model.embed_queries(["warm up"])
    rows = []
    summary = {}
    for mode in ("semantic", "hybrid"):
        recalls, hit1, rr, lat = [], [], [], []
        for q in labels["queries"]:
            t0 = time.perf_counter()
            qv = svc.model.embed_queries([q["query"]])[0]
            hits = svc.index.search(qv, q["query"], None, 10, mode)
            lat.append((time.perf_counter() - t0) * 1000)
            hit_dicts = [dict(h.meta) for h in hits]
            found = [any(matches(h, t) for h in hit_dicts[:K]) for t in q["relevant"]]
            first = next((i for i, h in enumerate(hit_dicts) if any(matches(h, t) for t in q["relevant"])), None)
            recalls.append(sum(found) / len(found))
            hit1.append(1.0 if first == 0 else 0.0)
            rr.append(1.0 / (first + 1) if first is not None else 0.0)
            rows.append({
                "mode": mode, "query": q["query"], "recall@5": sum(found) / len(found), "first_relevant_rank": (first + 1) if first is not None else None,
                "top3": [f"{h['filename']} [{h['kind']}] {fmt_loc(h['locator'])} ({s.semantic:.3f})" for h, s in zip(hit_dicts[:3], hits[:3])],
                "note": q.get("note"),
            })
        summary[mode] = {
            "recall@5": round(statistics.mean(recalls), 3), "hit@1": round(statistics.mean(hit1), 3),
            "mrr": round(statistics.mean(rr), 3), "latency_ms_median": round(statistics.median(lat), 1),
            "latency_ms_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1),
        }

    # ------------------------------------------------------ calibration
    # Raw cosine distributions per embedded modality: best relevant item per
    # query vs every non-relevant item. Used to set the UI strength bands.
    import numpy as np

    rel_best: dict[str, list[float]] = {}
    nonrel: dict[str, list[float]] = {}
    for q in labels["queries"]:
        qv = svc.model.embed_queries([q["query"]])[0]
        sims = svc.index.matrix @ qv
        best: dict[str, float] = {}
        for m, s in zip(svc.index.meta, sims):
            if any(matches(m, t) for t in q["relevant"]):
                best[m["modality"]] = max(best.get(m["modality"], -1.0), float(s))
            elif not any(m["filename"] == t["file"] for t in q["relevant"]):
                nonrel.setdefault(m["modality"], []).append(float(s))
        for mod, s in best.items():
            rel_best.setdefault(mod, []).append(s)
    calibration = {}
    for mod in sorted(set(rel_best) | set(nonrel)):
        r, n = np.array(rel_best.get(mod, [])), np.array(nonrel.get(mod, []))
        calibration[mod] = {
            "relevant_n": int(r.size), "relevant_min": round(float(r.min()), 3) if r.size else None,
            "relevant_median": round(float(np.median(r)), 3) if r.size else None,
            "nonrelevant_n": int(n.size), "nonrelevant_p95": round(float(np.percentile(n, 95)), 3) if n.size else None,
            "nonrelevant_max": round(float(n.max()), 3) if n.size else None,
        }

    # ------------------------------------------------------- robustness
    bad_dir = eval_dir / "bad_inputs"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "corrupt.pdf").write_bytes(b"%PDF-1.4\nthis is not really a pdf")
    (bad_dir / "not_an_image.jpg").write_text("plain text pretending to be a JPEG")
    (bad_dir / "empty.txt").write_text("")
    (bad_dir / "corrupt.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    (bad_dir / "archive.xyz").write_text("unsupported")
    robustness = []
    bad_regs = [svc.indexer.register_local(p) for p in sorted(bad_dir.iterdir())]
    bad_ids = [r.file_id for r in bad_regs if r.action in ("new", "updated")]
    if bad_ids:
        wait_job(svc, svc.indexer.submit(bad_ids))
    for r in bad_regs:
        f = svc.db.get_file(r.file_id) if r.file_id else None
        robustness.append({"file": r.filename, "registration": r.action,
                           "outcome": f["status"] if f else r.action, "message": (f or {}).get("error") or r.reason})
    for r in bad_regs:
        if r.file_id:
            svc.indexer.remove_file(r.file_id)

    results = {
        "model": svc.model.status(), "model_load_s": round(load_s, 1), "index_seconds": round(index_s, 1),
        "reindex_check_seconds": round(reuse_s, 2), "reuse": reuse, "files": per_file, "summary": summary,
        "queries": rows, "robustness": robustness, "indexed_items": svc.index.size, "calibration": calibration,
        "video_codec": labels.get("video_codec"),
    }
    (eval_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results, ROOT / "docs" / "EVALUATION.md")
    print(json.dumps(summary, indent=2))
    svc.close()
    return 0


def fmt_loc(loc: dict) -> str:
    t = loc.get("type")
    if t == "pdf_page":
        return f"p.{loc['page']}"
    if t == "slide":
        return f"slide {loc['slide']}"
    if t in ("video", "audio"):
        return f"{loc['start']:.1f}-{loc['end']:.1f}s"
    if t == "sheet":
        return f"{loc.get('sheet') or ''} {loc['cell_range']}".strip()
    if t == "text":
        return f"L{loc['line_start']}-{loc['line_end']}"
    if t == "docx":
        return f"table {loc['table']}" if loc.get("table") else f"para {loc['paragraph_start']}-{loc['paragraph_end']}"
    return ""


def write_report(r: dict, path: Path) -> None:
    m = r["model"]
    lines = [
        "# MediaTrace evaluation", "",
        "Generated by `scripts/evaluate.py` on the corpus from `scripts/make_demo_corpus.py`. "
        "All numbers below come from an actual run; rerun the scripts to reproduce them.", "",
        "## Setup", "",
        f"- Model: `{m['model_id']}` on **{m['device']}** ({m['dtype']}), GPU: {m['gpu'] or 'n/a'}, "
        f"modalities: {', '.join(m['modalities'])}",
        f"- Model load time: {r['model_load_s']} s",
        f"- Corpus: {len(r['files'])} files → {r['indexed_items']} searchable units; video codec `{r['video_codec']}`",
        f"- Full indexing time (cold): {r['index_seconds']} s",
        f"- Re-registration of the unchanged corpus: {r['reindex_check_seconds']} s, outcome {r['reuse']} "
        "(no re-embedding)", "",
        "## Retrieval quality", "",
        "Each query has manually labelled relevant targets (file, and where applicable page / slide / sheet / "
        "time range / modality). Most queries have only 1–2 relevant targets, so Precision@5 is not meaningful "
        "and is not reported; Recall@5 is the fraction of labelled targets that appear in the top 5.", "",
        "| Mode | Recall@5 | Hit@1 | MRR | Median latency | p95 latency |", "|---|---|---|---|---|---|",
    ]
    for mode, s in r["summary"].items():
        lines.append(f"| {mode} | {s['recall@5']} | {s['hit@1']} | {s['mrr']} | {s['latency_ms_median']} ms | "
                     f"{s['latency_ms_p95']} ms |")
    lines += ["", "Latency = query embedding + similarity search, model already loaded.", "",
              "## Per-query results (semantic)", "", "| Query | Recall@5 | First relevant rank | Top 3 |", "|---|---|---|---|"]
    for q in r["queries"]:
        if q["mode"] != "semantic":
            continue
        top = "<br>".join(q["top3"])
        note = f" *({q['note']})*" if q.get("note") else ""
        lines.append(f"| {q['query']}{note} | {q['recall@5']:.2f} | {q['first_relevant_rank'] or '—'} | {top} |")
    lines += ["", "## Semantic vs hybrid (queries whose rank changed)", "", "| Query | Semantic rank | Hybrid rank |", "|---|---|---|"]
    sem = {q["query"]: q["first_relevant_rank"] for q in r["queries"] if q["mode"] == "semantic"}
    changed = False
    for q in r["queries"]:
        if q["mode"] == "hybrid" and q["first_relevant_rank"] != sem[q["query"]]:
            changed = True
            lines.append(f"| {q['query']} | {sem[q['query']] or '—'} | {q['first_relevant_rank'] or '—'} |")
    if not changed:
        lines.append("| (no query changed rank) | | |")
    lines += ["", "## Score calibration (raw cosine, per embedded modality)", "",
              "Best-scoring relevant item per query vs. every item from a non-relevant file. EmbeddingGemma 2 "
              "gives unrelated items fairly high cosine scores (~0.5–0.7), so absolute scores must not be read as "
              "confidence; the UI strength bands are set from these numbers.", "",
              "| Embedded modality | Relevant (n) | Relevant min | Relevant median | Non-relevant (n) | Non-relevant p95 | Non-relevant max |",
              "|---|---|---|---|---|---|---|"]
    for mod, c in r["calibration"].items():
        lines.append(f"| {mod} | {c['relevant_n']} | {c['relevant_min']} | {c['relevant_median']} | "
                     f"{c['nonrelevant_n']} | {c['nonrelevant_p95']} | {c['nonrelevant_max']} |")
    lines += ["", "## Indexed files", "", "| File | Status | Units | Error |", "|---|---|---|---|"]
    for name, f in sorted(r["files"].items()):
        lines.append(f"| {name} | {f['status']} | {f['items']} | {f['error'] or ''} |")
    lines += ["", "## Unsupported / corrupt input handling", "", "| File | Registration | Outcome | Message |", "|---|---|---|---|"]
    for b in r["robustness"]:
        lines.append(f"| {b['file']} | {b['registration']} | {b['outcome']} | {b['message'] or ''} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
