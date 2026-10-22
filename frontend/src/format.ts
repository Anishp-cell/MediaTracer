import type { Family } from './types'

export const FAMILY_LABEL: Record<Family, string> = {
  image: 'Images',
  document: 'Documents',
  video: 'Video',
  audio: 'Audio',
  spreadsheet: 'Spreadsheets',
}

/** Formats a browser can display inline; others are offered as downloads. */
const VIEWABLE = /\.(jpe?g|png|webp|pdf|mp4|mov|webm|mkv|wav|mp3|m4a|flac|ogg|txt|md|markdown|csv)$/i
export const isViewable = (filename: string) => VIEWABLE.test(filename)

export function fmtTime(t: number): string {
  const s = Math.max(0, Math.floor(t))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

export function fmtDate(epoch: number | null): string {
  return epoch ? new Date(epoch * 1000).toLocaleString() : '—'
}
