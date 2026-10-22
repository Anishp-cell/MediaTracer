# Third-party notices

MediaTrace's own source code is licensed under the [MIT License](LICENSE). MediaTrace depends on the following
third-party model and packages, which are **installed by the user** (pip / npm / Hugging Face cache) and are
**not redistributed in this repository**. Each keeps its own license. Versions are those installed and tested on
the reference machine; license values come from each package's installed metadata (`License` /
`License-Expression` / classifiers, or `package.json`) unless noted.

MIT was chosen for MediaTrace because it is permissive, widely understood and compatible with every dependency
listed here (Apache-2.0, BSD, MIT, ISC, public domain), which keeps the project easy to reuse and fork.

## Model weights

| Model | License | Source |
|---|---|---|
| `google/embeddinggemma-2` | Apache-2.0 (`license: apache-2.0` in the model card front matter) | https://huggingface.co/google/embeddinggemma-2 |

## Python packages (direct dependencies, `backend/requirements.txt` + PyTorch)

| Package | Version | License (declared) | Source |
|---|---|---|---|
| torch | 2.11.0+cu128 | BSD-3-Clause | https://github.com/pytorch/pytorch |
| torchvision | 0.26.0+cu128 | BSD (BSD-3-Clause) | https://github.com/pytorch/vision |
| sentence-transformers | 6.2.0 | Apache-2.0 | https://github.com/huggingface/sentence-transformers |
| transformers | 5.20.2 | Apache-2.0 | https://github.com/huggingface/transformers |
| huggingface-hub (transitive) | 2.2.0 | Apache-2.0 | https://github.com/huggingface/huggingface_hub |
| tokenizers (transitive) | 0.23.3 | Apache-2.0 (classifier) | https://github.com/huggingface/tokenizers |
| safetensors (transitive) | 0.8.0 | Apache-2.0 (classifier) | https://github.com/huggingface/safetensors |
| fastapi | 0.159.1 | MIT | https://github.com/fastapi/fastapi |
| starlette (transitive) | 1.7.0 | BSD-3-Clause | https://github.com/encode/starlette |
| pydantic (transitive) | 2.14.1 | MIT | https://github.com/pydantic/pydantic |
| uvicorn | 0.54.0 | BSD-3-Clause | https://github.com/encode/uvicorn |
| python-multipart | 0.0.32 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, plus bundled dependency licenses (PDFium) | https://github.com/pypdfium2-team/pypdfium2 |
| pypdf | 6.21.2 | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| pillow | 12.3.0 | MIT-CMU | https://github.com/python-pillow/Pillow |
| numpy | 2.2.6 | BSD-3-Clause (classifier "BSD License") | https://github.com/numpy/numpy |
| av (PyAV) | 17.1.0 | BSD-3-Clause — **bundles FFmpeg, see note** | https://github.com/PyAV-Org/PyAV |
| python-docx | 1.2.0 | MIT | https://github.com/python-openxml/python-docx |
| python-pptx | 1.0.2 | MIT | https://github.com/scanny/python-pptx |
| openpyxl | 3.1.5 | MIT | https://foss.heptapod.net/openpyxl/openpyxl |
| pytest (tests only) | 9.1.1 | MIT | https://github.com/pytest-dev/pytest |
| httpx (tests only) | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx |
| sqlite3 (Python standard library) | — | SQLite: public domain | https://sqlite.org/copyright.html |

## JavaScript packages (`frontend/package.json`)

| Package | Version | License | Source |
|---|---|---|---|
| react, react-dom | 19.3.1 | MIT | https://github.com/facebook/react |
| vite | 8.3.5 | MIT | https://github.com/vitejs/vite |
| @vitejs/plugin-react | 6.1.2 | MIT | https://github.com/vitejs/vite-plugin-react |
| typescript | 6.0.3 | Apache-2.0 | https://github.com/microsoft/TypeScript |
| lucide-react | 1.61.0 | ISC | https://github.com/lucide-icons/lucide |

## Unresolved / flagged

- **FFmpeg inside the PyAV wheel.** `av.library_meta` for the installed wheel reports FFmpeg 8.1.1 with license
  *"LGPL version 3 or later"*, but the wheel also ships `libx264` and `libx265` DLLs, which are separate projects
  licensed GPL-2.0-or-later. MediaTrace does not redistribute PyAV or FFmpeg (users install them from PyPI), and
  only `scripts/make_demo_corpus.py` uses the x264 *encoder*; the app itself only decodes. Anyone redistributing
  a bundled binary of MediaTrace should review FFmpeg/x264 licensing first. **Not legally reviewed.**
- **Transitive dependencies** beyond those listed above (e.g. jinja2, filelock, regex, sympy) were not individually audited.
- **Demo corpus**: COCO val2017 images and the LibriSpeech sample are CC BY 4.0; they are downloaded at run time by
  `scripts/make_demo_corpus.py` and are git-ignored, not redistributed.
