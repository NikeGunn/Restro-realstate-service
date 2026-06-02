/** Map a use-case `icon` slug (lucide name from the backend) to a component. */
import {
  BadgePercent, Utensils, ConciergeBell, CalendarCheck, PartyPopper,
  Martini, Sparkles, Quote, Gift, Wifi, Ticket, Layers, Image as ImageIcon,
  type LucideIcon,
} from 'lucide-react'

const MAP: Record<string, LucideIcon> = {
  'badge-percent': BadgePercent,
  'utensils': Utensils,
  'concierge-bell': ConciergeBell,
  'calendar-star': CalendarCheck,
  'party-popper': PartyPopper,
  'martini': Martini,
  'sparkles': Sparkles,
  'quote': Quote,
  'gift': Gift,
  'wifi': Wifi,
  'ticket': Ticket,
  'layers': Layers,
  'image': ImageIcon,
}

export function useCaseIcon(slug: string): LucideIcon {
  return MAP[slug] || ImageIcon
}
