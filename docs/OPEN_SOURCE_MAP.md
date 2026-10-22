# Open-source integration map

Where every open-source model and library is used in MediaTrace — precise enough to open the file in VS Code and
show the line. Line numbers refer to the repository as of this document's commit.

**Ownership.** Everything under `backend/app/`, `frontend/src/`, `scripts/` and `tests/` is original MediaTrace
application code (MIT, see [`LICENSE`](../LICENSE)). The model weights and the libraries below are third-party
work used as dependencies; they are not part of our source tree and keep their own licenses
(see [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)). No third-party source code is copied into this repo.

"Runtime-tested" refers to checks actually run on the reference machine (RTX 5050 Laptop GPU, Python 3.10.11,
torch 2.11.0+cu128): `pytest` (25 passed), `scripts/verify_model.py`, `scripts/evaluate.py` (19 labelled
queries) and a live-server API session.

## 1. The open-weight model — `google/embeddinggemma-2`

| | |
|---|---|
| Model | [`google/embeddinggemma-2`](https://huggingface.co/google/embeddinggemma-2) (local snapshot `914f7f89142e33e77833254d9c9b90c3cef7303b`) |
| License | **Apache-2.0** — `license: apache-2.0` in the model card front matter (verified in the cached `README.md`) |
| What it gives us | One shared **768-dimensional** embedding space for text, images and audio (the card also lists video) |
| Weights | `model.safetensors`, 1,488,915,288 bytes, loaded from the local Hugging Face cache; never committed |

The **only** module that touches the model is [`backend/app/model_service.py`](../backend/app/model_service.py):

| What | Where | Concrete behaviour | Runtime-tested |
|---|---|---|---|
| Load the model once | `ModelService.load()` — `SentenceTransformer(self.model_id, device=device, model_kwargs={"torch_dtype": dtype})` at **lines 85–89** | Loads `google/embeddinggemma-2` with all encoders (text, vision, audio) | ✅ loads in 11–25 s on CUDA |
| GPU + dtype policy | `ModelService._select_device()` **lines 52–71** | Checks `torch.cuda.get_device_capability` against `torch.cuda.get_arch_list()` (sm_120 for RTX 50-series); **bfloat16** if supported else float32; **never float16** (model-card warning) | ✅ `cuda`, `bfloat16`, ~1.5 GB VRAM peak |
| Verify modalities with real forward passes | `ModelService._probe()` **lines 112–155** | Text self-test via `encode_query`; image + audio probes via `encode_document`; a modality is enabled only if it returns valid vectors | ✅ text, image, audio all pass |
| Search queries | `ModelService.embed_queries()` **line 236** → `model.encode_query(...)` | Applies the model's `query` task prompt (`task: search result \| query:`) | ✅ |
| Documents / pages / frames / audio | `embed_texts()` **245**, `embed_images()` **249**, `embed_audio()` **254** → `model.encode_document(...)` | Text chunks as strings, images as `{"image": PIL.Image}`, audio as `{"audio": {"array": float32, "sampling_rate": 16000}}` | ✅ |
| Reference-image query | `embed_query_image()` **line 240** | Image goes through `encode_query` for image-to-anything search | ✅ live API: bear photo → `bear.jpg` + same picture inside a PPTX slide |
| Output validation | `ModelService._validate()` **lines 195–204** | Asserts shape `(n, 768)`, finite values, non-zero norm; L2-normalises | ✅ |
| OOM handling | `ModelService._encode_with()` **lines 206–231** | `torch.OutOfMemoryError` → empty cache, halve batch, retry | ⚠️ code path not triggered in tests |

Where the model's vectors are consumed (original code):

| Step | Where |
|---|---|
| Units → embeddings during indexing | [`backend/app/indexer.py`](../backend/app/indexer.py) `Indexer.index_file()` → `flush()` → `self.model.embed_units(...)` (**line 308**) |
| Vectors persisted as float32 BLOBs | [`backend/app/db.py`](../backend/app/db.py) `Database.replace_items()` **line 149**; loaded by `load_vectors()` **line 191** (`np.frombuffer`) |
| Cosine-similarity retrieval | [`backend/app/search.py`](../backend/app/search.py) `VectorIndex.search()` — `sem = self.matrix[idx] @ qvec` **line 123** |
| Query embedding per request | [`backend/app/main.py`](../backend/app/main.py) `search()` route **line 412** → `s.model.embed_queries([q])` |
| Live model status for the UI | `main.py` `health()` **line 170** → `ModelService.status()`; shown in [`frontend/src/components/About.tsx`](../frontend/src/components/About.tsx) and the header pill in `frontend/src/App.tsx` |

**Video note.** EmbeddingGemma 2 also accepts native video input, but MediaTrace does **not** use it. Videos are
indexed as sampled frames (image embeddings, every 2 s) plus the audio track (audio embeddings, 5 s windows) so
each hit carries an exact timestamp — see `VideoAdapter.iter_units()` in `backend/app/adapters/media.py`.

## 2. Libraries

| Component | Exact package (version tested) | Role in MediaTrace | License (source) | Where it is integrated | Concrete call | Runtime-tested |
|---|---|---|---|---|---|---|
| Sentence Transformers | `sentence-transformers` 6.2.0 | Model loading, prompts, pooling, normalisation, multimodal input routing | Apache-2.0 ([repo](https://github.com/huggingface/sentence-transformers)) | `backend/app/model_service.py` `ModelService.load()` L85, `_encode_with()` L219 | `SentenceTransformer(...)`, `encode_query`, `encode_document` | ✅ |
| Hugging Face Transformers | `transformers` 5.20.2 | EmbeddingGemma2 architecture, tokenizer, image/audio processors (used through Sentence Transformers) | Apache-2.0 ([repo](https://github.com/huggingface/transformers)) | indirect, via `SentenceTransformer` in `model_service.py` | `EmbeddingGemma2Model` loaded from the snapshot | ✅ |
| huggingface_hub | `huggingface-hub` 2.2.0 | Resolves the model from the local cache (offline mode in `scripts/start-backend.ps1`) | Apache-2.0 ([repo](https://github.com/huggingface/huggingface_hub)) | indirect | snapshot resolution | ✅ offline |
| PyTorch + CUDA | `torch` 2.11.0+cu128 | Inference runtime on the RTX 5050 (sm_120), bf16 | BSD-3-Clause ([repo](https://github.com/pytorch/pytorch)) | `model_service.py` `_select_device()` L52–71, `_encode_with()` (`torch.inference_mode`) | `torch.cuda.is_bf16_supported()` | ✅ |
| FastAPI (+ Starlette, Pydantic, Uvicorn) | `fastapi` 0.159.1, `starlette` 1.7.0, `pydantic` 2.14.1, `uvicorn` 0.54.0 | Local HTTP API, validation, range-capable file streaming | MIT / BSD-3 / MIT / BSD-3 | `backend/app/main.py` `create_app()` L130; schemas in `backend/app/schemas.py` | `FastAPI(...)`, `FileResponse` (HTTP 206 range verified) | ✅ |
| SQLite | Python stdlib `sqlite3` | Persistent index: files, items (embeddings), jobs | Public domain ([sqlite.org](https://sqlite.org/copyright.html)) | `backend/app/db.py` `Database.__init__` L75 | `sqlite3.connect(...)`, WAL mode | ✅ survives restart |
| NumPy | `numpy` 2.2.6 | Vector matrix, cosine similarity, audio buffers | BSD-3-Clause | `backend/app/search.py`, `db.py` | `matrix @ qvec` | ✅ |
| pypdfium2 (PDFium) | `pypdfium2` 5.14.0 | Renders PDF pages to images (charts, diagrams, scans) | BSD-3-Clause / Apache-2.0 + bundled PDFium licenses | `backend/app/adapters/pdf.py` `PdfAdapter.iter_units()` L24, L45 | `pdfium.PdfDocument`, `page.render(...).to_pil()` | ✅ |
| pypdf | `pypdf` 6.21.2 | Selectable-text extraction per page | BSD-3-Clause | `backend/app/adapters/pdf.py` L28, L40 | `PdfReader(...).pages[i].extract_text()` | ✅ |
| Pillow | `pillow` 12.3.0 | Image decoding, EXIF rotation, thumbnails, waveform previews | MIT-CMU | `backend/app/adapters/image.py` L24; `adapters/base.py` `thumbnail()` | `ImageOps.exif_transpose` | ✅ |
| PyAV (FFmpeg 8.1.1) | `av` 17.1.0 | Video frame sampling, audio decode + resample to 16 kHz mono | BSD-3-Clause (PyAV); bundled FFmpeg reports *LGPL v3 or later* — see notices | `backend/app/adapters/media.py` `iter_audio_windows()` L62, `VideoAdapter.iter_units()` L159, `sample_frames()` L206 | `av.open`, `container.decode`, `av.AudioResampler` | ✅ |
| python-docx | `python-docx` 1.2.0 | Word paragraphs, headings, tables, inline pictures | MIT | `backend/app/adapters/office.py` `DocxAdapter.iter_units()` L46 | `docx.Document(...)` | ✅ |
| python-pptx | `python-pptx` 1.0.2 | Slide text, tables, notes, pictures + bounding boxes | MIT | `backend/app/adapters/office.py` `PptxAdapter.iter_units()` L135 | `Presentation(...)` | ✅ |
| openpyxl | `openpyxl` 3.1.5 | Excel sheets → header-aware row blocks with cell ranges | MIT | `backend/app/adapters/spreadsheet.py` `XlsxAdapter.iter_units()` L119 | `openpyxl.load_workbook(..., read_only=True)` | ✅ |
| React | `react` 19.3.1 | User interface | MIT | `frontend/src/App.tsx` and `frontend/src/components/*` | `runSearch()` → `api.search()` (`frontend/src/api.ts` L59) | ✅ production build; UI served via Vite |
| Vite | `vite` 8.3.5, `@vitejs/plugin-react` 6.1.2 | Dev server, `/api` proxy, production build | MIT | `frontend/vite.config.ts` | proxy `/api` → `127.0.0.1:8000` | ✅ |
| TypeScript | `typescript` 6.0.3 | Type-checked frontend | Apache-2.0 | `frontend/tsconfig*.json` | `tsc -b` in `npm run build` | ✅ |
| lucide-react | `lucide-react` 1.61.0 | Icons | ISC | `frontend/src/components/FamilyIcon.tsx` and others | icon components | ✅ build |
| pytest, httpx | `pytest` 9.1.1, `httpx` 0.28.1 | Test runner, FastAPI TestClient transport | MIT / BSD-3-Clause | `tests/` | `TestClient(create_app(...))` | ✅ 25 passed |

## 3. Demo data (not code, not committed)

| Asset | Source | License | Where used |
|---|---|---|---|
| 9 photographs | COCO val2017 (`images.cocodataset.org`) | CC BY 4.0 | downloaded at run time by `scripts/make_demo_corpus.py` |
| Speech clip | LibriSpeech sample via `huggingface.co/datasets/Narsil/asr_dummy` | CC BY 4.0 (LibriSpeech) | same script |
| Documents, spreadsheets, charts, diagram, beeps, synthetic clapping, test videos | generated by `scripts/make_demo_corpus.py` | ours (MIT) | same script |

## 4. What is *not* used

- No hosted AI API (no OpenAI/Gemini/Anthropic calls). `grep` of `backend/app` finds no outbound HTTP client usage;
  the frontend only calls its own relative `/api` path (`frontend/src/api.ts`).
- No OCR engine, no speech-to-text model, no Gemma 4 generative model.
- Native EmbeddingGemma 2 video input is not used (frames + audio track instead, see above).
