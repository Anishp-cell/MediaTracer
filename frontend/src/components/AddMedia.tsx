import { FolderInput, Upload, X } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { api } from '../api'
import type { Capabilities, Registration } from '../types'

interface Props {
  caps: Capabilities | null
  onJob: (jobId: string) => void
  onRegistered: () => void
  onClose: () => void
}

const ACTION_TEXT: Record<Registration['action'], string> = {
  new: 'Queued for indexing',
  updated: 'Changed — re-indexing',
  unchanged: 'Unchanged — kept existing index',
  duplicate: 'Already indexed',
  rejected: 'Rejected',
}

export function AddMedia({ caps, onJob, onRegistered, onClose }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [regs, setRegs] = useState<Registration[]>([])
  const [error, setError] = useState<string | null>(null)
  const [folder, setFolder] = useState('')

  const accept = caps?.accepted_extensions.join(',') ?? ''

  const handle = async (p: Promise<{ job_id: string | null; files: Registration[] }>) => {
    setBusy(true)
    setError(null)
    try {
      const r = await p
      setRegs(r.files)
      if (r.job_id) onJob(r.job_id)
      onRegistered()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return
    void handle(api.upload(Array.from(list)))
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDrag(false)
    onFiles(e.dataTransfer.files)
  }

  const disabled = caps?.adapters.filter((a) => !a.enabled) ?? []

  return (
    <section className="card add-media">
      <div className="section-head">
        <h2>Add media</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close add media"><X size={18} /></button>
      </div>
      <div
        className={`dropzone ${drag ? 'drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
      >
        <Upload size={28} aria-hidden />
        <p><strong>Drop files here</strong> or click to choose</p>
        <p className="muted small">{caps ? caps.accepted_extensions.join(' ') : 'Loading supported formats…'}
          {caps && ` · up to ${caps.max_upload_mb} MB each`}</p>
        <input ref={input} type="file" multiple hidden accept={accept} onChange={(e) => { onFiles(e.target.files); e.target.value = '' }} />
      </div>

      <form className="folder-row" onSubmit={(e) => { e.preventDefault(); if (folder.trim()) void handle(api.indexLocal([folder.trim()])) }}>
        <FolderInput size={18} aria-hidden />
        <input value={folder} onChange={(e) => setFolder(e.target.value)}
          placeholder="…or index a local folder in place, e.g. D:\Photos" aria-label="Local folder path" />
        <button className="btn small" disabled={busy || !folder.trim()}>Index folder</button>
      </form>
      <p className="muted small">Files stay on this computer. Local folders are indexed in place and never modified.</p>

      {disabled.length > 0 && (
        <p className="muted small">Not available right now: {disabled.map((a) => `${Object.keys(a.formats).join(' ')} (${a.reason})`).join('; ')}</p>
      )}
      {error && <p className="error-text">{error}</p>}
      {regs.length > 0 && (
        <ul className="reg-list">
          {regs.map((r, i) => (
            <li key={i} className={`reg ${r.action}`}>
              <span className="fname">{r.filename}</span>
              <span>{ACTION_TEXT[r.action]}{r.reason ? ` — ${r.reason}` : ''}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
