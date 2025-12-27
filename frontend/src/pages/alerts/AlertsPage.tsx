import { useEffect, useState } from 'react'
import { useAuthStore } from '@/store/auth'
import { alertsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import {
  AlertTriangle,
  Bell,
  CheckCircle,
  Clock,
  MessageSquare,
  ExternalLink,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Link } from 'react-router-dom'
import type { HandoffAlert } from '@/types'

const priorityColors: Record<string, 'default' | 'secondary' | 'destructive' | 'warning'> = {
  low: 'secondary',
  medium: 'default',
  high: 'warning',
  urgent: 'destructive',
}

const typeIcons: Record<string, React.ReactNode> = {
  low_confidence: <AlertTriangle className="h-4 w-4" />,
  explicit_request: <MessageSquare className="h-4 w-4" />,
  complex_query: <AlertTriangle className="h-4 w-4" />,
  negative_sentiment: <AlertTriangle className="h-4 w-4" />,
  vip_customer: <Bell className="h-4 w-4" />,
}

export function AlertsPage() {
  const { currentOrganization } = useAuthStore()
  const [alerts, setAlerts] = useState<HandoffAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const { toast } = useToast()

  useEffect(() => {
    fetchAlerts()
  }, [currentOrganization, statusFilter])

  const fetchAlerts = async () => {
    if (!currentOrganization) return

    try {
      const params: Record<string, string> = {
        organization: currentOrganization.id,
      }
      if (statusFilter !== 'all') {
        params.status = statusFilter
      }

      const response = await alertsApi.list(params)
      setAlerts(response.results || [])
    } catch (error) {
      console.error('Error fetching alerts:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleAcknowledge = async (alertId: string) => {
    try {
      await alertsApi.acknowledge(alertId)
      await fetchAlerts()
      toast({
        title: 'Alert acknowledged',
        description: 'You are now handling this conversation.',
      })
    } catch (error) {
      console.error('Error acknowledging alert:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to acknowledge alert.',
      })
    }
  }

  const handleResolve = async (alertId: string) => {
    try {
      await alertsApi.resolve(alertId)
      await fetchAlerts()
      toast({
        title: 'Alert resolved',
        description: 'The handoff has been completed.',
      })
    } catch (error) {
      console.error('Error resolving alert:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to resolve alert.',
      })
    }
  }

  if (!currentOrganization) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Please select an organization first.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Alerts</h1>
        <p className="text-muted-foreground">
          Human handoff requests and notifications.
        </p>
      </div>

      <Tabs value={statusFilter} onValueChange={setStatusFilter}>
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="acknowledged">Acknowledged</TabsTrigger>
          <TabsTrigger value="resolved">Resolved</TabsTrigger>
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>

        <TabsContent value={statusFilter} className="mt-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : alerts.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Bell className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium">No alerts</h3>
                <p className="text-muted-foreground text-sm">
                  {statusFilter === 'pending'
                    ? 'All caught up! No pending handoff requests.'
                    : 'No alerts match this filter.'}
                </p>
              </CardContent>
            </Card>
          ) : (
            <ScrollArea className="h-[calc(100vh-300px)]">
              <div className="space-y-3">
                {alerts.map((alert) => (
                  <Card key={alert.id}>
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-4">
                          <div
                            className={`p-2 rounded-full ${alert.priority === 'urgent'
                                ? 'bg-red-100 text-red-600'
                                : alert.priority === 'high'
                                  ? 'bg-orange-100 text-orange-600'
                                  : 'bg-gray-100 text-gray-600'
                              }`}
                          >
                            {typeIcons[alert.type] || <AlertTriangle className="h-4 w-4" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="font-medium">
                                {alert.conversation_customer_name || 'Anonymous Customer'}
                              </h3>
                              <Badge variant={priorityColors[alert.priority]}>
                                {alert.priority}
                              </Badge>
                              <Badge variant="outline">
                                {alert.type.replace('_', ' ')}
                              </Badge>
                            </div>
                            <p className="text-sm text-muted-foreground mt-1">
                              {alert.reason}
                            </p>
                            {alert.trigger_message && (
                              <div className="mt-2 p-2 bg-muted rounded text-sm">
                                "{alert.trigger_message}"
                              </div>
                            )}
                            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {formatDistanceToNow(new Date(alert.created_at), {
                                  addSuffix: true,
                                })}
                              </span>
                              {alert.acknowledged_by_name && (
                                <span>Acknowledged by {alert.acknowledged_by_name}</span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Link to={`/inbox/${alert.conversation}`}>
                            <Button variant="outline" size="sm">
                              <ExternalLink className="h-4 w-4 mr-2" />
                              View Chat
                            </Button>
                          </Link>
                          {alert.status === 'pending' && (
                            <Button
                              size="sm"
                              onClick={() => handleAcknowledge(alert.id)}
                            >
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Acknowledge
                            </Button>
                          )}
                          {alert.status === 'acknowledged' && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleResolve(alert.id)}
                            >
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Resolve
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </ScrollArea>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
