import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from '@/components/ui/toaster'
import { useAuthStore } from '@/store/auth'
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
import { PrivacyPolicy } from '@/pages/PrivacyPolicy'
import { TermsOfService } from '@/pages/TermsOfService'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { tokens } = useAuthStore()

  if (!tokens?.access) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function OrganizationRequiredRoute({ children }: { children: React.ReactNode }) {
  const { tokens, currentOrganization } = useAuthStore()

  if (!tokens?.access) {
    return <Navigate to="/login" replace />
  }

  // If no organization is set, redirect to organization setup
  if (!currentOrganization) {
    return <Navigate to="/setup-organization" replace />
  }

  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { tokens } = useAuthStore()

  if (tokens?.access) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
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
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
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
