/**
 * Flexible color parsing for the Brand Kit picker.
 *
 * Accepts whatever a user copies from any design tool and normalizes it to a
 * canonical uppercase `#RRGGBB` (or `#RRGGBBAA` when an alpha channel is given).
 * Supported inputs:
 *   - hex:  `#fff`, `fff`, `#ffffff`, `ffffffff`, with or without leading `#`
 *   - rgb:  `rgb(225, 29, 72)`, `rgba(225 29 72 / 0.5)`, `225,29,72`
 *   - hsl:  `hsl(347, 77%, 50%)`, `hsla(347 77% 50% / 0.5)`
 *   - named CSS colors (a useful subset): `red`, `rebeccapurple`, …
 *
 * Returns the normalized hex string, or `null` if the input can't be understood.
 */

const NAMED_COLORS: Record<string, string> = {
  black: '#000000', white: '#FFFFFF', red: '#FF0000', green: '#008000',
  blue: '#0000FF', yellow: '#FFFF00', orange: '#FFA500', purple: '#800080',
  pink: '#FFC0CB', gray: '#808080', grey: '#808080', brown: '#A52A2A',
  cyan: '#00FFFF', magenta: '#FF00FF', lime: '#00FF00', navy: '#000080',
  teal: '#008080', olive: '#808000', maroon: '#800000', silver: '#C0C0C0',
  gold: '#FFD700', indigo: '#4B0082', violet: '#EE82EE', coral: '#FF7F50',
  salmon: '#FA8072', crimson: '#DC143C', turquoise: '#40E0D0',
  rebeccapurple: '#663399', transparent: '#00000000',
}

const clamp = (n: number, max: number) => Math.max(0, Math.min(max, n))
const toHex2 = (n: number) => clamp(Math.round(n), 255).toString(16).padStart(2, '0')

/** Parse the numbers out of a `rgb(...)` / `hsl(...)` / bare `a, b, c` string. */
function extractNumbers(input: string): number[] {
  // Split on commas, whitespace, and the CSS `/` alpha separator.
  return input
    .split(/[\s,/]+/)
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => (s.endsWith('%') ? parseFloat(s) : parseFloat(s)))
    .filter(n => !Number.isNaN(n))
}

function hslToHex(h: number, s: number, l: number, a?: number): string {
  s /= 100
  l /= 100
  const k = (n: number) => (n + h / 30) % 12
  const f = (n: number) => {
    const c = l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1))
    return Math.round(255 * c)
  }
  const base = `#${toHex2(f(0))}${toHex2(f(8))}${toHex2(f(4))}`.toUpperCase()
  return a !== undefined && a < 1 ? base + toHex2(a * 255).toUpperCase() : base
}

export function parseColor(raw: string): string | null {
  if (!raw) return null
  const input = raw.trim().toLowerCase()
  if (!input) return null

  // Named colors
  if (NAMED_COLORS[input]) return NAMED_COLORS[input]

  // Functional notations: rgb / rgba / hsl / hsla
  const fnMatch = input.match(/^(rgba?|hsla?)\s*\((.*)\)$/)
  if (fnMatch) {
    const kind = fnMatch[1]
    const nums = extractNumbers(fnMatch[2])
    if (kind.startsWith('rgb') && nums.length >= 3) {
      const [r, g, b, alpha] = nums
      const base = `#${toHex2(r)}${toHex2(g)}${toHex2(b)}`.toUpperCase()
      return alpha !== undefined && alpha < 1 ? base + toHex2(alpha * 255).toUpperCase() : base
    }
    if (kind.startsWith('hsl') && nums.length >= 3) {
      const [h, s, l, alpha] = nums
      return hslToHex(h, s, l, alpha)
    }
    return null
  }

  // Bare comma/space separated triplet → treat as rgb: `225, 29, 72`
  if (/^[\d.\s,/%]+$/.test(input) && /[\s,]/.test(input)) {
    const nums = extractNumbers(input)
    if (nums.length >= 3 && nums.length <= 4) {
      const [r, g, b, alpha] = nums
      const base = `#${toHex2(r)}${toHex2(g)}${toHex2(b)}`.toUpperCase()
      return alpha !== undefined && alpha < 1 ? base + toHex2(alpha * 255).toUpperCase() : base
    }
  }

  // Hex (with or without leading #), 3/4/6/8 digits
  const hex = input.replace(/^#/, '')
  if (/^[0-9a-f]{3}$/.test(hex)) {
    return `#${hex.split('').map(c => c + c).join('')}`.toUpperCase()
  }
  if (/^[0-9a-f]{4}$/.test(hex)) {
    return `#${hex.split('').map(c => c + c).join('')}`.toUpperCase()
  }
  if (/^[0-9a-f]{6}$/.test(hex) || /^[0-9a-f]{8}$/.test(hex)) {
    return `#${hex}`.toUpperCase()
  }

  return null
}

/** A 6-digit hex (dropping any alpha) suitable for an `<input type="color">`. */
export function toPickerHex(value: string): string {
  const parsed = parseColor(value)
  if (!parsed) return '#000000'
  return parsed.slice(0, 7)
}

/** True if the string parses to any understood color. */
export function isValidColor(value: string): boolean {
  return parseColor(value) !== null
}
