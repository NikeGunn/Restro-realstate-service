import { api } from './api'

// ──────────────────────────────────────────────────────────
// Types (mirror apps/crm serializers)
// ──────────────────────────────────────────────────────────
export type CustomerSource =
  | 'booking' | 'chatbot' | 'whatsapp' | 'instagram' | 'messenger'
  | 'manual' | 'lucky_draw' | 'wifi' | 'walk_in' | 'import'

export type ConsentStatus = 'not_asked' | 'given' | 'refused' | 'withdrawn'

export type Gender = 'male' | 'female' | 'other' | 'prefer_not_to_say' | ''

export type PreferredLanguage = 'en' | 'zh-CN' | 'zh-TW' | ''

export type ConsentSource =
  | 'booking_form' | 'lucky_draw_form' | 'wifi_form' | 'chatbot' | 'manual' | 'import'

export interface CRMTagBrief {
  id: string
  name: string
  color: string
  is_system: boolean
}

export interface CRMCustomer {
  id: string
  organization: string
  name: string
  phone: string | null
  phone_raw: string
  email: string | null
  whatsapp_number: string | null
  birthday: string | null
  birthday_month: number | null
  gender: Gender
  preferred_language: PreferredLanguage
  source: CustomerSource
  notes: string
  last_visit_date: string | null
  last_interaction_at: string | null
  visit_count: number
  marketing_consent_status: ConsentStatus
  is_active: boolean
  tags: CRMTagBrief[]
  created_at: string
  updated_at: string
}

export interface CRMTag {
  id: string
  organization: string
  name: string
  color: string
  is_system: boolean
  created_at: string
}

export interface CRMInteraction {
  id: string
  organization: string
  customer: string
  interaction_type: string
  source_channel: string
  summary: string
  related_entity_type: string
  related_entity_id: string | null
  created_at: string
  created_by: string | null
}

export interface CRMConsent {
  id: string
  organization: string
  customer: string
  consent_given: boolean
  consent_source: ConsentSource
  consent_text_snapshot: string
  consent_text_version: string
  marketing_channels_allowed: string[]
  opt_out_timestamp: string | null
  privacy_notice_version: string
  ip_address_hashed: string
  created_at: string
}

export interface SegmentRule {
  field: string
  op: string
  value: unknown
}

export interface SegmentFilterRules {
  logic: 'AND' | 'OR'
  rules: SegmentRule[]
}

export interface CRMSegment {
  id: string
  organization: string
  name: string
  description: string
  filter_rules: SegmentFilterRules | Record<string, never>
  customer_count: number
  is_dynamic: boolean
  last_evaluated_at: string | null
  created_at: string
  updated_at: string
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ──────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────
function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

const BASE = '/v1/crm'

export const crmApi = {
  // ── Customers ──────────────────────────────────────────
  listCustomers: async (params: {
    organization?: string
    source?: CustomerSource
    marketing_consent_status?: ConsentStatus
    is_active?: boolean
    search?: string
    page?: number
    ordering?: string
  } = {}): Promise<Paginated<CRMCustomer>> => {
    const res = await api.get(`${BASE}/customers/`, { params })
    return res.data as Paginated<CRMCustomer>
  },

  getCustomer: async (id: string): Promise<CRMCustomer> => {
    const res = await api.get(`${BASE}/customers/${id}/`)
    return res.data as CRMCustomer
  },

  createCustomer: async (data: Partial<CRMCustomer>): Promise<CRMCustomer> => {
    const res = await api.post(`${BASE}/customers/`, data)
    return res.data as CRMCustomer
  },

  updateCustomer: async (id: string, data: Partial<CRMCustomer>): Promise<CRMCustomer> => {
    const res = await api.patch(`${BASE}/customers/${id}/`, data)
    return res.data as CRMCustomer
  },

  deleteCustomer: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/customers/${id}/`)
  },

  customerTags: async (id: string): Promise<CRMTag[]> => {
    const res = await api.get(`${BASE}/customers/${id}/tags/`)
    return res.data as CRMTag[]
  },

  setCustomerTag: async (id: string, tagId: string, action: 'add' | 'remove'): Promise<CRMTag[]> => {
    const res = await api.post(`${BASE}/customers/${id}/tags/`, { tag_id: tagId, action })
    return res.data as CRMTag[]
  },

  customerInteractions: async (id: string): Promise<CRMInteraction[]> => {
    const res = await api.get(`${BASE}/customers/${id}/interactions/`)
    return unwrap<CRMInteraction>(res.data)
  },

  customerConsents: async (id: string): Promise<CRMConsent[]> => {
    const res = await api.get(`${BASE}/customers/${id}/consents/`)
    return unwrap<CRMConsent>(res.data)
  },

  mergeCustomer: async (primaryId: string, duplicateId: string): Promise<CRMCustomer> => {
    const res = await api.post(`${BASE}/customers/${primaryId}/merge/`, { duplicate_id: duplicateId })
    return res.data as CRMCustomer
  },

  // ── Tags ───────────────────────────────────────────────
  listTags: async (params: { organization?: string } = {}): Promise<CRMTag[]> => {
    const res = await api.get(`${BASE}/tags/`, { params })
    return unwrap<CRMTag>(res.data)
  },

  createTag: async (data: Partial<CRMTag>): Promise<CRMTag> => {
    const res = await api.post(`${BASE}/tags/`, data)
    return res.data as CRMTag
  },

  updateTag: async (id: string, data: Partial<CRMTag>): Promise<CRMTag> => {
    const res = await api.patch(`${BASE}/tags/${id}/`, data)
    return res.data as CRMTag
  },

  deleteTag: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/tags/${id}/`)
  },

  // ── Consent ────────────────────────────────────────────
  recordConsent: async (data: {
    customer: string
    consent_given: boolean
    consent_source: ConsentSource
    marketing_channels_allowed?: string[]
    consent_text_snapshot?: string
    consent_text_version?: string
  }): Promise<CRMConsent> => {
    const res = await api.post(`${BASE}/consents/record/`, data)
    return res.data as CRMConsent
  },

  // ── Segments ───────────────────────────────────────────
  listSegments: async (params: { organization?: string } = {}): Promise<CRMSegment[]> => {
    const res = await api.get(`${BASE}/segments/`, { params })
    return unwrap<CRMSegment>(res.data)
  },

  createSegment: async (data: Partial<CRMSegment>): Promise<CRMSegment> => {
    const res = await api.post(`${BASE}/segments/`, data)
    return res.data as CRMSegment
  },

  updateSegment: async (id: string, data: Partial<CRMSegment>): Promise<CRMSegment> => {
    const res = await api.patch(`${BASE}/segments/${id}/`, data)
    return res.data as CRMSegment
  },

  deleteSegment: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/segments/${id}/`)
  },

  previewSegment: async (organization: string, filterRules: SegmentFilterRules): Promise<number> => {
    const res = await api.post(
      `${BASE}/segments/preview/?organization=${organization}`,
      { filter_rules: filterRules },
    )
    return (res.data as { count: number }).count
  },

  segmentCustomers: async (id: string, page = 1): Promise<Paginated<CRMCustomer>> => {
    const res = await api.get(`${BASE}/segments/${id}/customers/`, { params: { page } })
    return res.data as Paginated<CRMCustomer>
  },

  segmentReadyToEngage: async (id: string, page = 1): Promise<Paginated<CRMCustomer>> => {
    const res = await api.get(`${BASE}/segments/${id}/ready-to-engage/`, { params: { page } })
    return res.data as Paginated<CRMCustomer>
  },
}

// Segment DSL metadata (mirrors segment_service whitelist) — drives the rule builder.
export const SEGMENT_FIELDS = [
  'source', 'marketing_consent_status', 'tags', 'last_visit_date',
  'last_interaction_at', 'preferred_language', 'birthday_month', 'visit_count',
] as const

export const SEGMENT_OPS = [
  'eq', 'neq', 'in', 'not_in', 'gte', 'lte', 'exists', 'not_exists',
] as const
