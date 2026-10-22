export type Family = 'image' | 'document' | 'video' | 'audio' | 'spreadsheet'

export interface ModelStatus {
  model_id: string
  state: 'not_loaded' | 'loading' | 'ready' | 'error'
  error: string | null
  device: string | null
  dtype: string | null
  gpu: string | null
  modalities: string[]
  modality_errors: Record<string, string>
  input_forms: Record<string, string>
  load_seconds: number | null
  embedding_dim: number
}

export interface Health {
  status: 'ok' | 'degraded'
  model: ModelStatus
  indexed_files: number
  indexed_items: number
}

export interface AdapterCapability {
  family: Family
  formats: Record<string, string>
  enabled: boolean
  reason: string | null
}

export interface Capabilities {
  adapters: AdapterCapability[]
  accepted_extensions: string[]
  max_upload_mb: number
  image_query: boolean
  video_refine: boolean
}

export interface Registration {
  file_id: string | null
  filename: string
  action: 'new' | 'updated' | 'unchanged' | 'duplicate' | 'rejected'
  reason: string | null
}

export interface IndexResponse {
  job_id: string | null
  files: Registration[]
}

export interface Job {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  file_ids: string[]
  total: number
  done: number
  failed: number
  current: string | null
  progress: number
  message: string | null
  errors: { file_id: string; filename: string; error: string }[]
  created_at: number
  updated_at: number
}

export interface FileInfo {
  id: string
  filename: string
  family: Family
  format: string
  origin: 'upload' | 'local'
  size_bytes: number
  sha256: string
  status: 'queued' | 'processing' | 'indexed' | 'failed'
  error: string | null
  item_count: number
  created_at: number
  indexed_at: number | null
  modified_at: number | null
  model_id: string | null
  source_path: string | null
}

export interface Locator {
  type: 'image' | 'pdf_page' | 'slide' | 'video' | 'audio' | 'sheet' | 'text' | 'docx'
  [key: string]: unknown
}

export interface SearchResult {
  rank: number
  item_id: string
  file_id: string
  filename: string
  family: Family
  kind: string
  modality: 'text' | 'image' | 'audio'
  match_type: string
  locator: Locator
  location_label: string
  text: string | null
  preview_url: string | null
  original_url: string
  open_url: string
  score: number
  semantic_score: number
  keyword_score: number
  relative: number
  strength: 'strong' | 'moderate' | 'weak'
  also_matched: string[]
}

export interface SearchResponse {
  query: string
  mode: 'semantic' | 'hybrid'
  families: Family[] | null
  results: SearchResult[]
  searched_items: number
  took_ms: number
  notice: string | null
}

export interface RefineResponse {
  item_id: string
  coarse_time: number
  best_time: number
  best_score: number
  samples: { time: number; score: number }[]
}
