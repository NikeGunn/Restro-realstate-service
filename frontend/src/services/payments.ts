/**
 * Payments API client (Stripe credit-pack purchases).
 * Endpoints under /v1/payments. Card data never touches our frontend —
 * we redirect to Stripe's hosted Checkout page.
 */
import { api } from './api'

const BASE = '/v1/payments'

function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

export interface CreditPack {
  id: string
  slug: string
  name: string
  description: string
  credits: number
  price_hkd: string
  currency: string
  sort_order: number
}

export interface CreditPurchase {
  id: string
  organization: string
  pack: string
  pack_name: string
  status: 'pending' | 'paid' | 'failed' | 'expired' | 'refunded'
  credits: number
  amount_hkd: string
  currency: string
  stripe_receipt_url: string
  refunded_amount_hkd: string
  created_at: string
  paid_at: string | null
}

export interface CheckoutResult {
  purchase_id: string
  checkout_url: string
  session_id: string
  credits: number
  amount_hkd: string
  currency: string
}

export const paymentsApi = {
  listPacks: async (): Promise<CreditPack[]> => {
    const res = await api.get(`${BASE}/packs/`)
    return unwrap<CreditPack>(res.data)
  },

  createCheckout: async (organization: string, pack: string): Promise<CheckoutResult> => {
    const res = await api.post(`${BASE}/checkout/`, { organization, pack })
    return res.data
  },

  listPurchases: async (organization: string): Promise<CreditPurchase[]> => {
    const res = await api.get(`${BASE}/purchases/`, { params: { organization } })
    return unwrap<CreditPurchase>(res.data)
  },
}
