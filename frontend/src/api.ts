import {
  DEMO_CAPABILITIES,
  DEMO_FILES,
  DEMO_HEALTH,
  getDemoSearchResponse,
} from './mockData'
import type {
  Capabilities, Family, FileInfo, Health, IndexResponse, Job, RefineResponse, SearchResponse,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

// Demo mode allows designing and testing the full UI even when the heavy Python backend is not running.
let demoModeActive = localStorage.getItem('mediatrace_demo_mode') === 'true'

export function isDemoMode(): boolean {
  return demoModeActive
}

export function setDemoMode(active: boolean): void {
  demoModeActive = active
  localStorage.setItem('mediatrace_demo_mode', String(active))
}

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
  url: (path: string) => {
    if (!path) return ''
    if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) {
      return path
    }
    return BASE + path
  },

  health: async (): Promise<Health> => {
    if (demoModeActive) return DEMO_HEALTH
    try {
      return await request<Health>('/api/health')
    } catch (e) {
      if (demoModeActive) return DEMO_HEALTH
      throw e
    }
  },

  capabilities: async (): Promise<Capabilities> => {
    if (demoModeActive) return DEMO_CAPABILITIES
    try {
      return await request<Capabilities>('/api/capabilities')
    } catch (e) {
      if (demoModeActive) return DEMO_CAPABILITIES
      throw e
    }
  },

  files: async (): Promise<FileInfo[]> => {
    if (demoModeActive) return DEMO_FILES
    try {
      return await request<FileInfo[]>('/api/files')
    } catch (e) {
      if (demoModeActive) return DEMO_FILES
      throw e
    }
  },

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

  jobs: async (): Promise<Job[]> => {
    if (demoModeActive) return []
    try {
      return await request<Job[]>('/api/jobs?limit=10')
    } catch {
      return []
    }
  },

  cancelJob: (id: string) => request<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: 'POST' }),

  search: async (query: string, families: Family[] | null, mode: 'semantic' | 'hybrid', limit = 24): Promise<SearchResponse> => {
    if (demoModeActive) {
      return getDemoSearchResponse(query, mode)
    }
    try {
      return await request<SearchResponse>('/api/search', json({ query, families, mode, limit }))
    } catch (e) {
      if (demoModeActive) return getDemoSearchResponse(query, mode)
      throw e
    }
  },

  searchImage: async (image: File, families: Family[] | null, limit = 24): Promise<SearchResponse> => {
    if (demoModeActive) {
      return getDemoSearchResponse('Reference image match', 'semantic')
    }
    const form = new FormData()
    form.append('image', image, image.name)
    if (families?.length) form.append('families', families.join(','))
    form.append('limit', String(limit))
    return request<SearchResponse>('/api/search/image', { method: 'POST', body: form })
  },

  refine: async (itemId: string, query: string): Promise<RefineResponse> => {
    if (demoModeActive) {
      return {
        item_id: itemId,
        coarse_time: 84.0,
        best_time: 86.2,
        best_score: 0.92,
        samples: [
          { time: 84.0, score: 0.82 },
          { time: 85.0, score: 0.87 },
          { time: 86.2, score: 0.92 },
          { time: 87.5, score: 0.81 },
          { time: 89.0, score: 0.74 },
        ],
      }
    }
    return request<RefineResponse>(`/api/items/${itemId}/refine`, json({ query, step: 0.5 }))
  },
}
