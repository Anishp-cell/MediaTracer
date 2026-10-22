# Graph Report - MediaTracer  (2026-10-22)

## Corpus Check
- 52 files · ~28,292 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: (none) 5, .css 2, .ini 1)

## Summary
- 577 nodes · 1288 edges · 20 communities (13 shown, 7 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 112 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Settings
- indexer.py
- App.tsx
- ModelService
- main.py
- make_demo_corpus.py
- create_app
- MediaTrace
- package.json
- Database
- test_adapters.py
- compilerOptions
- compilerOptions
- .oxlintrc.json
- tsconfig.json
- CLAUDE.md
- .claude/CLAUDE.md

## God Nodes (most connected - your core abstractions)
1. `Settings` - 49 edges
2. `create_app()` - 38 edges
3. `Unit` - 34 edges
4. `AdapterError` - 32 edges
5. `ModelService` - 32 edges
6. `Database` - 31 edges
7. `Indexer` - 23 edges
8. `Adapter` - 21 edges
9. `compilerOptions` - 18 edges
10. `1. The open-weight model — `google/embeddinggemma-2`` - 18 edges

## Surprising Connections (you probably didn't know these)
- `2. Libraries` --references--> `create_app()`  [INFERRED]
  docs/OPEN_SOURCE_MAP.md → backend/app/main.py
- `1. The open-weight model — `google/embeddinggemma-2`` --references--> `health()`  [INFERRED]
  docs/OPEN_SOURCE_MAP.md → backend/app/main.py
- `2. Libraries` --references--> `thumbnail()`  [INFERRED]
  docs/OPEN_SOURCE_MAP.md → backend/app/adapters/base.py
- `2. Libraries` --references--> `iter_audio_windows()`  [INFERRED]
  docs/OPEN_SOURCE_MAP.md → backend/app/adapters/media.py
- `2. Libraries` --references--> `sample_frames()`  [INFERRED]
  docs/OPEN_SOURCE_MAP.md → backend/app/adapters/media.py

## Import Cycles
- None detected.

## Communities (20 total, 7 thin omitted)

### Community 0 - "Settings"
Cohesion: 0.06
Nodes (32): Adapter, AdapterError, chunk_text(), thumbnail(), Unit, ImageAdapter, _audio_units(), AudioAdapter (+24 more)

### Community 1 - "indexer.py"
Cohesion: 0.06
Nodes (12): adapter_for(), supported_extensions(), new_id(), Indexer, flush(), JobCancelled, Registration, sha256_file() (+4 more)

### Community 2 - "App.tsx"
Cohesion: 0.09
Nodes (45): MediaTrace frontend, api, ApiError, json(), request(), App(), EXAMPLES, JobBar() (+37 more)

### Community 3 - "ModelService"
Cohesion: 0.09
Nodes (10): audio_input(), ModelNotReady, ModelService, _probe_audio(), _probe_image(), _write_wav(), 1:50–2:25 — The open-weight model in the code, 1. The open-weight model — `google/embeddinggemma-2` (+2 more)

### Community 4 - "main.py"
Cohesion: 0.07
Nodes (17): get_item(), fmt_time(), get_services(), location_label(), Services, fmt_loc(), main(), matches() (+9 more)

### Community 5 - "make_demo_corpus.py"
Cohesion: 0.09
Nodes (19): accuracy_chart(), cnn_diagram(), decode_audio(), fetch(), font(), main(), _pdf_str(), pick_video_codec() (+11 more)

### Community 6 - "create_app"
Cohesion: 0.09
Nodes (40): create_app(), build_results(), capabilities(), file_info(), file_items(), file_or_404(), file_preview(), get_file() (+32 more)

### Community 7 - "MediaTrace"
Cohesion: 0.05
Nodes (38): 0:00–0:25 — The problem, 0:25–0:55 — Solution and architecture, 0:55–1:50 — Live demo, 2:25–2:50 — Provenance, local-first, reliability, 2:50–3:00 — Close, Before the judges arrive (≈2 minutes, not part of the 3:00), If something goes wrong, MediaTrace — 3-minute judging script (+30 more)

### Community 8 - "package.json"
Cohesion: 0.07
Nodes (29): dependencies, lucide-react, react, react-dom, devDependencies, oxlint, @types/node, @types/react (+21 more)

### Community 10 - "test_adapters.py"
Cohesion: 0.15
Nodes (17): lifespan(), model(), settings(), test_audio_windows(), test_chunk_text_preserves_line_numbers(), test_corrupt_inputs_raise_adapter_error(), test_csv_rows_and_cells(), test_docx_text_picture_table() (+9 more)

### Community 11 - "compilerOptions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 12 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 13 - ".oxlintrc.json"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

## Knowledge Gaps
- **5 isolated node(s):** `@types/node`, `@types/react`, `@types/react-dom`, `oxlint`, `typescript`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 207 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaTrace frontend` connect `App.tsx` to `MediaTrace`?**
  _High betweenness centrality (0.231) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `Settings` (e.g. with `Adapter` and `ImageAdapter`) actually correct?**
  _`Settings` has 20 INFERRED edges - model-reasoned connections that need verification._
- **What connects `@types/node`, `@types/react`, `@types/react-dom` to the rest of the system?**
  _5 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Settings` be split into smaller, more focused modules?**
  _Cohesion score 0.06472564389697648 - nodes in this community are weakly interconnected._
- **Why does `Open-source integration map` connect `MediaTrace` to `Settings`, `ModelService`?**
  _High betweenness centrality (0.195) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `create_app()` (e.g. with `Settings` and `lifespan()`) actually correct?**
  _`create_app()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `indexer.py` be split into smaller, more focused modules?**
  _Cohesion score 0.061367621274108705 - nodes in this community are weakly interconnected._