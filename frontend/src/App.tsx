import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { Toaster } from '@/components/ui/toaster'
import { useAuthStore } from '@/store/auth'
import { authApi, organizationsApi } from '@/services/api'
import { AuthLayout } from '@/layouts/AuthLayout'
import { DashboardLayout } from '@/layouts/DashboardLayout'
import { LoginPage } from '@/pages/auth/LoginPage'
import { RegisterPage } from '@/pages/auth/RegisterPage'
import { OrganizationSetupPage } from '@/pages/auth/OrganizationSetupPage'
import { DashboardPage } from '@/pages/dashboard/DashboardPage'
import { InboxPage } from '@/pages/inbox/InboxPage'
import { ConversationPage } from '@/pages/inbox/ConversationPage'
import { AlertsPage } from '@/pages/alerts/AlertsPage'
import { KnowledgePage } from '@/pages/knowledge/KnowledgePage'
import { SettingsPage } from '@/pages/settings/SettingsPage'
import { ChannelsPage } from '@/pages/settings/ChannelsPage'
import { AnalyticsPage } from '@/pages/analytics/AnalyticsPage'

// Restaurant pages
import { MenuPage } from '@/pages/restaurant/MenuPage'
import { BookingsPage } from '@/pages/restaurant/BookingsPage'

// Real Estate pages
import { PropertiesPage } from '@/pages/realestate/PropertiesPage'
import { LeadsPage } from '@/pages/realestate/LeadsPage'

// Public pages
import { LandingPage } from '@/pages/LandingPage'
import { PrivacyPolicy } from '@/pages/PrivacyPolicy'
import { TermsOfService } from '@/pages/TermsOfService'

// Reconciles persisted token state with the API on every cold load.
// Without this, a user with valid tokens but a missing/stale currentOrganization
// in localStorage would be bounced to /setup-organization instead of /dashboard.
function AppInitializer() {
  const { tokens, currentOrganization, setUser, setCurrentOrganization, setInitialized, logout } = useAuthStore()

  useEffect(() => {
    if (!tokens?.access) {
      setInitialized(true)
      return
    }

    // Tokens exist — verify them and hydrate org if missing
    const hydrate = async () => {
      try {
        const [user, organizations] = await Promise.all([
          authApi.getCurrentUser(),
          organizationsApi.list(),
        ])
        setUser(user)
        if (organizations.length > 0) {
          // Only update if store is stale/empty to avoid resetting a manually-chosen org
          if (!currentOrganization) {
            setCurrentOrganization(organizations[0])
          }
        } else {
          setCurrentOrganization(null)
        }
      } catch {
        // Tokens are invalid/expired and refresh failed → force logout
        logout()
      } finally {
        setInitialized(true)
      }
    }

    hydrate()
    // Run once on mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { tokens, isInitialized } = useAuthStore()

  if (!isInitialized) return null

  if (!tokens?.access) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function OrganizationRequiredRoute({ children }: { children: React.ReactNode }) {
  const { tokens, currentOrganization, isInitialized } = useAuthStore()

  // Wait for AppInitializer to finish before making redirect decisions
  if (!isInitialized) return null

  if (!tokens?.access) {
    return <Navigate to="/login" replace />
  }

  if (!currentOrganization) {
    return <Navigate to="/setup-organization" replace />
  }

  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { tokens, currentOrganization, isInitialized } = useAuthStore()

  // Wait for AppInitializer to finish so we know the real org state
  if (!isInitialized) return null

  if (tokens?.access) {
    // Authenticated: go to dashboard if org exists, else setup
    return <Navigate to={currentOrganization ? '/dashboard' : '/setup-organization'} replace />
  }

  return <>{children}</>
}

function App() {
  return (
    <BrowserRouter>
      <AppInitializer />
      <Routes>
        {/* Landing Page - Public */}
        <Route path="/" element={<LandingPage />} />

        {/* Public Pages (no auth required) */}
        <Route path="/privacy" element={<PrivacyPolicy />} />
        <Route path="/terms" element={<TermsOfService />} />

        {/* Auth Routes */}
        <Route element={
          <PublicRoute>
            <AuthLayout />
          </PublicRoute>
        }>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        {/* Organization Setup - requires auth but no org */}
        <Route
          path="/setup-organization"
          element={
            <ProtectedRoute>
              <OrganizationSetupPage />
            </ProtectedRoute>
          }
        />

        {/* Dashboard Routes - requires both auth and organization */}
        <Route
          element={
            <OrganizationRequiredRoute>
              <DashboardLayout />
            </OrganizationRequiredRoute>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/inbox/:conversationId" element={<ConversationPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/channels" element={<ChannelsPage />} />

          {/* Restaurant Routes */}
          <Route path="/restaurant/menu" element={<MenuPage />} />
          <Route path="/restaurant/bookings" element={<BookingsPage />} />

          {/* Real Estate Routes */}
          <Route path="/realestate/properties" element={<PropertiesPage />} />
          <Route path="/realestate/leads" element={<LeadsPage />} />
        </Route>
      </Routes>
      <Toaster />
    </BrowserRouter>
  )
}

export default App
