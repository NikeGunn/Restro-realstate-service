import { useEffect, useState } from 'react'
import { useAuthStore } from '@/store/auth'
import { analyticsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  const { currentOrganization } = useAuthStore()
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [channelStats, setChannelStats] = useState<ChannelStats[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

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
          <h1 className="text-3xl font-bold">Analytics</h1>
          <p className="text-muted-foreground">
            Track your chatbot performance and customer engagement.
          </p>
        </div>
      </div>

      {/* Time Range Tabs */}
      <Tabs value={String(days)} onValueChange={(v) => setDays(Number(v))}>
        <TabsList>
          <TabsTrigger value="7">Last 7 Days</TabsTrigger>
          <TabsTrigger value="30">Last 30 Days</TabsTrigger>
          <TabsTrigger value="90">Last 90 Days</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Key Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Conversations</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.conversations.total || 0}</div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-3 w-3" />
              Active: {overview?.conversations.by_state?.ai_handling || 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.messages.total || 0}</div>
            <p className="text-xs text-muted-foreground">
              {overview?.messages.customer || 0} from customers
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">AI Handle Rate</CardTitle>
            <Bot className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{aiHandleRate}%</div>
            <p className="text-xs text-muted-foreground">
              {overview?.messages.ai || 0} AI responses
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Handoff Resolution</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{resolutionRate}%</div>
            <p className="text-xs text-muted-foreground">
              {overview?.handoffs.resolved || 0} of {overview?.handoffs.total || 0} resolved
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Stats */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Conversation States */}
        <Card>
          <CardHeader>
            <CardTitle>Conversation States</CardTitle>
            <CardDescription>Current distribution of conversations</CardDescription>
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
                  No conversation data yet
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Channel Stats */}
        <Card>
          <CardHeader>
            <CardTitle>Channel Performance</CardTitle>
            <CardDescription>Messages by channel</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {channelStats.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No channel data yet
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
                          {channel.conversations} conversations
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-bold">{channel.messages}</p>
                      <p className="text-xs text-muted-foreground">messages</p>
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
            <CardTitle>Message Distribution</CardTitle>
            <CardDescription>By sender type</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-blue-500" />
                  <span>Customer</span>
                </div>
                <span className="font-bold">{overview?.messages.customer || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-green-500" />
                  <span>AI</span>
                </div>
                <span className="font-bold">{overview?.messages.ai || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-purple-500" />
                  <span>Human Agent</span>
                </div>
                <span className="font-bold">{overview?.messages.human || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Handoffs */}
        <Card>
          <CardHeader>
            <CardTitle>Handoff Summary</CardTitle>
            <CardDescription>Human escalation metrics</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span>Total Handoffs</span>
                <span className="font-bold">{overview?.handoffs.total || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Resolved</span>
                <span className="font-bold text-green-600">
                  {overview?.handoffs.resolved || 0}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Pending</span>
                <span className="font-bold text-yellow-600">
                  {overview?.handoffs.pending || 0}
                </span>
              </div>
              {overview?.handoffs.total > 0 && (
                <div className="pt-2 border-t">
                  <p className="text-sm text-muted-foreground">
                    {resolutionRate}% of handoffs have been resolved
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
