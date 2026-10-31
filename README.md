# MediaTrace

**Search by what you remember, not by where you saved it.**

You remember *what* was in a file — a diagram, a moment in a video, a sound, a number in a spreadsheet —
but search tools want the *filename*. MediaTrace is a **local-first multimodal semantic search engine**: describe
what you remember in plain language and it returns ranked, verifiable evidence from your photos, PDFs, Word
and PowerPoint files, text notes, spreadsheets, videos and audio — with the exact **page, slide, paragraph, cell
range or timestamp**, a preview, and a link that opens the original at that place.

**Core Technology:** Google's **[EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2)**
(`google/embeddinggemma-2`, Apache-2.0) embeds text, images and audio into a single 768-dimensional space, so one
query searches every media type at once — and every hit carries real provenance instead of a generated answer.
Everything runs locally; no file ever leaves your device.

---

## 📱 MediaTrace for Mobile (Android & Google Play)

MediaTrace is coming directly to your phone as a **daily-use, privacy-first mobile companion**.

Most phone galleries are cluttered with thousands of photos, screenshots, and videos that are impossible to find when you need them. Standard gallery search forces you to remember dates, albums, or exact file names. MediaTrace replaces endless scrolling with **instant, natural recall** — just describe what you remember, and your phone finds it in milliseconds.

### ✨ Key Features for Daily Use

* 🔍 **Search by What You Remember:**  
  Type in plain everyday language. Search for *"cat sleeping in a shoebox"*, *"receipt on blue paper from the bicycle shop"*, *"mom laughing at the dinner table"*, or *"whiteboard diagram from work"*. You never have to tag a photo manually.

* ⏱️ **Jump Straight to the Exact Moment in Videos:**  
  No more scrubbing through a 10-minute video to find a 5-second highlight. Search *"blowing out birthday candles"* or *"dog jumping into water"*, and MediaTrace opens the video directly at that exact second.

* 🗣️ **One-Tap Voice Search:**  
  Hands full? Just tap the microphone and speak your query naturally: *"show me sunset photos from our summer trip"*.

* 📁 **Smart Living Albums:**  
  Create dynamic albums defined by meaning rather than dates. Type *"Healthy recipes"*, *"Concerts"*, or *"Coffee shop moments"*, and MediaTrace keeps that album continuously updated as you capture new media.

* 👥 **People & Face Grouping:**  
  Group your memories by the people who matter most. Tap a friend or family member's face to see every photo and video with them, or search *"Alex playing tennis"*.

* 📍 **Location & Landmark Search:**  
  Search by places or landmarks (*"photos in Paris"*, *"beach holiday"*, *"mountain hike"*), with an interactive map view of your photo history.

* 🔄 **Reverse Image Search & Share Integration:**  
  See a picture in WhatsApp, Instagram, or a web browser? Tap Android's **Share** button and send it to MediaTrace to instantly find similar photos or original high-res versions in your library.

* 🧹 **One-Tap Duplicate & Clutter Cleaner:**  
  Free up phone storage effortlessly. MediaTrace spots burst shots, duplicate downloads, and repeated WhatsApp memes so you can declutter in one tap.

* ⚡ **Home Screen Quick Search Widget:**  
  Search your personal media library or tap the voice mic directly from your home screen without even launching the full app.

* 🔒 **100% Private, Completely Offline:**  
  Your personal memories never leave your device. No accounts, no cloud uploads, no subscriptions, and zero tracking. Search works anywhere, even in airplane mode.

* 🔋 **Battery-Smart Background Scanning:**  
  New photos are indexed quietly in the background without draining your battery. Heavy scanning automatically pauses when you're using your phone and resumes when plugged in.

### 🗺️ Mobile Rollout Plan

* **Version 1.0 (Google Play Store):**  
  Full focus on your daily **Phone Gallery & Camera Roll** (Photos + Videos) with instant semantic search, video moments, voice search, face grouping, smart albums, home screen widget, and storage cleaner.
* **Version 2.0 (Expansion):**  
  Expanding search to **all phone files** — PDF documents, notes, spreadsheets, voice notes, WhatsApp chat media folders, and Google Drive cloud storage.

---

## How it works

```
 file ─▶ adapter (per format) ─▶ Units: payload (text | image | audio) + source locator + preview
                                   │
                                   ▼
          ModelService (EmbeddingGemma 2 via Sentence Transformers)
          queries → encode_query · units → encode_document · validate (768-d, finite, L2-normalised)
                                   │
                                   ▼
          SQLite (files, items with float32 embedding BLOBs, jobs)  +  in-memory NumPy matrix
                                   │
 query ─▶ encode_query ─▶ cosine similarity (+ optional BM25 keyword boost) ─▶ de-duplicate by location
                                   │
                                   ▼
          FastAPI JSON (filename, location label, match type, strength, preview/open URLs) ─▶ Client UI
```

| Path | Responsibility |
|---|---|
| `backend/app/model_service.py` | Model loading, device/dtype policy, modality probe, batching, OOM back-off, validation |
| `backend/app/adapters/` | Family adapters: `image.py`, `pdf.py`, `office.py` (DOCX/PPTX), `text.py`, `spreadsheet.py` (CSV/XLSX), `media.py` (video/audio via PyAV) |
| `backend/app/indexer.py` | SHA-256 fingerprints, background job queue with progress/cancel, atomic per-file swap, resume after restart |
| `backend/app/db.py` | SQLite schema and persistence |
| `backend/app/search.py` | NumPy cosine similarity, optional BM25, per-location de-duplication |
| `backend/app/main.py` | FastAPI routes, uploads, streaming, result shaping, strength labels |
| `frontend/src/` | React + TypeScript web client (`App.tsx`, `components/`) |

### Supported formats

| Family | Formats | Indexed as | Source locator |
|---|---|---|---|
| Images | JPG, JPEG, PNG, WebP | the image | image + size |
| PDF | PDF | each page rendered as an image **and** its selectable-text chunks | page *n* of *N* |
| Word | DOCX | paragraph chunks, inline pictures, tables | heading + paragraph range / table rows |
| PowerPoint | PPTX | slide text, tables, notes; pictures | slide *n* + title; picture bounding box |
| Text | TXT, MD | line-aligned chunks | line range + Markdown section |
| Spreadsheets | CSV, XLSX | header-aware row blocks | sheet, row range, cell range |
| Video | MP4, MOV, WebM, MKV | a frame every 2 s (≤600 frames) + audio track in 5 s windows | start–end time |
| Audio | WAV, MP3, M4A, FLAC, OGG | 5 s windows, 2.5 s hop, 16 kHz mono; silence skipped | start–end time |

---

## Configuration (Environment Variables)

| Variable | Default | Meaning |
|---|---|---|
| `MEDIATRACE_DATA_DIR` | `./data` | uploads, SQLite index, previews |
| `MEDIATRACE_DEVICE` | `auto` | `auto`, `cuda` or `cpu` |
| `MEDIATRACE_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS origins |
| `MEDIATRACE_MAX_UPLOAD_MB` | `512` | per-file upload limit |
| `MEDIATRACE_VIDEO_SAMPLE_SECONDS` / `_MAX_FRAMES` | `2.0` / `600` | video frame sampling |
| `MEDIATRACE_AUDIO_WINDOW_SECONDS` / `_HOP_SECONDS` | `5.0` / `2.5` | audio window sampling |
| `MEDIATRACE_EMBED_BATCH_SIZE` | `8` | batch size for embedding units |
| `MEDIATRACE_STRENGTH_BANDS` | see `backend/app/main.py` | JSON thresholds for strong / possible / weak match labels |

---

## API Reference

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Model state, device, dtype, verified modalities, index size |
| `GET /api/capabilities` | Adapters usable in the current environment, accepted extensions |
| `POST /api/index` · `POST /api/index/local` · `POST /api/files/rescan` | Upload files · index local files/folders in place · re-check files |
| `GET /api/jobs/{id}` · `POST /api/jobs/{id}/cancel` | Indexing progress / job cancellation |
| `POST /api/search` · `POST /api/search/image` | Text query search · reference-image search |
| `POST /api/items/{id}/refine` | Fine-grained frame search around a video hit |
| `GET /api/files` · `DELETE /api/files/{id}` · `POST /api/files/{id}/reindex` | Collection management (originals are never deleted) |
| `GET /api/files/{id}/original` · `/stream` · `GET /api/items/{id}/preview` | Original file access, HTTP Range audio/video streaming, previews |

---

## Known limitations

- **Audio retrieval**: Relevant audio windows score within narrower margins than visual content; audio hits are ranked as candidate matches.
- **Strength labels**: Thresholds are calibrated hints for match confidence, not exact statistical probabilities.
- **Video representation**: Video is indexed via timestamped visual keyframes and audio intervals.
- **In-memory search matrix**: Designed for personal collections (tens of thousands of media units).

---

## Attribution & Intellectual Property

- **MediaTrace Application:** Copyright © 2026 MediaTrace. All rights reserved. Proprietary software.
- **Foundation Model:** `google/embeddinggemma-2` — Apache-2.0 per Google's [model card](https://huggingface.co/google/embeddinggemma-2). Weights are downloaded directly by the user and are never bundled or redistributed.
- **Third-Party Notices:** See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## AI Disclosure

- Indexing and search are powered entirely on-device by locally running multimodal embedding models. No external cloud inference or hosted third-party models are utilized.
