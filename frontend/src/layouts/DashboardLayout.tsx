import { useState, useMemo } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
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
} from 'lucide-react'

const coreNavKeys = [
  { path: '/dashboard', labelKey: 'nav.dashboard', icon: LayoutDashboard },
  { path: '/inbox', labelKey: 'nav.inbox', icon: Inbox },
  { path: '/alerts', labelKey: 'nav.alerts', icon: Bell },
  { path: '/knowledge', labelKey: 'nav.knowledgeBase', icon: BookOpen },
  { path: '/analytics', labelKey: 'nav.analytics', icon: BarChart3 },
]

const restaurantNavKeys = [
  { path: '/restaurant/menu', labelKey: 'nav.menu', icon: UtensilsCrossed },
  { path: '/restaurant/bookings', labelKey: 'nav.bookings', icon: CalendarDays },
]

const realEstateNavKeys = [
  { path: '/realestate/properties', labelKey: 'nav.properties', icon: Building2 },
  { path: '/realestate/leads', labelKey: 'nav.leads', icon: Users },
]

const settingsNavKey = { path: '/settings', labelKey: 'nav.settings', icon: Settings }
const channelsNavKey = { path: '/settings/channels', labelKey: 'nav.channels', icon: Phone }

export function DashboardLayout() {
  const { t } = useTranslation()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const { user, currentOrganization, logout } = useAuthStore()
  const navigate = useNavigate()

  // Build navigation items based on organization business type
  const navItems = useMemo(() => {
    const items = [...coreNavKeys]
    
    // Add vertical-specific navigation based on current organization
    const businessType = currentOrganization?.business_type
    
    if (businessType === 'restaurant') {
      items.push(...restaurantNavKeys)
    } else if (businessType === 'real_estate') {
      items.push(...realEstateNavKeys)
    } else {
      // Show both if no specific type or generic
      items.push(...restaurantNavKeys)
      items.push(...realEstateNavKeys)
    }
    
    items.push(settingsNavKey)
    items.push(channelsNavKey)
    return items
  }, [currentOrganization?.business_type])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userInitials = user
    ? `${user.first_name?.[0] || ''}${user.last_name?.[0] || ''}`.toUpperCase() || user.email[0].toUpperCase()
    : '?'

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
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
              {navItems.map((item) => (
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
              ))}
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
