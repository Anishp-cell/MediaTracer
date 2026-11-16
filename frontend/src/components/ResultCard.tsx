import { Download, ExternalLink, Eye, MapPin, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { isViewable } from '../format'
import type { SearchResult } from '../types'
import { FamilyIcon } from './FamilyIcon'

const STRENGTH_LABEL = {
  strong: 'Strong match',
  moderate: 'Possible match',
  weak: 'Weak match',
}

interface Props {
  result: SearchResult
  onInspect: (r: SearchResult) => void
  viewMode?: 'grid' | 'list'
}

export function ResultCard({ result: r, onInspect, viewMode = 'grid' }: Props) {
  const [imgError, setImgError] = useState(false)
  const hasPreview = Boolean(r.preview_url && !imgError)

  return (
    <article className={`photo-card strength-${r.strength} ${viewMode === 'list' ? 'list-mode' : ''}`}>
      {/* Visual Canvas (Google Photos / Lightbox preview style) */}
      <div className="photo-canvas" onClick={() => onInspect(r)} role="button" tabIndex={0} aria-label={`Inspect ${r.filename}`}>
        {hasPreview ? (
          <img
            src={api.url(r.preview_url!)}
            alt={`Preview of ${r.filename}, ${r.location_label}`}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="photo-canvas-fallback">
            <div className={`canvas-icon-bubble family-bg-${r.family}`}>
              <FamilyIcon family={r.family} size={36} />
            </div>
            {r.text && <p className="fallback-text">{r.text.slice(0, 220)}</p>}
          </div>
        )}

        {/* Floating Glassmorphic Badges on the Image */}
        <div className="floating-top-row">
          <span className="glass-pill rank-pill">#{r.rank}</span>
          <span className={`glass-pill strength-pill ${r.strength}`}>
            <span className="pill-dot" />
            {STRENGTH_LABEL[r.strength]}
          </span>
        </div>

        <div className="floating-bottom-row">
          <span className="glass-pill location-pill" title={`Provenance: ${r.location_label}`}>
            <MapPin size={12} />
            <span>{r.location_label}</span>
          </span>

          <button
            type="button"
            className="glass-btn inspect-quick-btn"
            onClick={(e) => {
              e.stopPropagation()
              onInspect(r)
            }}
            title="Inspect evidence"
            aria-label="Inspect evidence"
          >
            <Eye size={15} />
          </button>
        </div>
      </div>

      {/* Clean Minimalist Metadata Bar */}
      <div className="photo-info">
        <div className="photo-meta-header">
          <div className="photo-title-wrap">
            <FamilyIcon family={r.family} size={17} />
            <h3 title={r.filename}>{r.filename}</h3>
          </div>
          <span className="score-percentage">{(r.relative * 100).toFixed(0)}%</span>
        </div>

        {/* Match signal tags */}
        <div className="photo-tags-row">
          <span className="tag tonal-tag">
            <Sparkles size={11} /> {r.match_type}
          </span>
          {r.also_matched.slice(0, 1).map((signal) => (
            <span key={signal} className="tag subtle-tag">
              +{signal}
            </span>
          ))}
        </div>

        {/* Context snippet */}
        {r.text && hasPreview && (
          <p className="photo-snippet" title={r.text}>
            {r.text.slice(0, 140)}
            {r.text.length > 140 ? '…' : ''}
          </p>
        )}

        {/* Quick action footer */}
        <div className="photo-footer-actions">
          <button type="button" className="action-pill primary" onClick={() => onInspect(r)}>
            <Eye size={13} /> View
          </button>
          {isViewable(r.filename) ? (
            <a className="action-pill ghost" href={api.url(r.open_url)} target="_blank" rel="noreferrer">
              <ExternalLink size={13} /> Open
            </a>
          ) : (
            <a
              className="action-pill ghost"
              href={api.url(`${r.original_url}?download=true`)}
              title={`Download original file`}
            >
              <Download size={13} /> Download
            </a>
          )}
        </div>
      </div>
    </article>
  )
}
