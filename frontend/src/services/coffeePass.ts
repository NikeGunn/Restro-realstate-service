import { api } from './api'

// ──────────────────────────────────────────────────────────
// Types (mirror apps/coffee_pass serializers)
// ──────────────────────────────────────────────────────────
export type PlanStatus = 'draft' | 'active' | 'paused' | 'archived'
export type PassStatus =
  | 'pending_payment' | 'active' | 'expired' | 'suspended' | 'cancelled'
export type RedemptionStatus = 'redeemed' | 'voided'
export type Sentiment = 'good' | 'okay' | 'not_good'
export type RoutineContext =
  | 'work_nearby' | 'study_nearby' | 'live_nearby' | 'occasional' | 'prefer_not_to_say'

export interface MenuItemBrief {
  id: string
  name: string
  price: string
  item_type: string
  is_available: boolean
  sold_out: boolean
}

export interface BreakEven {
  average_eligible_price: string | null
  saving_per_visit: string | null
  break_even_visits: number | null
  max_recommended_visits?: number
}

export interface CoffeePassPlan {
  id: string
  organization: string
  location: string
  location_name: string
  name: string
  description: string
  price_hkd: string
  currency: string
  discount_percent: string
  duration_days: number
  eligible_items: string[]
  eligible_items_detail: MenuItemBrief[]
  allow_neutral_feedback: boolean
  status: PlanStatus
  break_even_acknowledged: boolean
  public_token: string
  public_url_path: string
  active_pass_count: number
  break_even: BreakEven | null
  created_at: string
  updated_at: string
}

export interface ActivationReadiness {
  ready: boolean
  errors: string[]
  warnings: string[]
  break_even: BreakEven
}

export interface CoffeePass {
  id: string
  organization: string
  location: string
  location_name: string
  customer: string
  customer_name: string
  plan: string
  plan_name: string
  purchase: string
  status: PassStatus
  discount_percent: string
  starts_at: string
  expires_at: string
  suspension_reason: string
  cancelled_at: string | null
  cancel_reason: string
  redemption_count: number
  total_saved_hkd: string
  is_redeemable: boolean
  created_at: string
}

export interface CoffeePassRedemption {
  id: string
  organization: string
  location: string
  location_name: string
  coffee_pass: string
  customer: string
  customer_name: string
  redeemed_by: string | null
  redeemed_by_email: string | null
  eligible_subtotal_hkd: string
  discount_amount_hkd: string
  discount_percent_applied: string
  pos_receipt_reference: string
  status: RedemptionStatus
  redeemed_at: string
  voided_at: string | null
  void_reason: string
  created_at: string
}

export interface CoffeeExperience {
  id: string
  organization: string
  location: string
  customer: string
  customer_name: string
  sentiment: Sentiment
  comment: string
  routine_context: RoutineContext | ''
  source: string
  offer_shown_at: string | null
  created_at: string
}

export interface CoffeePassPurchase {
  id: string
  organization: string
  location: string
  customer: string
  customer_name: string
  plan: string
  status: string
  amount_hkd: string
  currency: string
  stripe_receipt_url: string
  refunded_amount_hkd: string
  paid_at: string | null
  created_at: string
}

/** Staff redemption preview. Deliberately excludes private feedback (A.9). */
export interface ResolveResult {
  valid: boolean
  reason_code: string
  pass_id?: string
  customer_name?: string
  plan_name?: string
  discount_percent?: string
  expires_at?: string
  location_id?: string
  eligible_items?: { id: string; name: string; price: string }[]
  redemption_count?: number
  verification_token_id?: string
  token_expires_at?: string
}

export interface AnalyticsSummary {
  window: { from: string; to: string }
  sales: {
    checkout_started: number
    purchases_paid: number
    conversion_rate: number
    gross_revenue_hkd: string
    refunded_hkd: string
    net_revenue_hkd: string
  }
  passes: {
    total: number
    active: number
    expired: number
    cancelled: number
    suspended: number
  }
  redemptions: {
    count: number
    voided_count: number
    eligible_subtotal_hkd: string
    total_discount_hkd: string
    average_saving_hkd: string
    missing_receipt_reference: number
  }
  retention: {
    passes_measured: number
    first_redemption_within_7_days: number
    first_redemption_rate: number
    repeat_customers: number
    repeat_rate: number
    never_redeemed: number
  }
  feedback: {
    good: number
    okay: number
    not_good: number
    offers_shown: number
  }
}

export interface Anomaly {
  code: string
  detail: string
  count?: number
  customer_id?: string
  user_id?: string | null
  reference?: string
}

const BASE = '/v1/coffee-pass'

/** DRF returns either a paginated envelope or a bare array depending on the view. */
function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

export const coffeePassApi = {
  // ── Plans ───────────────────────────────────────────────
  listPlans: async (params?: { organization?: string; status?: PlanStatus }) => {
    const { data } = await api.get(`${BASE}/plans/`, { params })
    return unwrap<CoffeePassPlan>(data)
  },
  getPlan: async (id: string) => {
    const { data } = await api.get<CoffeePassPlan>(`${BASE}/plans/${id}/`)
    return data
  },
  createPlan: async (payload: Partial<CoffeePassPlan>) => {
    const { data } = await api.post<CoffeePassPlan>(`${BASE}/plans/`, payload)
    return data
  },
  updatePlan: async (id: string, payload: Partial<CoffeePassPlan>) => {
    const { data } = await api.patch<CoffeePassPlan>(`${BASE}/plans/${id}/`, payload)
    return data
  },
  deletePlan: async (id: string) => {
    await api.delete(`${BASE}/plans/${id}/`)
  },
  /** Dry-run the activation rules so the owner sees break-even before committing. */
  activationPreview: async (id: string) => {
    const { data } = await api.get<ActivationReadiness>(
      `${BASE}/plans/${id}/activation-preview/`,
    )
    return data
  },
  // The menu items a Coffee Pass may cover, decided by the SERVER.
  //
  // Never re-filter a full menu on the client: the previous client-side filter
  // fell back to "show everything" when it matched nothing, which is how food
  // items became pass-eligible in production. An empty `results` means the org
  // has no coffee on the menu yet — show that, never a food list.
  eligibleItems: async (organization: string) => {
    const { data } = await api.get<{
      count: number
      eligible_item_types: string[]
      results: MenuItemBrief[]
    }>(`${BASE}/plans/eligible-items/`, { params: { organization } })
    return data
  },

  // QR + poster come through the authed axios instance (the endpoints need a
  // Bearer token, so a plain <a href> would 401). Returns an object URL the
  // caller must revoke after triggering the download.
  fetchPlanQrObjectUrl: async (id: string): Promise<string> => {
    const res = await api.get(`${BASE}/plans/${id}/qr/`, { responseType: 'blob' })
    return URL.createObjectURL(res.data as Blob)
  },

  fetchPlanPosterObjectUrl: async (id: string, language = 'zh-TW'): Promise<string> => {
    const res = await api.get(`${BASE}/plans/${id}/poster/`, {
      responseType: 'blob', params: { language },
    })
    return URL.createObjectURL(res.data as Blob)
  },

  activatePlan: async (id: string) => {
    const { data } = await api.post<CoffeePassPlan>(`${BASE}/plans/${id}/activate/`)
    return data
  },
  pausePlan: async (id: string) => {
    const { data } = await api.post<CoffeePassPlan>(`${BASE}/plans/${id}/pause/`)
    return data
  },

  // ── Passes ──────────────────────────────────────────────
  listPasses: async (params?: {
    organization?: string; status?: PassStatus; search?: string; location?: string
  }) => {
    const { data } = await api.get(`${BASE}/passes/`, { params })
    return unwrap<CoffeePass>(data)
  },
  getPass: async (id: string) => {
    const { data } = await api.get<CoffeePass>(`${BASE}/passes/${id}/`)
    return data
  },
  passRedemptions: async (id: string) => {
    const { data } = await api.get(`${BASE}/passes/${id}/redemptions/`)
    return unwrap<CoffeePassRedemption>(data)
  },
  suspendPass: async (id: string, reason: string) => {
    const { data } = await api.post<CoffeePass>(`${BASE}/passes/${id}/suspend/`, { reason })
    return data
  },
  restorePass: async (id: string) => {
    const { data } = await api.post<CoffeePass>(`${BASE}/passes/${id}/restore/`)
    return data
  },

  // ── Till operations ─────────────────────────────────────
  /** Validate a scanned/typed code. Does NOT consume it. */
  resolveCode: async (payload: {
    code: string; organization?: string; location?: string
  }) => {
    const { data } = await api.post<ResolveResult>(`${BASE}/verification/resolve/`, payload)
    return data
  },
  /** Consume the code and record the redemption. The discount is server-calculated. */
  createRedemption: async (payload: {
    verification_token_id: string
    eligible_subtotal_hkd: string
    pos_receipt_reference?: string
    organization?: string
    location?: string
  }) => {
    const { data } = await api.post<CoffeePassRedemption>(
      `${BASE}/redemptions/create/`, payload,
    )
    return data
  },

  // ── Redemptions ─────────────────────────────────────────
  listRedemptions: async (params?: {
    organization?: string; status?: RedemptionStatus
    coffee_pass?: string; missing_receipt?: 'true'
  }) => {
    const { data } = await api.get(`${BASE}/redemptions/`, { params })
    return unwrap<CoffeePassRedemption>(data)
  },
  voidRedemption: async (id: string, reason: string) => {
    const { data } = await api.post<CoffeePassRedemption>(
      `${BASE}/redemptions/${id}/void/`, { reason },
    )
    return data
  },

  // ── Experiences / purchases ─────────────────────────────
  listExperiences: async (params?: { organization?: string; sentiment?: Sentiment }) => {
    const { data } = await api.get(`${BASE}/experiences/`, { params })
    return unwrap<CoffeeExperience>(data)
  },
  listPurchases: async (params?: { organization?: string; status?: string }) => {
    const { data } = await api.get(`${BASE}/purchases/`, { params })
    return unwrap<CoffeePassPurchase>(data)
  },
  refundPurchase: async (id: string, payload?: { amount_hkd?: string }) => {
    const { data } = await api.post(`${BASE}/purchases/${id}/refund/`, payload ?? {})
    return data
  },

  // ── Analytics ───────────────────────────────────────────
  summary: async (params?: {
    organization?: string; location?: string; date_from?: string; date_to?: string
  }) => {
    const { data } = await api.get<AnalyticsSummary>(`${BASE}/analytics/summary/`, { params })
    return data
  },
  anomalies: async (params?: { organization?: string; location?: string }) => {
    const { data } = await api.get<{ anomalies: Anomaly[] }>(
      `${BASE}/analytics/anomalies/`, { params },
    )
    return data.anomalies
  },
}

/** Public customer page path for a plan's QR code. */
export function publicPassUrl(plan: Pick<CoffeePassPlan, 'public_token'>) {
  return `${window.location.origin}/public/coffee-pass/${plan.public_token}/`
}
