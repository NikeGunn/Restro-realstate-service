/**
 * Market-aware money formatting. The market comes from the listing's (or
 * location's) country, so a Nepal agency sees "Rs 1,85,00,000 (1.85 crore)"
 * and a Hong Kong agency sees "HK$18,800,000" — mirroring the backend agent.
 */
type Market = { locale: string; currency: string; lakhCrore: boolean }

const MARKETS: Record<string, Market> = {
  nepal: { locale: 'en-IN', currency: 'NPR', lakhCrore: true },
  'hong kong': { locale: 'en-HK', currency: 'HKD', lakhCrore: false },
}
const DEFAULT: Market = { locale: 'en-US', currency: 'USD', lakhCrore: false }

export function marketFor(country?: string | null): Market {
  return MARKETS[(country ?? '').trim().toLowerCase()] ?? DEFAULT
}

export function formatMoney(amount: number | string | null | undefined, country?: string | null): string {
  const value = Number(amount)
  if (amount === null || amount === undefined || Number.isNaN(value)) return '—'
  const m = marketFor(country)
  if (m.currency === 'NPR') {
    const grouped = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value)
    if (value >= 10_000_000) return `Rs ${grouped} (${+(value / 10_000_000).toFixed(2)} crore)`
    if (value >= 100_000) return `Rs ${grouped} (${+(value / 100_000).toFixed(2)} lakh)`
    return `Rs ${grouped}`
  }
  return new Intl.NumberFormat(m.locale, { style: 'currency', currency: m.currency, maximumFractionDigits: 0 }).format(value)
}
