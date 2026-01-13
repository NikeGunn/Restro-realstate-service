import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/auth'
import { analyticsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  MessageSquare,
  Bot,
  Users,
  AlertTriangle,
  TrendingUp,
  Globe,
  Phone,
} from 'lucide-react'
import type { AnalyticsOverview, ChannelStats } from '@/types'

export function AnalyticsPage() {
  const { t } = useTranslation()
  const { currentOrganization } = useAuthStore()
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [channelStats, setChannelStats] = useState<ChannelStats[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  // Check if current organization is on Power plan
  const isPowerPlan = currentOrganization?.is_power_plan || currentOrganization?.plan === 'power'

  useEffect(() => {
    fetchAnalytics()
  }, [currentOrganization, days])

  const fetchAnalytics = async () => {
    if (!currentOrganization) return

    try {
      const [overviewData, channelData] = await Promise.all([
        analyticsApi.overview({ organization: currentOrganization.id, days }),
        analyticsApi.byChannel({ organization: currentOrganization.id, days }),
      ])

      setOverview(overviewData)
      // Backend returns {by_channel: [...]} but we need just the array
      setChannelStats(Array.isArray(channelData) ? channelData : channelData.by_channel || [])
    } catch (error) {
      console.error('Error fetching analytics:', error)
    } finally {
      setLoading(false)
    }
  }

  if (!currentOrganization) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Please select an organization first.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  const aiHandleRate = overview
    ? Math.round((overview.messages.ai / (overview.messages.total || 1)) * 100)
    : 0

  const resolutionRate = overview
    ? Math.round((overview.handoffs.resolved / (overview.handoffs.total || 1)) * 100)
    : 0

  const channelIcons: Record<string, React.ReactNode> = {
    website: <Globe className="h-4 w-4" />,
    whatsapp: <Phone className="h-4 w-4" />,
    instagram: <MessageSquare className="h-4 w-4" />,
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">{t('analytics.title')}</h1>
          <p className="text-muted-foreground">
            {t('analytics.subtitle')}
          </p>
        </div>
      </div>

      {/* Time Range Tabs */}
      <Tabs value={String(days)} onValueChange={(v) => setDays(Number(v))}>
        <TabsList>
          <TabsTrigger value="7">{t('analytics.last7Days')}</TabsTrigger>
          <TabsTrigger value="30">{t('analytics.last30Days')}</TabsTrigger>
          <TabsTrigger value="90">{t('analytics.last90Days')}</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Key Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">{t('analytics.totalConversations')}</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.conversations.total || 0}</div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-3 w-3" />
              {t('analytics.active')}: {overview?.conversations.by_state?.ai_handling || 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">{t('analytics.totalMessages')}</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.messages.total || 0}</div>
            <p className="text-xs text-muted-foreground">
              {overview?.messages.customer || 0} {t('analytics.fromCustomers')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">{t('analytics.aiHandleRate')}</CardTitle>
            <Bot className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{aiHandleRate}%</div>
            <p className="text-xs text-muted-foreground">
              {overview?.messages.ai || 0} {t('analytics.aiResponses')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">{t('analytics.handoffResolution')}</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{resolutionRate}%</div>
            <p className="text-xs text-muted-foreground">
              {overview?.handoffs.resolved || 0} {t('analytics.of')} {overview?.handoffs.total || 0} {t('analytics.resolved')}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Stats */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Conversation States */}
        <Card>
          <CardHeader>
            <CardTitle>{t('analytics.conversationStates')}</CardTitle>
            <CardDescription>{t('analytics.conversationStatesDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(overview?.conversations.by_state || {}).map(([state, count]) => {
                const total = overview?.conversations.total || 1
                const percentage = Math.round(((count as number) / total) * 100)
                return (
                  <div key={state} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="capitalize">{state.replace('_', ' ')}</span>
                      <span className="text-muted-foreground">
                        {count} ({percentage}%)
                      </span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                )
              })}
              {Object.keys(overview?.conversations.by_state || {}).length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {t('analytics.noConversationData')}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Channel Stats */}
        <Card>
          <CardHeader>
            <CardTitle>{t('analytics.channelPerformance')}</CardTitle>
            <CardDescription>{t('analytics.channelPerformanceDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {channelStats.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {t('analytics.noChannelData')}
                </p>
              ) : (
                channelStats.map((channel) => (
                  <div
                    key={channel.channel}
                    className="flex items-center justify-between p-3 bg-muted rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {channelIcons[channel.channel]}
                      <div>
                        <p className="font-medium capitalize">{channel.channel}</p>
                        <p className="text-xs text-muted-foreground">
                          {channel.conversations} {t('analytics.conversations')}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-bold">{channel.messages}</p>
                      <p className="text-xs text-muted-foreground">{t('analytics.messages')}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        {/* Message Types */}
        <Card>
          <CardHeader>
            <CardTitle>{t('analytics.messageDistribution')}</CardTitle>
            <CardDescription>{t('analytics.messageDistributionDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-blue-500" />
                  <span>{t('analytics.customer')}</span>
                </div>
                <span className="font-bold">{overview?.messages.customer || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-green-500" />
                  <span>{t('analytics.ai')}</span>
                </div>
                <span className="font-bold">{overview?.messages.ai || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-purple-500" />
                  <span>{t('analytics.humanAgent')}</span>
                </div>
                <span className="font-bold">{overview?.messages.human || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Handoffs */}
        <Card>
          <CardHeader>
            <CardTitle>{t('analytics.handoffSummary')}</CardTitle>
            <CardDescription>{t('analytics.handoffSummaryDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span>{t('analytics.totalHandoffs')}</span>
                <span className="font-bold">{overview?.handoffs.total || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>{t('analytics.resolved')}</span>
                <span className="font-bold text-green-600">
                  {overview?.handoffs.resolved || 0}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>{t('analytics.pending')}</span>
                <span className="font-bold text-yellow-600">
                  {overview?.handoffs.pending || 0}
                </span>
              </div>
              {(overview?.handoffs.total ?? 0) > 0 && (
                <div className="pt-2 border-t">
                  <p className="text-sm text-muted-foreground">
                    {resolutionRate}% {t('analytics.handoffsResolved')}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Business-Specific Metrics (Restaurant) */}
      {currentOrganization?.business_type === 'restaurant' && overview?.restaurant && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>🍽️ Restaurant Metrics</CardTitle>
            <CardDescription>Booking and guest analytics for your restaurant</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Total Bookings</p>
                <p className="text-2xl font-bold">{overview.restaurant.bookings?.total || 0}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Confirmed</p>
                <p className="text-2xl font-bold text-green-600">
                  {overview.restaurant.bookings?.confirmed || 0}
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Completed</p>
                <p className="text-2xl font-bold text-blue-600">
                  {overview.restaurant.bookings?.completed || 0}
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Total Guests</p>
                <p className="text-2xl font-bold">{overview.restaurant.bookings?.total_guests || 0}</p>
              </div>
            </div>
            {(overview.restaurant.bookings?.cancelled ?? 0) > 0 && (
              <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
                <p className="text-sm text-yellow-800 dark:text-yellow-200">
                  ⚠️ {overview.restaurant.bookings?.cancelled ?? 0} cancelled bookings,{' '}
                  {overview.restaurant.bookings?.no_shows ?? 0} no-shows
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Business-Specific Metrics (Real Estate) */}
      {currentOrganization?.business_type === 'real_estate' && overview?.real_estate && (
        <div className="grid gap-4 md:grid-cols-2 mt-6">
          <Card>
            <CardHeader>
              <CardTitle>🏠 Lead Analytics</CardTitle>
              <CardDescription>Property leads and conversion metrics</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span>Total Leads</span>
                  <span className="font-bold">{overview.real_estate.leads?.total || 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Avg Lead Score</span>
                  <span className="font-bold">{overview.real_estate.leads?.avg_score || 0}/100</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Conversion Rate</span>
                  <span className="font-bold text-green-600">
                    {overview.real_estate.leads?.conversion_rate || 0}%
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>📅 Appointments</CardTitle>
              <CardDescription>Property viewing appointments</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span>Total Appointments</span>
                  <span className="font-bold">{overview.real_estate.appointments?.total || 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Active Listings</span>
                  <span className="font-bold">{overview.real_estate.properties?.active_listings || 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Sold This Period</span>
                  <span className="font-bold text-green-600">
                    {overview.real_estate.properties?.sold_in_period || 0}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Power Plan Notice for Basic Users */}
      {!isPowerPlan && (
        <Card className="mt-6 border-blue-200 bg-blue-50 dark:bg-blue-900/20">
          <CardContent className="pt-6">
            <div className="flex items-start gap-4">
              <TrendingUp className="h-6 w-6 text-blue-600 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-blue-900 dark:text-blue-100">
                  Upgrade to Power Plan
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                  Get access to advanced analytics features: aggregated multi-location analytics,
                  custom dashboards, escalation rules, and detailed performance reports.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
