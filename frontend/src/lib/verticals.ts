/**
 * Which product areas belong to which business vertical — the single source of truth
 * for both the sidebar and the route guard. A real-estate agency must never see
 * restaurant tooling (menu, bookings, stock/recipes, coffee pass, coupon lucky draw)
 * and a restaurant must never see listings/leads.
 *
 * Shared areas (inbox, knowledge, CRM, content studio, billing, settings) are not listed.
 */
export type Vertical = 'restaurant' | 'real_estate'

const VERTICAL_ONLY_PREFIXES: Record<Vertical, string[]> = {
  restaurant: ['/restaurant', '/inventory', '/coffee-pass', '/lucky-draw'],
  real_estate: ['/realestate'],
}

function owner(path: string): Vertical | null {
  for (const [vertical, prefixes] of Object.entries(VERTICAL_ONLY_PREFIXES) as [Vertical, string[]][]) {
    if (prefixes.some((p) => path === p || path.startsWith(`${p}/`))) return vertical
  }
  return null
}

/** True when `path` is shared, or belongs to the org's vertical. Unknown vertical → allowed. */
export function isPathAllowed(path: string, businessType?: string | null): boolean {
  const v = owner(path)
  if (!v || !businessType || !(businessType in VERTICAL_ONLY_PREFIXES)) return true
  return v === businessType
}
