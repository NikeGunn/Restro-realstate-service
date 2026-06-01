import { useState, useMemo, useEffect, useRef } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/auth'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { ScrollArea } from '@/components/ui/scroll-area'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import {
  LayoutDashboard,
  Inbox,
  Bell,
  BookOpen,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  X,
  MessageSquare,
  UtensilsCrossed,
  CalendarDays,
  Building2,
  Users,
  Phone,
  Package,
  Truck,
  ArrowLeftRight,
  ClipboardList,
  ChefHat,
  Upload,
  PieChart,
  ScrollText,
  Sparkles,
  Boxes,
  ChevronRight,
  TrendingUp,
  MapPin,
  Contact,
  Tag,
  Filter,
} from 'lucide-react'

type NavLeaf = {
  kind: 'leaf'
  path: string
  labelKey: string
  icon: React.ComponentType<{ className?: string }>
}

type NavGroup = {
  kind: 'group'
  id: string
  labelKey: string
  icon: React.ComponentType<{ className?: string }>
  /** Any active path beginning with this prefix auto-expands the group. */
  pathPrefix: string
  children: NavLeaf[]
}

type NavItem = NavLeaf | NavGroup

const coreNavKeys: NavLeaf[] = [
  { kind: 'leaf', path: '/dashboard', labelKey: 'nav.dashboard', icon: LayoutDashboard },
  { kind: 'leaf', path: '/inbox', labelKey: 'nav.inbox', icon: Inbox },
  { kind: 'leaf', path: '/alerts', labelKey: 'nav.alerts', icon: Bell },
  { kind: 'leaf', path: '/knowledge', labelKey: 'nav.knowledgeBase', icon: BookOpen },
  { kind: 'leaf', path: '/analytics', labelKey: 'nav.analytics', icon: BarChart3 },
]

const restaurantNavKeys: NavLeaf[] = [
  { kind: 'leaf', path: '/restaurant/menu', labelKey: 'nav.menu', icon: UtensilsCrossed },
  { kind: 'leaf', path: '/restaurant/bookings', labelKey: 'nav.bookings', icon: CalendarDays },
]

const realEstateNavKeys: NavLeaf[] = [
  { kind: 'leaf', path: '/realestate/properties', labelKey: 'nav.properties', icon: Building2 },
  { kind: 'leaf', path: '/realestate/leads', labelKey: 'nav.leads', icon: Users },
]

/**
 * Inventory is a single sidebar GROUP. Its children are the full Plane B
 * surface — clicking the parent toggles the section, clicking the dashboard
 * sub-item lands on `/inventory`. Future Phase 4-6 features add new children
 * here rather than crowding the top-level sidebar.
 */
const inventoryGroup: NavGroup = {
  kind: 'group',
  id: 'inventory',
  labelKey: 'nav.inventory',
  icon: Boxes,
  pathPrefix: '/inventory',
  children: [
    { kind: 'leaf', path: '/inventory', labelKey: 'nav.inventoryDashboard', icon: LayoutDashboard },
    { kind: 'leaf', path: '/inventory/items', labelKey: 'nav.inventoryItems', icon: Package },
    { kind: 'leaf', path: '/inventory/suppliers', labelKey: 'nav.inventorySuppliers', icon: Truck },
    { kind: 'leaf', path: '/inventory/purchase-orders', labelKey: 'nav.inventoryPurchaseOrders', icon: ClipboardList },
    { kind: 'leaf', path: '/inventory/recipes', labelKey: 'nav.inventoryRecipes', icon: ChefHat },
    { kind: 'leaf', path: '/inventory/movements', labelKey: 'nav.inventoryMovements', icon: ArrowLeftRight },
    { kind: 'leaf', path: '/inventory/imports/sales', labelKey: 'nav.inventoryImports', icon: Upload },
    { kind: 'leaf', path: '/inventory/reports', labelKey: 'nav.inventoryReports', icon: PieChart },
    { kind: 'leaf', path: '/inventory/alerts', labelKey: 'nav.inventoryAlerts', icon: Bell },
    { kind: 'leaf', path: '/inventory/audit-log', labelKey: 'nav.inventoryAudit', icon: ScrollText },
    { kind: 'leaf', path: '/inventory/ai', labelKey: 'nav.inventoryAI', icon: Sparkles },
    { kind: 'leaf', path: '/inventory/stock-take', labelKey: 'nav.inventoryStockTake', icon: ClipboardList },
    { kind: 'leaf', path: '/inventory/analytics', labelKey: 'nav.inventoryAnalytics', icon: TrendingUp },
    { kind: 'leaf', path: '/inventory/location-pricing', labelKey: 'nav.inventoryLocationPricing', icon: MapPin },
  ],
}

// CRM Lite (Phase 1) — collapsible group, shared across verticals.
const crmGroup: NavGroup = {
  kind: 'group',
  id: 'crm',
  labelKey: 'nav.crm',
  icon: Contact,
  pathPrefix: '/crm',
  children: [
    { kind: 'leaf', path: '/crm', labelKey: 'nav.crmDashboard', icon: LayoutDashboard },
    { kind: 'leaf', path: '/crm/customers', labelKey: 'nav.crmCustomers', icon: Users },
    { kind: 'leaf', path: '/crm/tags', labelKey: 'nav.crmTags', icon: Tag },
    { kind: 'leaf', path: '/crm/segments', labelKey: 'nav.crmSegments', icon: Filter },
  ],
}

const settingsNavKey: NavLeaf = { kind: 'leaf', path: '/settings', labelKey: 'nav.settings', icon: Settings }
const channelsNavKey: NavLeaf = { kind: 'leaf', path: '/settings/channels', labelKey: 'nav.channels', icon: Phone }

const GROUP_STATE_STORAGE_KEY = 'sidebar.groupState.v1'

function loadGroupState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(GROUP_STATE_STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveGroupState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(GROUP_STATE_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // localStorage may be disabled — non-fatal
  }
}

export function DashboardLayout() {
  const { t } = useTranslation()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const { user, currentOrganization, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  // Build navigation items based on organization business type
  const navItems = useMemo<NavItem[]>(() => {
    const items: NavItem[] = [...coreNavKeys]

    const businessType = currentOrganization?.business_type
    if (businessType === 'restaurant') {
      items.push(...restaurantNavKeys)
    } else if (businessType === 'real_estate') {
      items.push(...realEstateNavKeys)
    } else {
      items.push(...restaurantNavKeys)
      items.push(...realEstateNavKeys)
    }

    // Inventory is shared across both verticals — single collapsible group.
    items.push(inventoryGroup)

    // CRM Lite — shared across verticals.
    items.push(crmGroup)

    items.push(settingsNavKey)
    items.push(channelsNavKey)
    return items
  }, [currentOrganization?.business_type])

  // Group expand/collapse state, persisted across reloads.
  const [groupState, setGroupState] = useState<Record<string, boolean>>(loadGroupState)

  // Auto-expand a group ONCE per pathname change — never on every render.
  //
  // Why a ref instead of putting `groupState` in deps: if we depend on
  // groupState, the effect re-runs after the user manually collapses a
  // group, sees the path is still under /inventory/*, and re-opens it
  // immediately. The user can then never close the group while browsing
  // inventory pages. Tracking the last-auto-expanded path lets us run
  // exactly once per real navigation and respect manual collapses.
  const lastAutoExpandedPath = useRef<string | null>(null)
  useEffect(() => {
    if (lastAutoExpandedPath.current === location.pathname) return
    lastAutoExpandedPath.current = location.pathname

    for (const item of navItems) {
      if (item.kind !== 'group') continue
      if (!location.pathname.startsWith(item.pathPrefix)) continue
      setGroupState(prev => {
        if (prev[item.id]) return prev
        const next = { ...prev, [item.id]: true }
        saveGroupState(next)
        return next
      })
    }
  }, [location.pathname, navItems])

  function toggleGroup(id: string) {
    setGroupState(prev => {
      const next = { ...prev, [id]: !prev[id] }
      saveGroupState(next)
      return next
    })
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userInitials = user
    ? `${user.first_name?.[0] || ''}${user.last_name?.[0] || ''}`.toUpperCase() || user.email[0].toUpperCase()
    : '?'

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar.
         z-index ladder (kept in sync with components/ui/*):
           z-30  page Cards / sticky headers
           z-40  sidebar (this)                  ← below all overlays
           z-90  Dialog overlay (backdrop)
           z-91  Dialog content
           z-100 toasts                          ← above dialogs
           z-110 Select / DropdownMenu / Popover ← always on top
      */}
      <aside
        className={cn(
          'fixed left-0 top-0 z-40 h-screen transition-transform',
          sidebarOpen ? 'w-64' : 'w-16',
          'bg-card border-r'
        )}
      >
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center justify-between px-4 border-b">
            {sidebarOpen && (
              <div className="flex items-center gap-2">
                <MessageSquare className="h-6 w-6 text-primary" />
                <span className="font-bold text-lg">ChatPlatform</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>

          {/* Organization */}
          {sidebarOpen && currentOrganization && (
            <div className="px-4 py-3 border-b">
              <p className="text-xs text-muted-foreground">{t('nav.organization')}</p>
              <p className="font-medium truncate">{currentOrganization.name}</p>
            </div>
          )}

          {/* Language Switcher */}
          {sidebarOpen && (
            <div className="px-3 py-3 border-b">
              <LanguageSwitcher variant="compact" showLabel={false} />
            </div>
          )}

          {/* Navigation */}
          <ScrollArea className="flex-1 py-4">
            <nav className="space-y-1 px-2">
              {navItems.map((item) => {
                if (item.kind === 'leaf') {
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end
                      className={({ isActive }) =>
                        cn(
                          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                        )
                      }
                    >
                      <item.icon className="h-5 w-5 flex-shrink-0" />
                      {sidebarOpen && <span>{t(item.labelKey)}</span>}
                    </NavLink>
                  )
                }

                // Group
                const isOpen = !!groupState[item.id]
                const isOnSection = location.pathname.startsWith(item.pathPrefix)
                return (
                  <div key={item.id} className="space-y-1">
                    <button
                      type="button"
                      onClick={() => {
                        if (!sidebarOpen) {
                          // When the sidebar itself is collapsed, expand it
                          // AND open the group so the user can pick a child.
                          setSidebarOpen(true)
                          if (!isOpen) toggleGroup(item.id)
                        } else {
                          toggleGroup(item.id)
                        }
                      }}
                      title={!sidebarOpen ? t(item.labelKey) : undefined}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                        isOnSection
                          ? 'bg-accent text-accent-foreground font-medium'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )}
                    >
                      <item.icon className="h-5 w-5 flex-shrink-0" />
                      {sidebarOpen && (
                        <>
                          <span className="flex-1 text-left">{t(item.labelKey)}</span>
                          <ChevronRight
                            className={cn(
                              'h-4 w-4 flex-shrink-0 transition-transform',
                              isOpen && 'rotate-90',
                            )}
                          />
                        </>
                      )}
                    </button>
                    {sidebarOpen && isOpen && (
                      <div className="ml-3 space-y-1 border-l pl-3">
                        {item.children.map((child) => (
                          <NavLink
                            key={child.path}
                            to={child.path}
                            end
                            className={({ isActive }) =>
                              cn(
                                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                                isActive
                                  ? 'bg-primary text-primary-foreground'
                                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                              )
                            }
                          >
                            <child.icon className="h-4 w-4 flex-shrink-0" />
                            <span>{t(child.labelKey)}</span>
                          </NavLink>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </nav>
          </ScrollArea>

          {/* User */}
          <div className="border-t p-4">
            <div className="flex items-center gap-3">
              <Avatar className="h-9 w-9">
                <AvatarFallback>{userInitials}</AvatarFallback>
              </Avatar>
              {sidebarOpen && (
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {user?.first_name} {user?.last_name}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {user?.email}
                  </p>
                </div>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={handleLogout}
                title={t('auth.logout')}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main
        className={cn(
          'min-h-screen transition-all',
          sidebarOpen ? 'ml-64' : 'ml-16'
        )}
      >
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
