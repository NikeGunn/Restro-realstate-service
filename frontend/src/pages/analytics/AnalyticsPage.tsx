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
  TrendingDown,
  Globe,
  Phone,
  Clock,
  Zap,
  MapPin,
  Calendar,
  BarChart3,
  Activity,
  Crown,
} from 'lucide-react'
import type { AnalyticsOverview, ChannelStats, DailyTrendResponse, LocationAnalyticsResponse } from '@/types'

export function AnalyticsPage() {
  const { t } = useTranslation()
  const { currentOrganization } = useAuthStore()
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [channelStats, setChannelStats] = useState<ChannelStats[]>([])
  const [dailyTrends, setDailyTrends] = useState<DailyTrendResponse | null>(null)
  const [locationStats, setLocationStats] = useState<LocationAnalyticsResponse | null>(null)
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
      const promises: Promise<unknown>[] = [
        analyticsApi.overview({ organization: currentOrganization.id, days }),
        analyticsApi.byChannel({ organization: currentOrganization.id, days }),
      ]

      // Fetch Power Plan exclusive data
      if (isPowerPlan) {
        promises.push(
          analyticsApi.daily({ organization: currentOrganization.id, days }),
          analyticsApi.byLocation({ organization: currentOrganization.id, days })
        )
      }

      const results = await Promise.all(promises)

      setOverview(results[0] as AnalyticsOverview)
      const channelData = results[1] as ChannelStats[] | { by_channel: ChannelStats[] }
      setChannelStats(Array.isArray(channelData) ? channelData : channelData.by_channel || [])

      if (isPowerPlan && results.length > 2) {
        setDailyTrends(results[2] as DailyTrendResponse)
        setLocationStats(results[3] as LocationAnalyticsResponse)
      }
    } catch (error) {
      console.error('Error fetching analytics:', error)
    } finally {
      setLoading(false)
    }
  }

  // Helper function to format seconds as human readable time
  const formatTime = (seconds: number | null): string => {
    if (seconds === null) return 'N/A'
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  // Helper function to format hour (0-23) as readable time
  const formatHour = (hour: number): string => {
    const suffix = hour >= 12 ? 'PM' : 'AM'
    const displayHour = hour % 12 || 12
    return `${displayHour}${suffix}`
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
            {((overview.restaurant.bookings?.cancelled ?? 0) > 0 || (overview.restaurant.bookings?.no_shows ?? 0) > 0) && (
              <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-900/30 rounded-lg border border-amber-200 dark:border-amber-700">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
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
        <Card className="mt-6 border-blue-300 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950 dark:to-indigo-950 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 rounded-lg bg-blue-100 dark:bg-blue-900 p-2">
                <TrendingUp className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="flex-1">
                <h3 className="font-bold text-lg text-gray-900 dark:text-gray-100">
                  Upgrade to Power Plan
                </h3>
                <p className="text-sm text-gray-700 dark:text-gray-300 mt-1 leading-relaxed">
                  Get access to advanced analytics features: aggregated multi-location analytics,
                  custom dashboards, escalation rules, and detailed performance reports.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ================================================= */}
      {/* POWER PLAN EXCLUSIVE ANALYTICS SECTION */}
      {/* ================================================= */}
      {isPowerPlan && (
        <>
          {/* Power Plan Header */}
          <div className="mt-8 mb-4">
            <div className="flex items-center gap-2 mb-2">
              <Crown className="h-5 w-5 text-amber-500" />
              <h2 className="text-xl font-bold text-amber-600 dark:text-amber-400">
                Power Plan Analytics
              </h2>
            </div>
            <p className="text-sm text-muted-foreground">
              Advanced insights and detailed performance metrics exclusive to Power Plan subscribers
            </p>
          </div>

          {/* Response Time & AI Efficiency Metrics */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Avg Response Time</CardTitle>
                <Clock className="h-4 w-4 text-amber-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-amber-600">
                  {formatTime(overview?.power_analytics?.response_time?.avg_seconds ?? null)}
                </div>
                <p className="text-xs text-muted-foreground">
                  Based on {overview?.power_analytics?.response_time?.sample_size || 0} messages
                </p>
              </CardContent>
            </Card>

            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Fastest Response</CardTitle>
                <Zap className="h-4 w-4 text-green-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">
                  {formatTime(overview?.power_analytics?.response_time?.min_seconds ?? null)}
                </div>
                <p className="text-xs text-muted-foreground">
                  Best response time achieved
                </p>
              </CardContent>
            </Card>

            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">AI Resolution Rate</CardTitle>
                <Bot className="h-4 w-4 text-blue-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-blue-600">
                  {overview?.power_analytics?.ai_efficiency?.ai_resolution_rate || 0}%
                </div>
                <p className="text-xs text-muted-foreground">
                  {overview?.power_analytics?.ai_efficiency?.ai_only_resolved || 0} resolved without human
                </p>
              </CardContent>
            </Card>

            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Conversation Trend</CardTitle>
                {dailyTrends?.trend?.direction === 'up' ? (
                  <TrendingUp className="h-4 w-4 text-green-500" />
                ) : dailyTrends?.trend?.direction === 'down' ? (
                  <TrendingDown className="h-4 w-4 text-red-500" />
                ) : (
                  <Activity className="h-4 w-4 text-gray-500" />
                )}
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${
                  dailyTrends?.trend?.direction === 'up' ? 'text-green-600' :
                  dailyTrends?.trend?.direction === 'down' ? 'text-red-600' : 'text-gray-600'
                }`}>
                  {dailyTrends?.trend?.direction === 'up' ? '+' : dailyTrends?.trend?.direction === 'down' ? '-' : ''}
                  {dailyTrends?.trend?.percent || 0}%
                </div>
                <p className="text-xs text-muted-foreground">
                  vs. first half of period
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Daily Trends Chart */}
          <div className="grid gap-4 md:grid-cols-2 mt-4">
            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-amber-500" />
                  <CardTitle>Daily Conversation Trends</CardTitle>
                </div>
                <CardDescription>Daily breakdown of conversations and resolutions</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {dailyTrends?.daily?.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No daily data available
                    </p>
                  ) : (
                    dailyTrends?.daily?.slice(-14).map((day) => {
                      const maxConv = Math.max(...(dailyTrends.daily?.map(d => d.conversations) || [1]))
                      const width = (day.conversations / maxConv) * 100
                      return (
                        <div key={day.date} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span>{new Date(day.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                            <span className="text-muted-foreground">
                              {day.conversations} conv / {day.messages} msg
                            </span>
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-amber-400 to-orange-500 rounded-full"
                              style={{ width: `${width}%` }}
                            />
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Peak Hours */}
            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-amber-500" />
                  <CardTitle>Peak Activity Hours</CardTitle>
                </div>
                <CardDescription>When your customers are most active</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {/* Top 3 Peak Hours */}
                  {overview?.power_analytics?.peak_hours?.peak_hours?.length ? (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {overview.power_analytics.peak_hours.peak_hours.map((hour, idx) => (
                        <div
                          key={hour}
                          className={`px-3 py-1 rounded-full text-sm font-medium ${
                            idx === 0 ? 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' :
                            idx === 1 ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' :
                            'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                          }`}
                        >
                          #{idx + 1} {formatHour(hour)}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {/* Hourly Distribution Bar Chart */}
                  <div className="grid grid-cols-12 gap-1 h-24">
                    {Array.from({ length: 24 }, (_, hour) => {
                      const hourData = overview?.power_analytics?.peak_hours?.hourly_distribution?.find(
                        h => h.hour === hour
                      )
                      const count = hourData?.count || 0
                      const maxCount = Math.max(
                        ...(overview?.power_analytics?.peak_hours?.hourly_distribution?.map(h => h.count) || [1])
                      )
                      const height = maxCount > 0 ? (count / maxCount) * 100 : 0
                      const isPeak = overview?.power_analytics?.peak_hours?.peak_hours?.includes(hour)

                      return hour % 2 === 0 ? (
                        <div key={hour} className="flex flex-col items-center justify-end h-full">
                          <div
                            className={`w-full rounded-t ${isPeak ? 'bg-amber-500' : 'bg-gray-300 dark:bg-gray-600'}`}
                            style={{ height: `${height}%`, minHeight: count > 0 ? '4px' : '0' }}
                          />
                          <span className="text-[10px] text-muted-foreground mt-1">{hour}</span>
                        </div>
                      ) : null
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground text-center mt-2">Hour of day (24h)</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Day of Week & Location Analytics */}
          <div className="grid gap-4 md:grid-cols-2 mt-4">
            {/* Day of Week Distribution */}
            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-amber-500" />
                  <CardTitle>Weekly Activity Pattern</CardTitle>
                </div>
                <CardDescription>Conversation distribution by day of week</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {overview?.power_analytics?.day_of_week?.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No weekly data available
                    </p>
                  ) : (
                    overview?.power_analytics?.day_of_week?.map((day) => {
                      const maxCount = Math.max(
                        ...(overview?.power_analytics?.day_of_week?.map(d => d.count) || [1])
                      )
                      const width = (day.count / maxCount) * 100
                      return (
                        <div key={day.day_of_week} className="space-y-1">
                          <div className="flex justify-between text-sm">
                            <span className="font-medium">{day.day_name}</span>
                            <span className="text-muted-foreground">{day.count} conversations</span>
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-purple-400 to-pink-500 rounded-full"
                              style={{ width: `${width}%` }}
                            />
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Location Analytics */}
            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <MapPin className="h-5 w-5 text-amber-500" />
                  <CardTitle>Location Performance</CardTitle>
                </div>
                <CardDescription>Analytics breakdown by location</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {locationStats?.by_location?.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No location data available
                    </p>
                  ) : (
                    locationStats?.by_location?.map((loc) => (
                      <div
                        key={loc.location_id || 'primary'}
                        className="p-3 bg-muted rounded-lg"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium">{loc.location_name}</span>
                          <span className={`text-xs px-2 py-1 rounded-full ${
                            loc.resolution_rate >= 70 
                              ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                              : loc.resolution_rate >= 40
                              ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                              : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                          }`}>
                            {loc.resolution_rate}% resolved
                          </span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                          <div>
                            <span className="font-semibold text-foreground">{loc.conversations}</span> conv
                          </div>
                          <div>
                            <span className="font-semibold text-foreground">{loc.messages}</span> msg
                          </div>
                          <div>
                            <span className="font-semibold text-foreground">{loc.handoffs}</span> handoffs
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Channel Performance Comparison */}
          <Card className="mt-4 border-amber-200 dark:border-amber-800">
            <CardHeader>
              <div className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-amber-500" />
                <CardTitle>Channel Performance Comparison</CardTitle>
              </div>
              <CardDescription>Compare resolution rates across different channels</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                {overview?.power_analytics?.channel_performance?.map((ch) => (
                  <div
                    key={ch.channel}
                    className="p-4 bg-muted rounded-lg text-center"
                  >
                    <div className="flex items-center justify-center gap-2 mb-2">
                      {channelIcons[ch.channel] || <Globe className="h-5 w-5" />}
                      <span className="font-medium capitalize">{ch.channel}</span>
                    </div>
                    <div className="text-3xl font-bold text-amber-600 mb-1">
                      {ch.resolution_rate}%
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {ch.resolved} of {ch.total} resolved
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
