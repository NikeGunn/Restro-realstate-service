/**
 * AI Content Studio API client (Phase 5).
 * All endpoints under /v1/content-studio. unwrap() handles paginated/array responses.
 */
import { api } from './api'

const BASE = '/v1/content-studio'

function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

export type FieldType =
  | 'text' | 'textarea' | 'select' | 'number' | 'image_upload' | 'checkbox'

export interface UseCaseField {
  key: string
  label: string
  type: FieldType
  max_length?: number
  choices?: string[]
  optional?: boolean
}

export interface ContentUseCase {
  id: string
  use_case_key: string
  display_name: string
  description: string
  icon: string
  required_fields: UseCaseField[]
  optional_fields: UseCaseField[]
  supported_formats: string[]
  credit_cost: number
  active: boolean
  sort_order: number
}

export interface BrandKit {
  id: string
  organization: string
  restaurant_name: string
  logo_url: string | null
  brand_colors: string[]
  preferred_language: string
  default_cta: string
  phone: string
  whatsapp: string
  address: string
  website_url: string
  social_handles: Record<string, string>
  watermark_preference: 'none' | 'logo' | 'text'
  style_preferences: Record<string, string>
  created_at: string
  updated_at: string
}

export interface GenerationOutput {
  id: string
  job: string
  asset_url: string | null
  thumbnail_url: string | null
  file_type: string
  width: number
  height: number
  format: string
  download_count: number
  is_favorite: boolean
  created_at: string
}

export type JobStatus =
  | 'draft' | 'queued' | 'processing' | 'completed'
  | 'failed' | 'blocked_by_cap' | 'cancelled' | 'refunded'

export interface GenerationJob {
  id: string
  organization: string
  use_case: string
  use_case_key: string
  use_case_name: string
  input_payload: Record<string, unknown>
  aspect: 'square' | 'portrait' | 'landscape'
  output_resolution: string
  generated_prompt: string
  provider: string
  model: string
  status: JobStatus
  credits_estimated: number
  credits_used: number | null
  cost_estimated_usd: string
  cost_actual_usd: string | null
  output_count: number
  error_message: string
  outputs: GenerationOutput[]
  created_at: string
  completed_at: string | null
}

export const contentStudioApi = {
  listUseCases: async (): Promise<ContentUseCase[]> => {
    const res = await api.get(`${BASE}/use-cases/`)
    return unwrap<ContentUseCase>(res.data)
  },

  // Brand kit — one per org. Returns the first (or null).
  getBrandKit: async (organization: string): Promise<BrandKit | null> => {
    const res = await api.get(`${BASE}/brand-kits/`, { params: { organization } })
    const rows = unwrap<BrandKit>(res.data)
    return rows.length ? rows[0] : null
  },

  createBrandKit: async (data: Partial<BrandKit> & { organization: string }): Promise<BrandKit> => {
    const res = await api.post(`${BASE}/brand-kits/`, data)
    return res.data
  },

  updateBrandKit: async (id: string, data: Partial<BrandKit>): Promise<BrandKit> => {
    const res = await api.patch(`${BASE}/brand-kits/${id}/`, data)
    return res.data
  },

  uploadLogo: async (id: string, file: File): Promise<BrandKit> => {
    const form = new FormData()
    form.append('logo', file)
    const res = await api.post(`${BASE}/brand-kits/${id}/upload-logo/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  listJobs: async (params: { organization?: string; status?: string } = {}): Promise<GenerationJob[]> => {
    const res = await api.get(`${BASE}/jobs/`, { params })
    return unwrap<GenerationJob>(res.data)
  },

  getJob: async (id: string): Promise<GenerationJob> => {
    const res = await api.get(`${BASE}/jobs/${id}/`)
    return res.data
  },

  createJob: async (data: {
    organization: string
    use_case: string
    input_payload: Record<string, unknown>
    aspect?: string
    output_resolution?: string
  }): Promise<GenerationJob> => {
    const res = await api.post(`${BASE}/jobs/`, data)
    return res.data
  },

  cancelJob: async (id: string): Promise<GenerationJob> => {
    const res = await api.post(`${BASE}/jobs/${id}/cancel/`)
    return res.data
  },

  regenerateJob: async (id: string): Promise<GenerationJob> => {
    const res = await api.post(`${BASE}/jobs/${id}/regenerate/`)
    return res.data
  },

  favoriteOutput: async (id: string): Promise<{ id: string; is_favorite: boolean }> => {
    const res = await api.post(`${BASE}/outputs/${id}/favorite/`)
    return res.data
  },

  downloadOutput: async (id: string): Promise<{ id: string; url: string | null }> => {
    const res = await api.post(`${BASE}/outputs/${id}/download/`)
    return res.data
  },
}
