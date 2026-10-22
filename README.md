# MediaTrace

**Search by what you remember, not by where you saved it.**

You remember *what* was in a file — a diagram, a moment in a video, a beeping sound, a number in a spreadsheet —
but search tools want the *filename*. MediaTrace is a **local-first multimodal semantic search engine**: describe
what you remember in plain language and it returns ranked, verifiable evidence from your own photos, PDFs, Word
and PowerPoint files, text notes, spreadsheets, videos and audio — with the exact **page, slide, paragraph, cell
range or timestamp**, a preview, and a link that opens the original at that place.

**Differentiator:** one open-weight model, Google's **[EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2)**
(`google/embeddinggemma-2`, Apache-2.0), embeds text, images and audio into a single 768-dimensional space, so one
query searches every media type at once — and every hit carries real provenance instead of a generated answer.
Everything runs on your machine; no file leaves it.

- **Where the model is integrated:** [`docs/OPEN_SOURCE_MAP.md`](docs/OPEN_SOURCE_MAP.md) (file + line for every component)
- **Licenses:** MediaTrace code — [MIT](LICENSE) · model — Apache-2.0 · dependencies — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- **3-minute demo script:** [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) · **Evaluation:** [`docs/EVALUATION.md`](docs/EVALUATION.md)

---

## Verified features

Verified on the reference machine (Windows 11, NVIDIA RTX 5050 Laptop GPU, Python 3.10.11,
torch 2.11.0+cu128, sentence-transformers 6.2.0, transformers 5.20.2) by the automated tests, the evaluation
script and a live-server session. See [Test results](#test-results).

| Feature | Status | Evidence |
|---|---|---|
| EmbeddingGemma 2 loads on GPU in **bfloat16** (never float16), ~1.5 GB VRAM | ✅ verified | `scripts/verify_model.py`, `/api/health` |
| Real forward-pass check of **text, image and audio** at startup; only passing modalities are enabled | ✅ verified (all 3 pass) | `ModelService._probe()` |
| Text search (documents, slides, spreadsheets, notes) | ✅ verified | evaluation: deadline (DOCX), revenue (XLSX), stock (CSV), GPU + recipe (MD) queries all hit@1 |
| Image search (photos, PDF page images, pictures inside DOCX/PPTX) | ✅ verified | evaluation: 6 photo queries + PDF diagram/chart queries all hit@1 |
| Video search by sampled frames, timestamped; segment playback; *Find exact moment* refinement | ✅ verified | API test (blue scene 8–12 s), evaluation (stop sign 0–4 s, skier 4–8 s, baseball 8–12 s all hit@1) |
| Audio search by 5 s windows (and the audio track of videos) | ✅ verified, **weak margins** | evaluation: speech, alarm, synthetic clapping queries hit@1, but scores close to non-relevant items |
| Reference-image search (image → anything) | ✅ verified | live API: bear photo → `bear.jpg` and the same picture inside a PPTX slide |
| Provenance: PDF page, slide (+picture box), DOCX heading/paragraphs, sheet + cell range, line range, start–end time | ✅ verified | adapter tests assert exact locators |
| Open original at location (PDF `#page=N`; audio/video Range streaming, HTTP 206) | ✅ verified (HTTP level) | API tests |
| Persistent SQLite index; survives restart without re-indexing | ✅ verified | API test + live restart (19 files / 48 units restored) |
| Fingerprinting: unchanged files skipped, changed files re-indexed, duplicates detected | ✅ verified | API tests, evaluation (`unchanged: 19`) |
| Clear errors for unsupported, empty, corrupt files and missing paths | ✅ verified | evaluation robustness table, API tests |
| Local-first: no outbound calls from app code; model runs from local cache offline | ✅ verified (code audit + offline runs) | `start-backend.ps1` sets `HF_HUB_OFFLINE=1` when cached |
| React UI (search, filters, results, detail view, collection, add media, *AI model & open source* panel) | ✅ builds; served & proxied correctly | `npm run build`; visual click-through **not automated** — rehearse once |

## How it works

```
 file ─▶ adapter (per format) ─▶ Units: payload (text | image | audio) + source locator + preview
                                   │
                                   ▼
          ModelService (EmbeddingGemma 2 via Sentence Transformers, CUDA bf16)
          queries → encode_query · units → encode_document · validate (768-d, finite, L2-normalised)
                                   │
                                   ▼
          SQLite (files, items with float32 embedding BLOBs, jobs)  +  in-memory NumPy matrix
                                   │
 query ─▶ encode_query ─▶ cosine similarity (+ optional BM25 keyword boost) ─▶ de-duplicate by location
                                   │
                                   ▼
          FastAPI JSON (filename, location label, match type, strength, preview/open URLs) ─▶ React UI
```

| Path | Responsibility |
|---|---|
| `backend/app/model_service.py` | the only code that touches EmbeddingGemma 2: load once, device/dtype policy, modality probe, batching, OOM back-off, validation |
| `backend/app/adapters/` | one adapter per family: `image.py`, `pdf.py`, `office.py` (DOCX/PPTX), `text.py`, `spreadsheet.py` (CSV/XLSX), `media.py` (video/audio via PyAV) |
| `backend/app/indexer.py` | SHA-256 fingerprints, background job queue with progress/cancel, atomic per-file swap, resume after restart |
| `backend/app/db.py` | SQLite schema and access |
| `backend/app/search.py` | NumPy cosine similarity, optional BM25, per-location de-duplication |
| `backend/app/main.py` | FastAPI routes, uploads, streaming, result shaping, strength labels |
| `frontend/src/` | React + TypeScript UI (`App.tsx`, `components/`) |

### Supported formats

| Family | Formats | Indexed as | Source locator |
|---|---|---|---|
| Images | JPG, JPEG, PNG, WebP | the image | image + size |
| PDF | PDF | each page rendered as an image **and** its selectable-text chunks | page *n* of *N* |
| Word | DOCX | paragraph chunks, inline pictures, tables | heading + paragraph range / table rows (no invented page numbers) |
| PowerPoint | PPTX | slide text, tables, notes; pictures | slide *n* + title; picture bounding box |
| Text | TXT, MD | line-aligned chunks | line range + Markdown section |
| Spreadsheets | CSV, XLSX | header-aware row blocks | sheet, row range, cell range |
| Video | MP4, MOV, WebM, MKV | a frame every 2 s (≤600 frames) + audio track in 5 s windows | start–end time |
| Audio | WAV, MP3, M4A, FLAC, OGG | 5 s windows, 2.5 s hop, 16 kHz mono; silence skipped | start–end time |

Tested (adapter tests and/or the indexed demo corpus): JPG/JPEG, PNG, PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, MP4
(H.264 + AAC), WAV, FLAC. **Not individually tested:** WebP (Pillow path), MOV, WebM, MKV, MP3, M4A, OGG (same
PyAV decode path as the tested formats).

## Installation (Windows)

Requirements: Python 3.10+ (reference: 3.10.11), Node.js 20+, ~2 GB disk for the model. NVIDIA GPU optional;
RTX 50-series (sm_120) needs a CUDA 12.8+ PyTorch build.

```powershell
git clone <your-repo-url> MediaTrace
cd MediaTrace

py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
# PyTorch with CUDA 12.8 — use ONLY this index for torch (PyPI would give a CPU build)
.\.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
#   CPU-only machines:  .\.venv\Scripts\python -m pip install torch torchvision
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
.\.venv\Scripts\hf download google/embeddinggemma-2          # ~1.5 GB, once

cd frontend; npm install; cd ..
```

No `librosa` is required: audio is passed to the model in memory as
`{"array": waveform, "sampling_rate": 16000}`, a form documented by Sentence Transformers.

## Run it

Two PowerShell windows, from the repository root:

```powershell
.\scripts\start-backend.ps1      # API on http://127.0.0.1:8000 (interactive docs: /docs)
.\scripts\start-frontend.ps1     # UI on  http://localhost:5173
```

The model loads in the background (~12–25 s). The header pill shows **Loading EmbeddingGemma 2…** and turns into
**EmbeddingGemma 2 · GPU · bfloat16** when ready; searches are disabled until then and uploads made meanwhile are
queued. Stop either server with **Ctrl+C**. When the model is in the local cache, `start-backend.ps1` runs fully
offline (`HF_HUB_OFFLINE=1`).

### Demo data and a first search

```powershell
.\.venv\Scripts\python scripts\make_demo_corpus.py   # 19 files in data\demo_corpus (downloads 10 small CC BY files once)
.\scripts\seed-demo.ps1                               # indexes them through the running backend (~5 s)
```

Or in the UI: **Add media → "…or index a local folder in place"** → `D:\python\MediaTracer\data\demo_corpus` →
**Index folder**. Then try `the diagram showing convolutional layers` (→ `research_paper.pdf`, page 2),
`a person skiing` (→ `street_sports.mp4`, 0:04–0:08), `when is the report deadline`
(→ `meeting_notes.docx`, *Schedule*), `quarterly revenue by region` (→ `revenue_2025.xlsx`, `A2:F5`).

To present on a clean, separate index: `$env:MEDIATRACE_DATA_DIR="D:\python\MediaTracer\data\judge_demo"` before
`start-backend.ps1` (see [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)).

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MEDIATRACE_DATA_DIR` | `./data` | uploads, SQLite index, previews |
| `MEDIATRACE_DEVICE` | `auto` | `auto`, `cuda` or `cpu` |
| `MEDIATRACE_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS origins |
| `MEDIATRACE_MAX_UPLOAD_MB` | `512` | per-file limit |
| `MEDIATRACE_VIDEO_SAMPLE_SECONDS` / `_MAX_FRAMES` | `2.0` / `600` | video sampling |
| `MEDIATRACE_AUDIO_WINDOW_SECONDS` / `_HOP_SECONDS` | `5.0` / `2.5` | audio windows |
| `MEDIATRACE_EMBED_BATCH_SIZE` | `8` | GPU batch size (halved automatically on CUDA OOM) |
| `MEDIATRACE_STRENGTH_BANDS` | see `backend/app/main.py` | JSON thresholds for strong / possible / weak labels |

## API (used by the frontend)

| Method & path | Purpose |
|---|---|
| `GET /api/health` | model state, device, dtype, verified modalities, index size |
| `GET /api/capabilities` | adapters actually usable now, accepted extensions |
| `POST /api/index` · `POST /api/index/local` · `POST /api/files/rescan` | upload files · index files/folders in place · re-check local files |
| `GET /api/jobs/{id}` · `POST /api/jobs/{id}/cancel` | indexing progress / cancel |
| `POST /api/search` · `POST /api/search/image` | text query · reference-image query |
| `POST /api/items/{id}/refine` | fine-grained frame search around a video hit |
| `GET /api/files` · `DELETE /api/files/{id}` · `POST /api/files/{id}/reindex` | collection management (originals are never deleted) |
| `GET /api/files/{id}/original` · `/stream` · `GET /api/items/{id}/preview` | original file, Range streaming, previews |

Files are addressed by stable IDs only. The server binds to `127.0.0.1`; the local-folder endpoint reads paths you
give it, so do not expose the server to a network.

## Test results

All commands run from the repository root with `.venv`; results are from actual runs on the reference machine.

| Command | Result |
|---|---|
| `.\.venv\Scripts\python -m pytest -m "not model"` | **15 passed** (adapters, ~2 s) |
| `.\.venv\Scripts\python -m pytest` | **25 passed** (adapters + real-model + API end-to-end, ~29 s) |
| `.\.venv\Scripts\python scripts\verify_model.py` | text ✅ image ✅ audio ✅ on cuda/bfloat16; query latency ~48 ms |
| `.\.venv\Scripts\python scripts\evaluate.py --fresh` | 19 labelled queries: Recall@5 **1.0**, Hit@1 **1.0**, MRR **1.0**; median query latency **47–113 ms** across runs (varies with other GPU load) |
| `cd frontend; npm run build` | **success** (TypeScript check + Vite build) |

The evaluation corpus is small (19 files, deliberately distinct content), so perfect scores show the pipeline is
correct end to end — **not** that retrieval is perfect on real collections. [`docs/EVALUATION.md`](docs/EVALUATION.md)
also reports the raw score distributions: non-relevant items score 0.5–0.77, which is why results are labelled
"Strong / Possible / Weak" with calibrated thresholds rather than shown as percentages.

## Known limitations

- **Audio retrieval is weak**: relevant audio windows score only slightly above unrelated content (median relevant
  0.661 vs. non-relevant 95th percentile 0.652 on the demo set). Treat audio hits as candidates.
- **Strength labels** are calibrated on a small demo corpus; they are hints, not probabilities.
- **Mixed-family lists** can favour one modality because score scales differ; use the family filter chips.
- **Video** is frame-based (every 2 s) plus its audio track; EmbeddingGemma 2's native video input is not used.
- **No OCR** and **no speech transcription**: text inside images/scans is matched only visually; "where someone
  says X" relies on audio similarity, not words.
- **DOCX/PPTX/XLSX** cannot be shown inline by browsers — the UI offers a download and shows the exact location.
  PPTX slides are not rendered (no LibreOffice dependency).
- The search matrix is in memory; designed for personal collections (tens of thousands of units).
- The UI was verified by build, HTTP and API checks; an automated browser click-through was not run.

## Model, licenses and attribution

- **Model:** `google/embeddinggemma-2` — Apache-2.0 per its [model card](https://huggingface.co/google/embeddinggemma-2)
  (verified in the cached card's front matter). Weights are downloaded by the user and never committed.
- **MediaTrace source code:** [MIT](LICENSE) (original application code in `backend/app`, `frontend/src`,
  `scripts`, `tests`).
- **Dependencies:** see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (including an unresolved note on the
  FFmpeg build bundled with PyAV) and [docs/OPEN_SOURCE_MAP.md](docs/OPEN_SOURCE_MAP.md).
- **Demo data:** COCO val2017 images and a LibriSpeech sample (CC BY 4.0), downloaded at run time, git-ignored.

## AI tool disclosure

- **Coding assistant:** this project was built with substantial help from Claude Code (Anthropic), which wrote and
  debugged much of the backend, frontend, tests and documentation under the author's direction and review.
- **Hosted models in the product:** none. Indexing and search use only the locally running open-weight
  EmbeddingGemma 2 model.
