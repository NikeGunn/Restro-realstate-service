/**
 * Market-aware money formatting. The market comes from the listing's country, else the
 * organization's primary location country (set in Settings → Market & currency), so a
 * Nepal agency sees "Rs 1,85,00,000 (1.85 crore)", a Hong Kong agency "HK$18,800,000"
 * and a US agency "$1,250,000" — mirroring the backend agent (apps/ai_engine/agent/tools.py).
 */
type Market = {
  country: string; label: string; locale: string; currency: string; symbol: string; lakhCrore: boolean; timezone: string
}

/** Markets an admin can pick. `country` is stored on Location/PropertyListing. */
export const MARKET_OPTIONS: Market[] = [
  { country: 'Nepal', label: 'Nepal — Rs (NPR)', locale: 'en-IN', currency: 'NPR', symbol: 'Rs', lakhCrore: true, timezone: 'Asia/Kathmandu' },
  { country: 'India', label: 'India — ₹ (INR)', locale: 'en-IN', currency: 'INR', symbol: '₹', lakhCrore: true, timezone: 'Asia/Kolkata' },
  { country: 'Hong Kong', label: 'Hong Kong — HK$ (HKD)', locale: 'en-HK', currency: 'HKD', symbol: 'HK$', lakhCrore: false, timezone: 'Asia/Hong_Kong' },
  { country: 'USA', label: 'United States — $ (USD)', locale: 'en-US', currency: 'USD', symbol: '$', lakhCrore: false, timezone: 'America/New_York' },
]

const ALIASES: Record<string, string> = { 'united states': 'usa', us: 'usa', 'u.s.': 'usa', hk: 'hong kong', np: 'nepal' }
const BY_COUNTRY: Record<string, Market> = Object.fromEntries(MARKET_OPTIONS.map((m) => [m.country.toLowerCase(), m]))
const DEFAULT: Market = BY_COUNTRY['usa']

export function marketFor(country?: string | null): Market {
  const key = (country ?? '').trim().toLowerCase()
  return BY_COUNTRY[ALIASES[key] ?? key] ?? DEFAULT
}

/** Short prefix for money inputs: "Rs", "HK$", "$". */
export function currencySymbol(country?: string | null): string {
  return marketFor(country).symbol
}

export function formatMoney(amount: number | string | null | undefined, country?: string | null): string {
  const value = Number(amount)
  if (amount === null || amount === undefined || amount === '' || Number.isNaN(value)) return '—'
  const m = marketFor(country)
  if (m.lakhCrore) {
    const grouped = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value)
    if (value >= 10_000_000) return `${m.symbol} ${grouped} (${+(value / 10_000_000).toFixed(2)} crore)`
    if (value >= 100_000) return `${m.symbol} ${grouped} (${+(value / 100_000).toFixed(2)} lakh)`
    return `${m.symbol} ${grouped}`
  }
  return new Intl.NumberFormat(m.locale, { style: 'currency', currency: m.currency, maximumFractionDigits: 0 }).format(value)
}
