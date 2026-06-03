/** Billing display helpers — pure, module-level (hoisted, no per-render alloc). */
import type { CapStatus } from '@/services/billing'

export const MODULE_LABELS: Record<string, string> = {
  content_studio: 'Content Studio',
  inventory_ai: 'Inventory AI',
  chatbot_ai: 'Chatbot AI',
  messaging: 'Messaging',
}

// Brand-aligned palette for the by-module donut (indigo/violet family + accents).
export const MODULE_COLORS: Record<string, string> = {
  content_studio: '#6366f1', // indigo
  inventory_ai: '#8b5cf6',   // violet
  chatbot_ai: '#0ea5e9',     // sky
  messaging: '#10b981',      // emerald
}

export const CAP_THEME: Record<CapStatus, {
  label: string; ring: string; text: string; bg: string; bar: string
}> = {
  active: { label: 'Healthy', ring: 'ring-emerald-200', text: 'text-emerald-700', bg: 'bg-emerald-50', bar: 'bg-emerald-500' },
  warning_50: { label: 'Watch', ring: 'ring-amber-200', text: 'text-amber-700', bg: 'bg-amber-50', bar: 'bg-amber-500' },
  warning_80: { label: 'Near cap', ring: 'ring-orange-200', text: 'text-orange-700', bg: 'bg-orange-50', bar: 'bg-orange-500' },
  blocked: { label: 'Cap reached', ring: 'ring-rose-200', text: 'text-rose-700', bg: 'bg-rose-50', bar: 'bg-rose-500' },
}

export function hkd(value: string | number): string {
  const n = typeof value === 'string' ? parseFloat(value) : value
  return `HK$${(Number.isFinite(n) ? n : 0).toLocaleString('en-HK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function monthName(m: number): string {
  return MONTHS[m] || String(m)
}
