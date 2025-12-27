import { useEffect, useState } from 'react'
import { useAuthStore } from '@/store/auth'
import { analyticsApi, alertsApi, organizationsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  MessageSquare,
  Users,
  Bot,
  AlertTriangle,
  Plus,
  Copy,
} from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import type { AnalyticsOverview, Organization } from '@/types'

export function DashboardPage() {
  const { user, currentOrganization, setCurrentOrganization } = useAuthStore()
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null)
  const [alertStats, setAlertStats] = useState({ pending: 0, total: 0 })
  const [loading, setLoading] = useState(true)
  const [showCreateOrg, setShowCreateOrg] = useState(false)
  const [newOrgName, setNewOrgName] = useState('')
  const [newOrgType, setNewOrgType] = useState<'restaurant' | 'real_estate'>('restaurant')
  const { toast } = useToast()

  useEffect(() => {
    fetchData()
  }, [currentOrganization])

  const fetchData = async () => {
    if (!currentOrganization) {
      setLoading(false)
      return
    }

    try {
      const [analyticsData, alertsData] = await Promise.all([
        analyticsApi.overview({ organization: currentOrganization.id, days: 30 }),
        alertsApi.stats({ organization: currentOrganization.id }),
      ])
      setAnalytics(analyticsData)
      setAlertStats(alertsData)
    } catch (error) {
      console.error('Error fetching dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateOrganization = async () => {
    if (!newOrgName.trim()) return

    try {
      const org = await organizationsApi.create({
        name: newOrgName,
        business_type: newOrgType,
      })

      // Fetch full org details
      const fullOrg = await organizationsApi.get(org.id)
      setCurrentOrganization(fullOrg)
      setShowCreateOrg(false)
      setNewOrgName('')

      toast({
        title: 'Organization created!',
        description: 'Your new organization is ready.',
      })

      fetchData()
    } catch (error) {
      console.error('Error creating organization:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to create organization.',
      })
    }
  }

  const copyWidgetCode = () => {
    if (!currentOrganization) return

    const code = `<script src="http://localhost:8000/static/widget.js" data-widget-key="${currentOrganization.widget_key}"></script>`
    navigator.clipboard.writeText(code)

    toast({
      title: 'Copied!',
      description: 'Widget code copied to clipboard.',
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!currentOrganization) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Welcome, {user?.first_name}!</h1>
          <p className="text-muted-foreground">Let's set up your first organization.</p>
        </div>

        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Create Organization</CardTitle>
            <CardDescription>
              Set up your business to start using the AI chatbot.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="orgName">Organization Name</Label>
              <Input
                id="orgName"
                placeholder="My Business"
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Business Type</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={newOrgType === 'restaurant' ? 'default' : 'outline'}
                  onClick={() => setNewOrgType('restaurant')}
                >
                  Restaurant
                </Button>
                <Button
                  type="button"
                  variant={newOrgType === 'real_estate' ? 'default' : 'outline'}
                  onClick={() => setNewOrgType('real_estate')}
                >
                  Real Estate
                </Button>
              </div>
            </div>
            <Button onClick={handleCreateOrganization} className="w-full">
              <Plus className="h-4 w-4 mr-2" />
              Create Organization
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Overview of your chat platform for the last 30 days.
          </p>
        </div>
        <Badge variant="outline" className="text-sm">
          {currentOrganization.business_type === 'restaurant' ? '🍽️ Restaurant' : '🏠 Real Estate'}
        </Badge>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Conversations</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{analytics?.conversations.total || 0}</div>
            <p className="text-xs text-muted-foreground">Last 30 days</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{analytics?.messages.total || 0}</div>
            <p className="text-xs text-muted-foreground">
              {analytics?.messages.customer || 0} from customers
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">AI Handled</CardTitle>
            <Bot className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{analytics?.messages.ai || 0}</div>
            <p className="text-xs text-muted-foreground">
              {analytics?.messages.human || 0} by humans
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Pending Alerts</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{alertStats.pending}</div>
            <p className="text-xs text-muted-foreground">
              {alertStats.total} total handoffs
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Widget Installation */}
      <Card>
        <CardHeader>
          <CardTitle>Install Chat Widget</CardTitle>
          <CardDescription>
            Add this code to your website to enable the chat widget.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="bg-muted p-4 rounded-lg font-mono text-sm overflow-x-auto">
            {`<script src="http://localhost:8000/static/widget.js" data-widget-key="${currentOrganization.widget_key}"></script>`}
          </div>
          <Button onClick={copyWidgetCode} className="mt-4" variant="outline">
            <Copy className="h-4 w-4 mr-2" />
            Copy Code
          </Button>
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Conversation States</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(analytics?.conversations.by_state || {}).map(([state, count]) => (
                <div key={state} className="flex justify-between items-center">
                  <span className="text-sm capitalize">{state.replace('_', ' ')}</span>
                  <Badge variant="secondary">{count as number}</Badge>
                </div>
              ))}
              {Object.keys(analytics?.conversations.by_state || {}).length === 0 && (
                <p className="text-sm text-muted-foreground">No conversations yet</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Handoff Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm">Total Handoffs</span>
                <Badge variant="secondary">{analytics?.handoffs.total || 0}</Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm">Resolved</span>
                <Badge variant="success">{analytics?.handoffs.resolved || 0}</Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm">Pending</span>
                <Badge variant="warning">{analytics?.handoffs.pending || 0}</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
