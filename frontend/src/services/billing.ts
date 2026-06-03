/**
 * Billing & Usage API client (Phase 6).
 * All endpoints under /v1/billing. unwrap() handles paginated/array responses.
 */
import { api } from './api'

const BASE = '/v1/billing'

function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

export type CapStatus = 'active' | 'warning_50' | 'warning_80' | 'blocked'

export interface CreditBalance {
  id: string
  organization: string
  free_credits_remaining: number
  paid_credits_remaining: number
  free_credits_used_this_month: number
  paid_credits_used_this_month: number
  reserved_credits: number
  total_available: number
  current_estimated_spend_hkd: string
  cap_status: CapStatus
  period_start: string
  updated_at: string
}

export interface ModuleUsage {
  credits: number
  billable_hkd: string
  count: number
}

export interface UsageSummary {
  organization: string
  period_start: string
  free_credits_remaining: number
  paid_credits_remaining: number
  reserved_credits: number
  total_available: number
  free_credits_used_this_month: number
  paid_credits_used_this_month: number
  current_estimated_spend_hkd: string
  monthly_ai_spend_cap_hkd: string
  spend_percent_of_cap: number
  cap_status: CapStatus
  by_module: Record<string, ModuleUsage>
}

export interface UsageLimit {
  id: string
  organization: string
  monthly_ai_spend_cap_hkd: string
  monthly_image_credits_extra_allowed: number
  alert_at_percent: number
  updated_at: string
}

export interface UsageEvent {
  id: string
  organization: string
  user: string | null
  module: string
  event_type: string
  provider: string
  model: string
  credits_used: number
  is_free_credit: boolean
  cost_usd: string
  cost_hkd: string
  billable_amount_hkd: string
  status: 'reserved' | 'success' | 'failed' | 'refunded'
  reference_id: string | null
  created_at: string
  metadata: Record<string, unknown>
}

export interface MonthlySummary {
  id: string
  organization: string
  year: number
  month: number
  free_credits_used: number
  paid_credits_used: number
  total_cost_usd: string
  total_cost_hkd: string
  total_billable_hkd: string
  image_generations: number
  ai_queries: number
  created_at: string
}

export const billingApi = {
  getSummary: async (organization: string): Promise<UsageSummary> => {
    const res = await api.get(`${BASE}/summary/`, { params: { organization } })
    return res.data
  },

  getBalance: async (organization: string): Promise<CreditBalance> => {
    const res = await api.get(`${BASE}/balance/`, { params: { organization } })
    return res.data
  },

  getLimit: async (organization: string): Promise<UsageLimit> => {
    const res = await api.get(`${BASE}/limit/`, { params: { organization } })
    return res.data
  },

  updateLimit: async (
    organization: string,
    data: Partial<Pick<UsageLimit, 'monthly_ai_spend_cap_hkd' | 'alert_at_percent' | 'monthly_image_credits_extra_allowed'>>,
  ): Promise<UsageLimit> => {
    const res = await api.patch(`${BASE}/limit/?organization=${organization}`, data)
    return res.data
  },

  listEvents: async (params: {
    organization: string; module?: string; status?: string
  }): Promise<UsageEvent[]> => {
    const res = await api.get(`${BASE}/usage-events/`, { params })
    return unwrap<UsageEvent>(res.data)
  },

  listMonthlySummaries: async (organization: string): Promise<MonthlySummary[]> => {
    const res = await api.get(`${BASE}/monthly-summaries/`, { params: { organization } })
    return unwrap<MonthlySummary>(res.data)
  },
}
