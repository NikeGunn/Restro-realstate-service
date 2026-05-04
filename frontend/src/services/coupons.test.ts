import { afterEach, describe, expect, it, vi } from 'vitest'
import { couponsApi, api } from './api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('couponsApi.validate', () => {
  it('returns the API valid:true payload on success', async () => {
    vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: { valid: true, coupon: { code: 'AI-FINYEHK', description: '', plan_granted: 'power', duration_days: 30 } },
    })
    const result = await couponsApi.validate('AI-FINYEHK', 'org-1')
    expect(result.valid).toBe(true)
    expect(result.coupon?.code).toBe('AI-FINYEHK')
  })

  it('returns valid:false with detail when API rejects', async () => {
    vi.spyOn(api, 'post').mockRejectedValueOnce({
      response: { data: { detail: 'This coupon has expired.' } },
    })
    const result = await couponsApi.validate('OLD', 'org-1')
    expect(result.valid).toBe(false)
    expect(result.detail).toBe('This coupon has expired.')
  })
})

describe('couponsApi.redeem', () => {
  it('posts to /coupons/redeem/ and returns the redemption record', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: {
        id: 'r1',
        coupon: { code: 'AI-FINYEHK', description: '', plan_granted: 'power', duration_days: 30 },
        organization: 'org-1',
        redeemed_at: '2026-05-04T00:00:00Z',
        granted_until: '2026-06-03T00:00:00Z',
      },
    })
    const result = await couponsApi.redeem('AI-FINYEHK', 'org-1')
    expect(spy).toHaveBeenCalledWith('/coupons/redeem/', { code: 'AI-FINYEHK', organization: 'org-1' })
    expect(result.coupon.plan_granted).toBe('power')
  })
})
