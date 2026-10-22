import type {
  Capabilities, Family, FileInfo, Health, IndexResponse, Job, RefineResponse, SearchResponse,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, init)
  } catch {
    throw new ApiError(0, 'Cannot reach the MediaTrace backend. Is it running on port 8000?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  url: (path: string) => BASE + path,
  health: () => request<Health>('/api/health'),
  capabilities: () => request<Capabilities>('/api/capabilities'),
  files: () => request<FileInfo[]>('/api/files'),
  removeFile: (id: string, deleteUploadedCopy: boolean) =>
    request<{ removed: boolean }>(`/api/files/${id}?delete_uploaded_copy=${deleteUploadedCopy}`, { method: 'DELETE' }),
  reindex: (id: string) => request<IndexResponse>(`/api/files/${id}/reindex`, { method: 'POST' }),
  rescan: () => request<IndexResponse>('/api/files/rescan', { method: 'POST' }),
  upload: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f, f.name))
    return request<IndexResponse>('/api/index', { method: 'POST', body: form })
  },
  indexLocal: (paths: string[], recursive = true) =>
    request<IndexResponse>('/api/index/local', json({ paths, recursive })),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  jobs: () => request<Job[]>('/api/jobs?limit=10'),
  cancelJob: (id: string) => request<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  search: (query: string, families: Family[] | null, mode: 'semantic' | 'hybrid', limit = 24) =>
    request<SearchResponse>('/api/search', json({ query, families, mode, limit })),
  searchImage: (image: File, families: Family[] | null, limit = 24) => {
    const form = new FormData()
    form.append('image', image, image.name)
    if (families?.length) form.append('families', families.join(','))
    form.append('limit', String(limit))
    return request<SearchResponse>('/api/search/image', { method: 'POST', body: form })
  },
  refine: (itemId: string, query: string) =>
    request<RefineResponse>(`/api/items/${itemId}/refine`, json({ query, step: 0.5 })),
}
