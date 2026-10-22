# MediaTrace — 3-minute judging script

Every query and expected result below was verified against the live API on the reference machine
(RTX 5050 Laptop GPU). The visual layout was **not** checked in a browser by the developer tooling — rehearse
the click path once before judging.

## Before the judges arrive (≈2 minutes, not part of the 3:00)

Open **three PowerShell windows** in `D:\python\MediaTracer` and VS Code on the repository.

```powershell
# Window 1 — backend on a fresh, demo-only data folder (your normal index is untouched)
$env:MEDIATRACE_DATA_DIR = "D:\python\MediaTracer\data\judge_demo"
.\scripts\start-backend.ps1
#   wait for:  "Loaded google/embeddinggemma-2 on cuda (bfloat16) ... modalities=['audio', 'image', 'text']"

# Window 2 — frontend
.\scripts\start-frontend.ps1          # then open http://localhost:5173 in the browser

# Window 3 — keep ready for the "local-first" moment
```

The demo corpus must already exist (`.\.venv\Scripts\python scripts\make_demo_corpus.py`, one time).
In the browser, confirm the header pill reads **"EmbeddingGemma 2 · GPU · bfloat16"** and the page shows
**"Your collection is empty"**. In VS Code, pre-open these tabs in this order:

1. `backend/app/model_service.py` (scroll to line 85)
2. `backend/app/search.py` (line 123)
3. `docs/OPEN_SOURCE_MAP.md`

## The 3 minutes

### 0:00–0:25 — The problem
*Say:* "We all remember **what** is in a file — a diagram, a moment in a video, a sound, a number in a
spreadsheet — but search tools want the **filename**. MediaTrace lets you search by what you remember, across
photos, PDFs, slides, spreadsheets, video and audio, and it shows you the exact page, slide, cell range or
timestamp as evidence."

### 0:25–0:55 — Solution and architecture
*Show:* the browser home page (headline **"Search by what you remember, not by where you saved it."**).
*Say:* "One open-weight model — Google's **EmbeddingGemma 2** — puts text, images and audio into the same
768-dimensional space. Independent adapters turn each file into units with provenance: PDF pages, slides, row
blocks, video frames every 2 seconds, 5-second audio windows. Embeddings and metadata live in SQLite; search is
cosine similarity. FastAPI backend, React frontend, everything local."

### 0:55–1:50 — Live demo
1. Click **Add media** (top right). In the input **"…or index a local folder in place"** paste
   `D:\python\MediaTracer\data\demo_corpus` and click **Index folder**.
   *Expected:* a list showing 19 files "Queued for indexing", then the progress bar runs to
   **"Indexed 19 of 19 file(s)"** in about 6 seconds. Close the panel.
2. Type **`the diagram showing convolutional layers`** → **Search**.
   *Expected #1:* `research_paper.pdf` · **Page 2 of 3** · "Page image match" · *Strong candidate*.
   Click **Inspect** → the PDF opens **at page 2** in the detail view. *Say:* "The diagram has no matching words —
   it was found visually."
3. Search **`a person skiing`**, click the **Video** filter chip if needed.
   *Expected:* `street_sports.mp4` · **0:04–0:06 / 0:06–0:08** · "Video frame match". **Inspect** → **Play segment**
   plays just that segment. (Optional: **Find exact moment** re-samples frames at 0.5 s.)
4. Search **`when is the report deadline`**.
   *Expected #1:* `meeting_notes.docx` · **Paragraphs 4–5 · Schedule** · "Text match", with the extracted sentence
   "The final report deadline is Friday at 5 pm…".
5. Search **`quarterly revenue by region`**.
   *Expected #1:* `revenue_2025.xlsx` · **Sheet Revenue 2025, rows 2–5 (A2:F5)**; #2 the `revenue_chart.png` image.
6. Search **`an alarm beeping`** → `alarm_beeps.wav` · **0:02–0:07** · "Audio match" → **Inspect** → **Play segment**.

### 1:50–2:25 — The open-weight model in the code
*Switch to VS Code.*
1. `backend/app/model_service.py`, **lines 85–89**: `SentenceTransformer("google/embeddinggemma-2", …,
   model_kwargs={"torch_dtype": dtype})`. Point at **`_select_device()` (line 52)**: "bfloat16 on the GPU, never
   float16 — the model card warns it breaks embeddings."
2. Same file, **`_probe()` (line 112)**: "At startup we run a real forward pass for text, image and audio; a
   modality is only enabled if it produces valid vectors." Then **`embed_queries` → `encode_query` (line 236)** and
   **`embed_images` / `embed_audio` → `encode_document` (lines 249–257)**.
3. `backend/app/search.py` **line 123**: `self.matrix[idx] @ qvec` — "that's the whole retrieval: cosine similarity."
4. Back in the browser click **AI model & open source** (header): live model id, device, dtype and verified
   modalities from `/api/health`, plus the component/license table. Mention `docs/OPEN_SOURCE_MAP.md` for exact lines.

### 2:25–2:50 — Provenance, local-first, reliability
1. Click the **Collection** tab: 19 files, each **Indexed** with its unit count and the original path.
2. *Window 3:*
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/health | Select-Object -ExpandProperty model
   ```
   shows `state: ready, device: cuda, dtype: bfloat16, modalities: {audio, image, text}`.
   *Say:* "The model runs from the local cache with `HF_HUB_OFFLINE=1`; the backend makes no outbound calls with
   your files."
3. *Reliability (say, or show if time):* "Restart the backend and the index is still there — re-indexing the
   same folder reports **19 unchanged** because files are fingerprinted. Corrupt or unsupported files get a clear
   message instead of a crash." (Verified: `docs/EVALUATION.md` → "Unsupported / corrupt input handling".)

### 2:50–3:00 — Close
*Say:* "MediaTrace: one open-weight multimodal model, real evidence with exact provenance, running entirely on
your own machine. Search by what you remember, not by where you saved it."

## If something goes wrong

- Pill says **Loading EmbeddingGemma 2…** → wait ~12 s; searches are disabled until ready.
- Pill says **Backend offline** → Window 1 is not running; restart `.\scripts\start-backend.ps1`.
- Index folder shows **Unchanged — kept existing index** → you are on an already-seeded data folder; that is
  the fingerprint reuse working. Search directly.
- After judging, `data\judge_demo` can be deleted; it is git-ignored.
