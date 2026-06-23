import { api } from './api'

// ──────────────────────────────────────────────────────────
// Types (mirror apps/lucky_draw serializers)
// ──────────────────────────────────────────────────────────
export type CampaignStatus = 'draft' | 'active' | 'paused' | 'ended'
export type EntryStatus = 'pending' | 'drawn' | 'redeemed' | 'expired' | 'invalid'
export type ReferralBonusType = 'extra_entry' | 'better_odds'
export type LuckyDrawLanguage = 'en' | 'zh-CN' | 'zh-TW'

export interface LuckyDrawPrize {
  id: string
  campaign: string
  label: string
  discount_percent: string
  weight: number
  max_wins_per_day: number | null
  max_total_wins: number | null
  wins_today_count: number
  wins_total_count: number
  active: boolean
  win_probability: number
  created_at: string
}

export interface LuckyDrawCampaign {
  id: string
  organization: string
  name: string
  description: string
  status: CampaignStatus
  start_date: string
  end_date: string | null
  daily_entry_limit_per_customer: number
  total_entry_limit_per_customer: number | null
  requires_name: boolean
  requires_phone: boolean
  requires_email: boolean
  consent_text: string
  privacy_notice_text: string
  default_language: LuckyDrawLanguage
  deliver_coupon_via_whatsapp: boolean
  referral_enabled: boolean
  referral_bonus_type: ReferralBonusType
  coupon_validity_days: number
  tag_redeemers_as_buffet: boolean
  prizes: LuckyDrawPrize[]
  entry_count: number
  max_discount: string | number
  created_at: string
  updated_at: string
}

export interface LuckyDrawEntry {
  id: string
  campaign: string
  crm_customer: string | null
  customer_name: string
  phone: string
  email: string
  table_number: string
  consent_given: boolean
  prize: string | null
  prize_discount: string | null
  coupon_code: string | null
  status: EntryStatus
  referred_by_entry: string | null
  referral_count: number
  whatsapp_sent_at: string | null
  reminder_sent_at: string | null
  entered_at: string
  drawn_at: string | null
  expires_at: string | null
  redeemed_at: string | null
  redeemed_by: string | null
}

export interface LuckyDrawQRCode {
  id: string
  campaign: string
  label: string
  qr_image: string | null
  poster_image: string | null
  url_token: string
  scan_count: number
  entry_url: string
  created_at: string
}

export interface PrizeDistribution {
  prize_id: string
  label: string
  discount_percent: number
  count: number
}

export interface CampaignStats {
  total_entries: number
  unique_customers: number
  total_scans: number
  drawn_count: number
  redeemed_count: number
  whatsapp_delivered: number
  whatsapp_delivery_rate: number
  prize_distribution: PrizeDistribution[]
  referral_funnel: {
    entries: number
    shared: number
    referred_entries: number
    referred_redeemed: number
    conversion_rate: number
  }
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

const BASE = '/v1/lucky_draw'

export const luckyDrawApi = {
  // ── Campaigns ──────────────────────────────────────────
  listCampaigns: async (params: { organization?: string; status?: CampaignStatus; search?: string } = {}): Promise<LuckyDrawCampaign[]> => {
    const res = await api.get(`${BASE}/campaigns/`, { params })
    return unwrap<LuckyDrawCampaign>(res.data)
  },

  getCampaign: async (id: string): Promise<LuckyDrawCampaign> => {
    const res = await api.get(`${BASE}/campaigns/${id}/`)
    return res.data as LuckyDrawCampaign
  },

  createCampaign: async (data: Partial<LuckyDrawCampaign>): Promise<LuckyDrawCampaign> => {
    const res = await api.post(`${BASE}/campaigns/`, data)
    return res.data as LuckyDrawCampaign
  },

  updateCampaign: async (id: string, data: Partial<LuckyDrawCampaign>): Promise<LuckyDrawCampaign> => {
    const res = await api.patch(`${BASE}/campaigns/${id}/`, data)
    return res.data as LuckyDrawCampaign
  },

  deleteCampaign: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/campaigns/${id}/`)
  },

  activate: async (id: string): Promise<LuckyDrawCampaign> => {
    const res = await api.post(`${BASE}/campaigns/${id}/activate/`)
    return res.data as LuckyDrawCampaign
  },

  pause: async (id: string): Promise<LuckyDrawCampaign> => {
    const res = await api.post(`${BASE}/campaigns/${id}/pause/`)
    return res.data as LuckyDrawCampaign
  },

  end: async (id: string): Promise<LuckyDrawCampaign> => {
    const res = await api.post(`${BASE}/campaigns/${id}/end/`)
    return res.data as LuckyDrawCampaign
  },

  stats: async (id: string): Promise<CampaignStats> => {
    const res = await api.get(`${BASE}/campaigns/${id}/stats/`)
    return res.data as CampaignStats
  },

  // ── Prizes (nested under campaign) ─────────────────────
  listPrizes: async (campaignId: string): Promise<LuckyDrawPrize[]> => {
    const res = await api.get(`${BASE}/campaigns/${campaignId}/prizes/`)
    return res.data as LuckyDrawPrize[]
  },

  addPrize: async (campaignId: string, data: Partial<LuckyDrawPrize>): Promise<LuckyDrawPrize> => {
    const res = await api.post(`${BASE}/campaigns/${campaignId}/prizes/`, data)
    return res.data as LuckyDrawPrize
  },

  updatePrize: async (prizeId: string, data: Partial<LuckyDrawPrize>): Promise<LuckyDrawPrize> => {
    const res = await api.patch(`${BASE}/prizes/${prizeId}/`, data)
    return res.data as LuckyDrawPrize
  },

  deletePrize: async (prizeId: string): Promise<void> => {
    await api.delete(`${BASE}/prizes/${prizeId}/`)
  },

  // ── QR codes ───────────────────────────────────────────
  listQrCodes: async (campaignId: string): Promise<LuckyDrawQRCode[]> => {
    const res = await api.get(`${BASE}/campaigns/${campaignId}/qr-codes/`)
    return res.data as LuckyDrawQRCode[]
  },

  createQrCode: async (campaignId: string, label: string): Promise<LuckyDrawQRCode> => {
    const res = await api.post(`${BASE}/campaigns/${campaignId}/qr-codes/`, { label })
    return res.data as LuckyDrawQRCode
  },

  // Fetch the poster through the authed axios instance (the endpoint requires a
  // Bearer token, so it can't be opened as a plain <a href> — that yields 401).
  // Returns an object URL the caller is responsible for revoking after download.
  fetchPosterObjectUrl: async (campaignId: string, qrId: string): Promise<string> => {
    const res = await api.get(
      `${BASE}/campaigns/${campaignId}/qr-codes/${qrId}/poster/`,
      { responseType: 'blob' },
    )
    return URL.createObjectURL(res.data as Blob)
  },

  // ── Entries ────────────────────────────────────────────
  listEntries: async (campaignId: string, params: { status?: EntryStatus; page?: number } = {}): Promise<Paginated<LuckyDrawEntry>> => {
    const res = await api.get(`${BASE}/campaigns/${campaignId}/entries/`, { params })
    return res.data as Paginated<LuckyDrawEntry>
  },

  redeem: async (couponCode: string): Promise<LuckyDrawEntry> => {
    const res = await api.post(`${BASE}/entries/redeem/`, { coupon_code: couponCode })
    return res.data as LuckyDrawEntry
  },
}

export const LUCKY_DRAW_LANGUAGES: LuckyDrawLanguage[] = ['zh-TW', 'zh-CN', 'en']
export const REFERRAL_BONUS_TYPES: ReferralBonusType[] = ['extra_entry', 'better_odds']
