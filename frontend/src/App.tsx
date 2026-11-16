import {
  CircleAlert,
  Compass,
  ImagePlus,
  Info,
  LayoutGrid,
  Library,
  List,
  Loader2,
  Moon,
  Plus,
  Search,
  SearchX,
  Sparkles,
  Sun,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, isDemoMode, setDemoMode } from './api'
import { About } from './components/About'
import { AddMedia } from './components/AddMedia'
import { Collection } from './components/Collection'
import { DetailView } from './components/DetailView'
import { FamilyIcon } from './components/FamilyIcon'
import { ResultCard } from './components/ResultCard'
import { FAMILY_LABEL } from './format'
import type { Capabilities, Family, FileInfo, Health, Job, SearchResponse, SearchResult } from './types'
import './App.css'

const EXAMPLES = [
  'a red backpack',
  'the diagram showing convolutional layers',
  'a slide comparing model accuracy',
  'quarterly revenue figures',
  'applause from an audience',
]

function ModelPill({ health, error, isDemo }: { health: Health | null; error: string | null; isDemo: boolean }) {
  if (isDemo) {
    return (
      <span className="pill ok" title="Previewing with simulated EmbeddingGemma 2 responses">
        <span className="dot" /> Demo Mode · EmbeddingGemma 2
      </span>
    )
  }
  if (error) return <span className="pill err"><CircleAlert size={14} /> Backend offline</span>
  if (!health) return <span className="pill"><Loader2 size={14} className="spin" /> Connecting…</span>
  const m = health.model
  if (m.state === 'ready') {
    const problems = Object.entries(m.modality_errors ?? {})
    const title = `${m.model_id} · verified modalities: ${m.modalities.join(', ')} · loaded in ${m.load_seconds}s` +
      (problems.length ? `\nUnavailable: ${problems.map(([k, v]) => `${k} (${v})`).join('; ')}` : '')
    return (
      <span className={`pill ${problems.length ? '' : 'ok'}`} title={title}>
        {problems.length ? <CircleAlert size={14} /> : <span className="dot" />}
        EmbeddingGemma 2 · {m.device === 'cuda' ? 'GPU' : 'CPU'} · {m.dtype}
        {problems.length > 0 && ` · no ${problems.map(([k]) => k).join('/')}`}
      </span>
    )
  }
  if (m.state === 'error') return <span className="pill err" title={m.error ?? ''}><CircleAlert size={14} /> Model failed to load</span>
  return <span className="pill"><Loader2 size={14} className="spin" /> Loading EmbeddingGemma 2…</span>
}

function JobBar({ job, onCancel, onDismiss }: { job: Job; onCancel: () => void; onDismiss: () => void }) {
  const active = job.status === 'queued' || job.status === 'running'
  return (
    <div className={`jobbar ${job.status}`} role="status" aria-live="polite">
      <div className="jobbar-text">
        {active && <Loader2 size={16} className="spin" />}
        <span>{job.message ?? job.status}</span>
        <span className="muted small">{job.done + job.failed}/{job.total} files</span>
      </div>
      <div className="progress"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
      {job.errors.length > 0 && (
        <ul className="job-errors">{job.errors.map((e) => <li key={e.file_id}><strong>{e.filename}</strong>: {e.error}</li>)}</ul>
      )}
      {active
        ? <button className="btn small ghost" onClick={onCancel}>Cancel</button>
        : <button className="icon-btn" onClick={onDismiss} aria-label="Dismiss"><X size={16} /></button>}
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [healthErr, setHealthErr] = useState<string | null>(null)
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [files, setFiles] = useState<FileInfo[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [view, setView] = useState<'search' | 'collection'>('search')
  const [showAdd, setShowAdd] = useState(false)
  const [showAbout, setShowAbout] = useState(false)

  // Demo Mode for designing without backend running
  const [demoActive, setDemoActive] = useState<boolean>(isDemoMode())

  // Dark / Light Theme
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('mediatrace_theme')
    if (saved === 'light' || saved === 'dark') return saved
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  // Search state
  const [query, setQuery] = useState('')
  const [families, setFamilies] = useState<Family[]>([])
  const [mode, setMode] = useState<'semantic' | 'hybrid'>('semantic')
  const [searching, setSearching] = useState(false)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [searchErr, setSearchErr] = useState<string | null>(null)
  const [selected, setSelected] = useState<SearchResult | null>(null)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

  const searchInputRef = useRef<HTMLInputElement>(null)
  const imageInput = useRef<HTMLInputElement>(null)

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('mediatrace_theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))
  }

  const toggleDemoMode = () => {
    const next = !demoActive
    setDemoActive(next)
    setDemoMode(next)
    void refreshStatus()
    void refreshFiles()
  }

  const refreshStatus = useCallback(async () => {
    try {
      const [h, c] = await Promise.all([api.health(), api.capabilities()])
      setHealth(h)
      setCaps(c)
      setHealthErr(null)
    } catch (e) {
      setHealthErr((e as Error).message)
    }
  }, [])

  const refreshFiles = useCallback(async () => {
    try {
      setFiles(await api.files())
    } catch { /* surfaced by health pill */ }
  }, [])

  // Poll health quickly while model loads, slowly afterwards
  useEffect(() => {
    void refreshStatus()
    void refreshFiles()
    if (demoActive) return
    const ready = health?.model.state === 'ready'
    const t = setInterval(() => void refreshStatus(), ready ? 15000 : 2000)
    return () => clearInterval(t)
  }, [refreshStatus, refreshFiles, health?.model.state, demoActive])

  // Resume jobs after page reload
  useEffect(() => {
    if (demoActive) return
    api.jobs()
      .then((all) => setJobs(all.filter((j) => j.status === 'queued' || j.status === 'running')))
      .catch(() => { /* backend offline; health pill reports it */ })
  }, [demoActive])

  // Poll active jobs
  const activeJobs = jobs.filter((j) => j.status === 'queued' || j.status === 'running')
  useEffect(() => {
    if (activeJobs.length === 0 || demoActive) return
    const t = setInterval(async () => {
      const updated = await Promise.all(jobs.map((j) =>
        j.status === 'queued' || j.status === 'running' ? api.job(j.id).catch(() => j) : Promise.resolve(j)))
      setJobs(updated)
      void refreshFiles()
      if (updated.every((j) => j.status !== 'queued' && j.status !== 'running')) void refreshStatus()
    }, 1000)
    return () => clearInterval(t)
  }, [jobs, activeJobs.length, refreshFiles, refreshStatus, demoActive])

  // Keyboard shortcut: '/' or 'Ctrl+K' focuses search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key === 'k')) && document.activeElement !== searchInputRef.current) {
        e.preventDefault()
        searchInputRef.current?.focus()
        searchInputRef.current?.select()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const trackJob = (id: string) => {
    void api.job(id).then((j) => setJobs((prev) => [j, ...prev.filter((p) => p.id !== id)]))
  }

  const runSearch = async (q: string) => {
    const text = q.trim()
    if (!text) return
    setQuery(text)
    setSearching(true)
    setSearchErr(null)
    try {
      setResponse(await api.search(text, families.length ? families : null, mode))
    } catch (e) {
      setSearchErr((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const runImageSearch = async (file: File) => {
    setSearching(true)
    setSearchErr(null)
    try {
      const r = await api.searchImage(file, families.length ? families : null)
      setQuery(r.query)
      setResponse(r)
    } catch (e) {
      setSearchErr((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const toggleFamily = (f: Family) =>
    setFamilies((prev) => (prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f]))

  const enabledFamilies = Array.from(new Set((caps?.adapters ?? []).filter((a) => a.enabled).map((a) => a.family)))
  const counts = files.reduce<Record<string, number>>((acc, f) => {
    if (f.status === 'indexed') acc[f.family] = (acc[f.family] ?? 0) + 1
    return acc
  }, {})

  const modelReady = demoActive || health?.model.state === 'ready'
  const empty = !demoActive && (health?.indexed_files ?? 0) === 0

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">
            <Compass size={20} />
          </div>
          <div className="brand-text">
            <span className="brand-title">MediaTrace</span>
            <span className="brand-subtitle">Semantic Recall</span>
          </div>
        </div>

        <nav className="tabs" aria-label="Views">
          <button className={view === 'search' ? 'active' : ''} onClick={() => setView('search')}>
            <Search size={15} /> Search
          </button>
          <button className={view === 'collection' ? 'active' : ''} onClick={() => setView('collection')}>
            <Library size={15} /> Collection <span className="count">{files.length}</span>
          </button>
        </nav>

        <div className="top-right">
          <button
            className="theme-toggle-btn"
            onClick={toggleTheme}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </button>

          <button className="pill-btn" onClick={() => setShowAbout(true)} title="AI model & system health">
            <ModelPill health={health} error={healthErr} isDemo={demoActive} />
          </button>

          <button className="btn ghost" onClick={() => setShowAbout(true)}>
            <Info size={16} /> Details
          </button>

          <button className="btn primary" onClick={() => setShowAdd((s) => !s)}>
            <Plus size={16} /> Add Media
          </button>
        </div>
      </header>

      <main>
        {/* Demo Mode Notification / Toggle Banner when Backend is offline */}
        {healthErr && (
          <div className="demo-banner">
            <div className="demo-banner-content">
              <span className="demo-badge">{demoActive ? 'Demo Mode Active' : 'Backend Offline'}</span>
              <span>
                {demoActive
                  ? 'Showing simulated results with EmbeddingGemma 2. Start Python backend on port 8000 anytime for live retrieval.'
                  : 'Backend on port 8000 is not running. Enable Demo Mode to preview interactive search and design the UI.'}
              </span>
            </div>
            <button className="btn small primary-subtle" onClick={toggleDemoMode}>
              {demoActive ? 'Disable Demo Mode' : 'Enable Demo Mode'}
            </button>
          </div>
        )}

        {showAdd && <AddMedia caps={caps} onJob={trackJob} onRegistered={refreshFiles} onClose={() => setShowAdd(false)} />}

        {jobs.map((j) => (
          <JobBar
            key={j.id}
            job={j}
            onCancel={() => void api.cancelJob(j.id).then(() => trackJob(j.id))}
            onDismiss={() => setJobs((prev) => prev.filter((p) => p.id !== j.id))}
          />
        ))}

        {view === 'collection' ? (
          <Collection files={files} onChanged={() => { void refreshFiles(); void refreshStatus() }} onJob={trackJob} />
        ) : (
          <>
            <section className={`hero ${response ? 'compact' : ''}`}>
              {!response && (
                <>
                  <div className="hero-tagline">
                    <Sparkles size={14} /> Local-first Multimodal Search
                  </div>
                  <h1>
                    Search by what you remember,<br />
                    <span className="gradient-text">not by where you saved it.</span>
                  </h1>
                  <p className="lede">
                    Describe a scene in a photo, a moment in a video, a voice note, or a table row.
                    MediaTrace finds the exact provenance — on-device, with EmbeddingGemma 2.
                  </p>
                </>
              )}

              <div className="searchbar-container">
                <form
                  className="searchbar"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void runSearch(query)
                  }}
                >
                  <Search size={20} className="search-icon-decor" aria-hidden />
                  <input
                    ref={searchInputRef}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    autoFocus
                    placeholder="e.g. the diagram showing convolutional layers, or roadtrip lake"
                    aria-label="Search query"
                  />
                  {query && (
                    <button
                      type="button"
                      className="icon-btn search-clear-btn"
                      onClick={() => {
                        setQuery('')
                        searchInputRef.current?.focus()
                      }}
                      aria-label="Clear input"
                    >
                      <X size={16} />
                    </button>
                  )}
                  <span className="kbd-shortcut" title="Press / to search">/</span>
                  {caps?.image_query && (
                    <button
                      type="button"
                      className="icon-btn"
                      title="Search with a reference image"
                      aria-label="Search with a reference image"
                      onClick={() => imageInput.current?.click()}
                    >
                      <ImagePlus size={19} />
                    </button>
                  )}
                  <input
                    ref={imageInput}
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp"
                    hidden
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) void runImageSearch(f)
                      e.target.value = ''
                    }}
                  />
                  <button className="btn primary" disabled={searching || !query.trim() || !modelReady}>
                    {searching ? <Loader2 size={16} className="spin" /> : 'Search'}
                  </button>
                </form>
              </div>

              <div className="filters">
                {enabledFamilies.map((f) => (
                  <button
                    key={f}
                    className={`chip ${families.includes(f) ? 'on' : ''}`}
                    onClick={() => toggleFamily(f)}
                    aria-pressed={families.includes(f)}
                  >
                    <FamilyIcon family={f} size={15} />
                    <span>{FAMILY_LABEL[f]}</span>
                    <span className="count">{counts[f] ?? 0}</span>
                  </button>
                ))}
                <span className="spacer" />
                <div className="segmented" role="group" aria-label="Ranking mode">
                  <button
                    className={mode === 'semantic' ? 'on' : ''}
                    onClick={() => setMode('semantic')}
                    title="Rank purely by EmbeddingGemma 2 semantic similarity"
                  >
                    Semantic
                  </button>
                  <button
                    className={mode === 'hybrid' ? 'on' : ''}
                    onClick={() => setMode('hybrid')}
                    title="Semantic similarity + BM25 keyword boost from extracted text"
                  >
                    Hybrid
                  </button>
                </div>
              </div>

              {!response && !empty && (
                <div className="examples">
                  <span className="muted small">Suggestions:</span>
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      className="example-tag"
                      onClick={() => void runSearch(ex)}
                      disabled={!modelReady}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              )}
            </section>

            {searchErr && <p className="error-text center">{searchErr}</p>}

            {empty && !response && (
              <div className="empty">
                <div className="empty-icon-wrap">
                  <Library size={36} aria-hidden />
                </div>
                <h2>Your collection is empty</h2>
                <p>Add photos, PDFs, videos, recordings, spreadsheets or documents to start searching.</p>
                <button className="btn primary" onClick={() => setShowAdd(true)}>
                  <Plus size={16} /> Add Media
                </button>
              </div>
            )}

            {response && (
              <section className="results-section">
                <div className="results-head">
                  <p className="results-count-text">
                    Found <strong>{response.results.length}</strong> match{response.results.length === 1 ? '' : 'es'} for{' '}
                    “<strong>{response.query}</strong>” · searched {response.searched_items} units in {response.took_ms} ms · {response.mode} mode
                  </p>
                  <div className="results-actions-bar">
                    <div className="view-mode-toggle" role="group" aria-label="Results layout view">
                      <button
                        className={viewMode === 'grid' ? 'active' : ''}
                        onClick={() => setViewMode('grid')}
                        title="Grid View"
                      >
                        <LayoutGrid size={15} />
                      </button>
                      <button
                        className={viewMode === 'list' ? 'active' : ''}
                        onClick={() => setViewMode('list')}
                        title="List View"
                      >
                        <List size={15} />
                      </button>
                    </div>
                    <button className="btn small ghost" onClick={() => setResponse(null)}>
                      Clear
                    </button>
                  </div>
                </div>

                {response.notice && (
                  <div className="notice">
                    <SearchX size={18} aria-hidden /> {response.notice}
                  </div>
                )}

                <div className={`grid ${viewMode === 'list' ? 'list' : ''}`}>
                  {response.results.map((r) => (
                    <ResultCard
                      key={r.item_id}
                      result={r}
                      onInspect={setSelected}
                      viewMode={viewMode}
                    />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </main>

      <footer className="foot">
        MediaTrace · Local multimodal retrieval with EmbeddingGemma 2 · Everything stays on your machine
      </footer>

      {showAbout && <About health={health} onClose={() => setShowAbout(false)} />}

      {selected && (
        <DetailView
          result={selected}
          query={query}
          canRefine={caps?.video_refine ?? false}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
