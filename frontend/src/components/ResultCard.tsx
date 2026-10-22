import { Download, ExternalLink, Eye } from 'lucide-react'
import { api } from '../api'
import { isViewable } from '../format'
import type { SearchResult } from '../types'
import { FamilyIcon } from './FamilyIcon'

const STRENGTH_LABEL = { strong: 'Strong candidate', moderate: 'Possible match', weak: 'Weak candidate' }

interface Props {
  result: SearchResult
  onInspect: (r: SearchResult) => void
}

export function ResultCard({ result: r, onInspect }: Props) {
  return (
    <article className={`card result strength-${r.strength}`}>
      <button className="result-preview" onClick={() => onInspect(r)} aria-label={`Inspect ${r.filename}`}>
        {r.preview_url ? (
          <img src={api.url(r.preview_url)} alt={`Preview of ${r.filename}, ${r.location_label}`} loading="lazy" />
        ) : (
          <div className="preview-fallback">
            <FamilyIcon family={r.family} size={36} />
            {r.text && <p>{r.text.slice(0, 220)}</p>}
          </div>
        )}
        <span className="rank">#{r.rank}</span>
      </button>
      <div className="result-body">
        <div className="result-title">
          <FamilyIcon family={r.family} />
          <h3 title={r.filename}>{r.filename}</h3>
        </div>
        <div className="location">{r.location_label}</div>
        <div className="meta-row">
          <span className="tag">{r.match_type}</span>
          {r.also_matched.length > 0 && <span className="tag subtle">+ {r.also_matched.length} more signal(s)</span>}
        </div>
        <div className="score-row" title={`Cosine similarity ${r.semantic_score.toFixed(3)}${r.keyword_score ? ` · keyword ${r.keyword_score.toFixed(2)}` : ''}. A ranking signal, not a probability.`}>
          <div className="score-bar"><span style={{ width: `${Math.max(4, r.relative * 100)}%` }} /></div>
          <span className={`strength ${r.strength}`}>{STRENGTH_LABEL[r.strength]}</span>
        </div>
        {r.text && r.preview_url && <p className="snippet">{r.text.slice(0, 180)}{r.text.length > 180 ? '…' : ''}</p>}
        <div className="actions">
          <button className="btn small" onClick={() => onInspect(r)}><Eye size={15} /> Inspect</button>
          {isViewable(r.filename) ? (
            <a className="btn small ghost" href={api.url(r.open_url)} target="_blank" rel="noreferrer">
              <ExternalLink size={15} /> Open source
            </a>
          ) : (
            <a className="btn small ghost" href={api.url(`${r.original_url}?download=true`)}
              title={`Download the original; the match is at ${r.location_label}`}>
              <Download size={15} /> Download source
            </a>
          )}
        </div>
      </div>
    </article>
  )
}
