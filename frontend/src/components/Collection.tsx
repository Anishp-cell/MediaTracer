import { AlertTriangle, CheckCircle2, FolderSync, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { fmtBytes, fmtDate } from '../format'
import { FamilyIcon } from './FamilyIcon'
import type { FileInfo } from '../types'

interface Props {
  files: FileInfo[]
  onChanged: () => void
  onJob: (jobId: string) => void
}

function StatusBadge({ f }: { f: FileInfo }) {
  if (f.status === 'indexed') return <span className="status ok"><CheckCircle2 size={14} /> Indexed</span>
  if (f.status === 'failed') return <span className="status err"><AlertTriangle size={14} /> Failed</span>
  return <span className="status busy"><Loader2 size={14} className="spin" /> {f.status === 'queued' ? 'Queued' : 'Processing'}</span>
}

export function Collection({ files, onChanged, onJob }: Props) {
  const [confirming, setConfirming] = useState<FileInfo | null>(null)
  const [deleteCopy, setDeleteCopy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const remove = async () => {
    if (!confirming) return
    try {
      await api.removeFile(confirming.id, deleteCopy)
      setConfirming(null)
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const act = async (fn: () => Promise<{ job_id: string | null }>) => {
    setError(null)
    try {
      const r = await fn()
      if (r.job_id) onJob(r.job_id)
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const hasLocal = files.some((f) => f.origin === 'local')
  return (
    <section className="collection">
      <div className="section-head">
        <h2>Indexed collection <span className="count">{files.length}</span></h2>
        {hasLocal && (
          <button className="btn small ghost" onClick={() => act(api.rescan)} title="Re-index local files that changed on disk">
            <FolderSync size={15} /> Rescan local files
          </button>
        )}
      </div>
      {error && <p className="error-text">{error}</p>}
      {files.length === 0 ? (
        <p className="muted">No files yet. Add media above to build your searchable collection.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>File</th><th>Type</th><th>Status</th><th>Units</th><th>Size</th><th>Indexed</th><th /></tr>
            </thead>
            <tbody>
              {files.map((f) => {
                return (
                  <tr key={f.id}>
                    <td className="file-cell">
                      <FamilyIcon family={f.family} />
                      <div>
                        <div className="fname" title={f.source_path ?? f.filename}>{f.filename}</div>
                        <div className="muted small">{f.origin === 'local' ? f.source_path : 'Uploaded copy'}</div>
                        {f.error && <div className="error-text small">{f.error}</div>}
                      </div>
                    </td>
                    <td>{f.format}</td>
                    <td><StatusBadge f={f} /></td>
                    <td>{f.item_count || '—'}</td>
                    <td>{fmtBytes(f.size_bytes)}</td>
                    <td className="small">{fmtDate(f.indexed_at)}</td>
                    <td className="row-actions">
                      {f.status === 'failed' && (
                        <button className="icon-btn" title="Retry indexing" aria-label={`Retry ${f.filename}`}
                          onClick={() => act(() => api.reindex(f.id))}><RefreshCw size={16} /></button>
                      )}
                      <button className="icon-btn danger" title="Remove from index" aria-label={`Remove ${f.filename}`}
                        onClick={() => { setDeleteCopy(false); setConfirming(f) }}><Trash2 size={16} /></button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {confirming && (
        <div className="modal-backdrop" onClick={() => setConfirming(null)}>
          <div className="modal small" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h3>Remove “{confirming.filename}” from the index?</h3>
            <p>Its embeddings and previews will be deleted. {confirming.origin === 'local'
              ? 'The original file on your disk will not be touched.'
              : 'You can also delete the copy MediaTrace stored when you uploaded it.'}</p>
            {confirming.origin === 'upload' && (
              <label className="check">
                <input type="checkbox" checked={deleteCopy} onChange={(e) => setDeleteCopy(e.target.checked)} />
                Also delete the uploaded copy stored by MediaTrace
              </label>
            )}
            <div className="actions end">
              <button className="btn small ghost" onClick={() => setConfirming(null)}>Cancel</button>
              <button className="btn small danger" onClick={remove}><Trash2 size={15} /> Remove</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
