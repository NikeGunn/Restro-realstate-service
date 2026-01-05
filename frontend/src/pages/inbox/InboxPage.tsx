import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { conversationsApi } from '@/services/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Search,
  MessageSquare,
  Globe,
  Phone,
  Clock,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import type { Conversation } from '@/types'

const stateColors: Record<string, 'default' | 'secondary' | 'destructive' | 'success' | 'warning'> = {
  new: 'default',
  ai_handling: 'secondary',
  awaiting_user: 'warning',
  human_handoff: 'destructive',
  resolved: 'success',
  archived: 'secondary',
}

const channelIcons: Record<string, React.ReactNode> = {
  website: <Globe className="h-4 w-4" />,
  whatsapp: <Phone className="h-4 w-4" />,
  instagram: <MessageSquare className="h-4 w-4" />,
}

export function InboxPage() {
  const { currentOrganization } = useAuthStore()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState<string>('all')

  useEffect(() => {
    fetchConversations()
  }, [currentOrganization, stateFilter, search])

  const fetchConversations = async () => {
    if (!currentOrganization) return

    try {
      const params: Record<string, string> = {
        organization: currentOrganization.id,
      }
      if (stateFilter !== 'all') {
        params.state = stateFilter
      }
      if (search) {
        params.search = search
      }

      const response = await conversationsApi.list(params)
      // API already returns the array, not paginated object
      setConversations(Array.isArray(response) ? response : (response.results || []))
    } catch (error) {
      console.error('Error fetching conversations:', error)
    } finally {
      setLoading(false)
    }
  }

  const getCustomerInitials = (conv: Conversation) => {
    if (conv.customer_name) {
      return conv.customer_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    }
    return '?'
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
        <h1 className="text-3xl font-bold">Inbox</h1>
        <p className="text-muted-foreground">Manage all your customer conversations.</p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 items-center">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search conversations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <Tabs value={stateFilter} onValueChange={setStateFilter}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="new">New</TabsTrigger>
          <TabsTrigger value="ai_handling">AI Handling</TabsTrigger>
          <TabsTrigger value="human_handoff">Human Handoff</TabsTrigger>
          <TabsTrigger value="resolved">Resolved</TabsTrigger>
        </TabsList>

        <TabsContent value={stateFilter} className="mt-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : conversations.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <MessageSquare className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium">No conversations</h3>
                <p className="text-muted-foreground text-sm">
                  Conversations will appear here when customers start chatting.
                </p>
              </CardContent>
            </Card>
          ) : (
            <ScrollArea className="h-[calc(100vh-300px)]">
              <div className="space-y-2">
                {conversations.map((conv) => (
                  <Link key={conv.id} to={`/inbox/${conv.id}`}>
                    <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                      <CardContent className="p-4">
                        <div className="flex items-start gap-4">
                          <Avatar>
                            <AvatarFallback>{getCustomerInitials(conv)}</AvatarFallback>
                          </Avatar>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="font-medium">
                                  {conv.customer_name || 'Anonymous'}
                                </span>
                                {channelIcons[conv.channel]}
                                {conv.unread_count > 0 && (
                                  <Badge variant="default">{conv.unread_count}</Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Clock className="h-3 w-3" />
                                {conv.last_message_at
                                  ? formatDistanceToNow(new Date(conv.last_message_at), { addSuffix: true })
                                  : 'No messages'}
                              </div>
                            </div>
                            <p className="text-sm text-muted-foreground truncate mt-1">
                              {conv.last_message?.content || 'No messages yet'}
                            </p>
                            <div className="flex items-center gap-2 mt-2">
                              <Badge variant={stateColors[conv.state]}>
                                {conv.state.replace('_', ' ')}
                              </Badge>
                              {conv.location_name && (
                                <Badge variant="outline">{conv.location_name}</Badge>
                              )}
                              {conv.is_locked && (
                                <Badge variant="warning">Locked</Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </ScrollArea>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
