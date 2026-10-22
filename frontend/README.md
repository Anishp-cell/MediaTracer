# MediaTrace frontend

React 19 + TypeScript + Vite UI for MediaTrace. See the [project README](../README.md) for setup.

```powershell
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on 127.0.0.1:8000
npm run build    # type-check + production build into dist/
```

- `src/App.tsx` — search page, filters, results, job progress, model status pill
- `src/components/` — `ResultCard`, `DetailView` (PDF page / media segment playback), `Collection`, `AddMedia`, `About` (live model & open-source panel)
- `src/api.ts` — typed client for every backend endpoint the UI uses
