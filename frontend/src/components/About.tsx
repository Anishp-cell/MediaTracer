import { ExternalLink, Info, X } from 'lucide-react'
import { useEffect } from 'react'
import type { Health } from '../types'

interface Props {
  health: Health | null
  onClose: () => void
}

// Libraries actually imported by the backend/frontend (see docs/OPEN_SOURCE_MAP.md for file/function locations).
const COMPONENTS: { name: string; role: string; license: string; url: string }[] = [
  { name: 'Sentence Transformers', role: 'Loads EmbeddingGemma 2; encode_query / encode_document', license: 'Apache-2.0', url: 'https://github.com/huggingface/sentence-transformers' },
  { name: 'Hugging Face Transformers', role: 'EmbeddingGemma 2 architecture & processor', license: 'Apache-2.0', url: 'https://github.com/huggingface/transformers' },
  { name: 'PyTorch (CUDA 12.8)', role: 'GPU / CPU inference runtime', license: 'BSD-3-Clause', url: 'https://github.com/pytorch/pytorch' },
  { name: 'FastAPI', role: 'Local HTTP API', license: 'MIT', url: 'https://github.com/fastapi/fastapi' },
  { name: 'SQLite (Python sqlite3)', role: 'Persistent index & embeddings', license: 'Public domain', url: 'https://sqlite.org/copyright.html' },
  { name: 'pypdfium2 / PDFium, pypdf', role: 'PDF page rendering & text extraction', license: 'Apache-2.0 / BSD-3-Clause', url: 'https://github.com/pypdfium2-team/pypdfium2' },
  { name: 'PyAV (FFmpeg)', role: 'Video frame & audio decoding', license: 'BSD-3-Clause (FFmpeg: LGPL/GPL)', url: 'https://github.com/PyAV-Org/PyAV' },
  { name: 'python-docx, python-pptx, openpyxl', role: 'Word, PowerPoint, Excel parsing', license: 'MIT', url: 'https://github.com/python-openxml' },
  { name: 'React, Vite, lucide-react', role: 'This user interface', license: 'MIT / MIT / ISC', url: 'https://react.dev' },
]

export function About({ health, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const m = health?.model
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal about" role="dialog" aria-modal="true" aria-label="AI model and open source"
        onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h2><Info size={18} /> AI model &amp; open source</h2>
            <p className="muted small">Live status from <code>/api/health</code> — nothing on this panel is hard-coded about readiness.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><X /></button>
        </header>
        <div className="about-body">
          <section>
            <h4>Embedding model</h4>
            {m ? (
              <dl className="facts-grid">
                <dt>Model</dt><dd><code>{m.model_id}</code> (open weights)</dd>
                <dt>Status</dt><dd>{m.state}{m.error ? ` — ${m.error}` : ''}</dd>
                <dt>Device</dt><dd>{m.device ?? '—'}{m.gpu ? ` · ${m.gpu}` : ''} · {m.dtype ?? '—'}</dd>
                <dt>Verified modalities</dt>
                <dd>{m.modalities.length ? m.modalities.join(', ') : '—'}
                  <small className="muted"> (each passed a real forward pass at load time)</small></dd>
                {Object.keys(m.modality_errors ?? {}).length > 0 && (
                  <><dt>Unavailable</dt><dd>{Object.entries(m.modality_errors).map(([k, v]) => `${k}: ${v}`).join('; ')}</dd></>
                )}
                <dt>Embedding size</dt><dd>{m.embedding_dim} dimensions, shared by text, images and audio</dd>
                <dt>Model license</dt><dd>Apache-2.0 (per the model card)</dd>
              </dl>
            ) : <p className="muted">Backend not reachable.</p>}
            <p className="links">
              <a href="https://huggingface.co/google/embeddinggemma-2" target="_blank" rel="noreferrer">Model card <ExternalLink size={13} /></a>
              <a href="https://huggingface.co/docs/transformers/en/model_doc/embedding_gemma2" target="_blank" rel="noreferrer">Transformers docs <ExternalLink size={13} /></a>
            </p>
          </section>
          <section>
            <h4>Privacy</h4>
            <p>Indexing and search run on this computer. The backend makes no outbound requests with your files;
              the model is loaded from the local Hugging Face cache.</p>
          </section>
          <section>
            <h4>Open-source components</h4>
            <table>
              <thead><tr><th>Component</th><th>Role in MediaTrace</th><th>License</th></tr></thead>
              <tbody>
                {COMPONENTS.map((c) => (
                  <tr key={c.name}>
                    <td><a href={c.url} target="_blank" rel="noreferrer">{c.name}</a></td>
                    <td>{c.role}</td>
                    <td>{c.license}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">MediaTrace application code: MIT. Full map with source files and functions:
              {' '}<code>docs/OPEN_SOURCE_MAP.md</code>.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
