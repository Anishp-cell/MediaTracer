import { Crosshair, Download, ExternalLink, Loader2, Play, X } from 'lucide-react'
import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtTime, isViewable } from '../format'
import type { SearchResult } from '../types'

interface Props {
  result: SearchResult
  query: string
  canRefine: boolean
  onClose: () => void
}

function MediaPlayer({ result, query, canRefine }: { result: SearchResult; query: string; canRefine: boolean }) {
  const loc = result.locator as unknown as { start: number; end: number; time?: number }
  const ref = useRef<HTMLMediaElement>(null)
  const stopAt = useRef<number | null>(null)
  const [refining, setRefining] = useState(false)
  const [refined, setRefined] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const isVideo = result.family === 'video'
  const src = api.url(`/api/files/${result.file_id}/stream`)

  const seek = (t: number, stop: number | null) => {
    const el = ref.current
    if (!el) return
    el.currentTime = t
    stopAt.current = stop
    void el.play().catch(() => { /* autoplay may be blocked; user can press play */ })
  }

  const onTime = () => {
    const el = ref.current
    if (el && stopAt.current !== null && el.currentTime >= stopAt.current) {
      el.pause()
      stopAt.current = null
    }
  }

  const refine = async () => {
    setRefining(true)
    setError(null)
    try {
      const r = await api.refine(result.item_id, query)
      setRefined(r.best_time)
      seek(r.best_time, null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRefining(false)
    }
  }

  const mediaProps = {
    src,
    controls: true,
    preload: 'metadata' as const,
    onLoadedMetadata: () => { if (ref.current) ref.current.currentTime = loc.start },
    onTimeUpdate: onTime,
  }
  return (
    <div className="player">
      {isVideo
        ? <video ref={ref as React.RefObject<HTMLVideoElement>} className="video" {...mediaProps} />
        : <audio ref={ref as React.RefObject<HTMLAudioElement>} className="audio" {...mediaProps} />}
      {!isVideo && result.preview_url && (
        <img className="waveform" src={api.url(result.preview_url)} alt="Waveform of the matched segment" />
      )}
      <div className="player-actions">
        <span className="pill">Matched segment {fmtTime(loc.start)}–{fmtTime(loc.end)}</span>
        <button className="btn small" onClick={() => seek(loc.start, loc.end)}><Play size={15} /> Play segment</button>
        {canRefine && result.kind === 'frame' && query && !query.startsWith('[image]') && (
          <button className="btn small ghost" onClick={refine} disabled={refining}>
            {refining ? <Loader2 size={15} className="spin" /> : <Crosshair size={15} />} Find exact moment
          </button>
        )}
        {refined !== null && <span className="pill accent">Best frame at {fmtTime(refined)} ({refined.toFixed(1)}s)</span>}
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}

export function DetailView({ result, query, canRefine, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const loc = result.locator
  const media = result.family === 'video' || result.family === 'audio'
  const isPdf = loc.type === 'pdf_page'
  const isImage = result.family === 'image'

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Details for ${result.filename}`}
        onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2>{result.filename}</h2>
            <p className="location">{result.location_label} · {result.match_type}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><X /></button>
        </header>

        <div className="modal-body">
          <div className="evidence">
            {media && <MediaPlayer result={result} query={query} canRefine={canRefine} />}
            {isImage && <img className="evidence-img" src={api.url(result.original_url)} alt={result.filename} />}
            {isPdf && (
              <iframe className="pdf-frame" title={`${result.filename} page ${String(loc.page)}`}
                src={api.url(result.open_url)} />
            )}
            {!media && !isImage && !isPdf && result.preview_url && (
              <img className="evidence-img" src={api.url(result.preview_url)} alt="Embedded picture from the source" />
            )}
            {!media && !isImage && !isPdf && !result.preview_url && (
              <pre className="evidence-text">{result.text}</pre>
            )}
          </div>

          <aside className="facts">
            <h4>Source (verified metadata)</h4>
            <dl>
              <dt>File</dt><dd>{result.filename}</dd>
              <dt>Location</dt><dd>{result.location_label}</dd>
              <dt>Matched by</dt><dd>{result.match_type} ({result.modality} embedding)</dd>
              <dt>Similarity</dt>
              <dd>{result.semantic_score.toFixed(3)} cosine{result.keyword_score > 0 && ` · keyword ${result.keyword_score.toFixed(2)}`}
                <small> — a ranking signal, not a probability</small></dd>
            </dl>
            {result.text && (
              <>
                <h4>Extracted text <small>(from the file, not AI-generated)</small></h4>
                <pre className="extract">{result.text}</pre>
              </>
            )}
            {!isViewable(result.filename) && (
              <p className="muted small">Your browser cannot display this format. Download it and go to
                {' '}<strong>{result.location_label}</strong>.</p>
            )}
            <div className="actions">
              {isViewable(result.filename) && (
                <a className="btn small" href={api.url(result.open_url)} target="_blank" rel="noreferrer">
                  <ExternalLink size={15} /> Open {isPdf ? `at page ${String(loc.page)}` : media ? 'at segment' : 'original'}
                </a>
              )}
              <a className="btn small ghost" href={api.url(`${result.original_url}?download=true`)}>
                <Download size={15} /> Download
              </a>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
