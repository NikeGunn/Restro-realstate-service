import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { conversationsApi } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { useToast } from '@/hooks/use-toast'
import {
  ArrowLeft,
  Send,
  Lock,
  Unlock,
  CheckCircle,
  Bot,
  User,
  Users,
} from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'
import type { Conversation, Message } from '@/types'
import { cn } from '@/lib/utils'

const senderIcons: Record<string, React.ReactNode> = {
  customer: <User className="h-4 w-4" />,
  ai: <Bot className="h-4 w-4" />,
  human: <Users className="h-4 w-4" />,
  system: <Bot className="h-4 w-4" />,
}

export function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const { toast } = useToast()

  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchConversation()

    // Poll for new messages
    const interval = setInterval(fetchConversation, 5000)
    return () => clearInterval(interval)
  }, [conversationId])

  useEffect(() => {
    scrollToBottom()
  }, [conversation?.messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const fetchConversation = async () => {
    if (!conversationId) return

    try {
      const data = await conversationsApi.get(conversationId)
      setConversation(data)

      // Mark as read
      await conversationsApi.markRead(conversationId)
    } catch (error) {
      console.error('Error fetching conversation:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to load conversation.',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleSendMessage = async () => {
    if (!message.trim() || !conversationId) return

    setSending(true)
    try {
      await conversationsApi.sendMessage(conversationId, message)
      setMessage('')
      await fetchConversation()
    } catch (error) {
      console.error('Error sending message:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to send message.',
      })
    } finally {
      setSending(false)
    }
  }

  const handleLock = async () => {
    if (!conversationId) return

    try {
      await conversationsApi.lock(conversationId)
      await fetchConversation()
      toast({
        title: 'Conversation locked',
        description: 'You are now handling this conversation.',
      })
    } catch (error) {
      console.error('Error locking conversation:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to lock conversation.',
      })
    }
  }

  const handleUnlock = async () => {
    if (!conversationId) return

    try {
      await conversationsApi.unlock(conversationId)
      await fetchConversation()
      toast({
        title: 'Conversation unlocked',
        description: 'AI will resume handling this conversation.',
      })
    } catch (error) {
      console.error('Error unlocking conversation:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to unlock conversation.',
      })
    }
  }

  const handleResolve = async () => {
    if (!conversationId) return

    try {
      await conversationsApi.resolve(conversationId)
      await fetchConversation()
      toast({
        title: 'Conversation resolved',
        description: 'This conversation has been marked as resolved.',
      })
    } catch (error) {
      console.error('Error resolving conversation:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to resolve conversation.',
      })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Conversation not found.</p>
        <Button onClick={() => navigate('/inbox')} className="mt-4">
          Back to Inbox
        </Button>
      </div>
    )
  }

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/inbox')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-xl font-bold">
              {conversation.customer_name || 'Anonymous'}
            </h1>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="outline">{conversation.channel}</Badge>
              <Badge variant={conversation.state === 'resolved' ? 'success' : 'secondary'}>
                {conversation.state.replace('_', ' ')}
              </Badge>
              {conversation.is_locked && (
                <Badge variant="warning">
                  Locked by {conversation.assigned_to_name || 'Unknown'}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!conversation.is_locked ? (
            <Button variant="outline" onClick={handleLock}>
              <Lock className="h-4 w-4 mr-2" />
              Take Over
            </Button>
          ) : (
            <Button variant="outline" onClick={handleUnlock}>
              <Unlock className="h-4 w-4 mr-2" />
              Release
            </Button>
          )}
          {conversation.state !== 'resolved' && (
            <Button variant="outline" onClick={handleResolve}>
              <CheckCircle className="h-4 w-4 mr-2" />
              Resolve
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-1 gap-4 mt-4 overflow-hidden">
        {/* Messages */}
        <Card className="flex-1 flex flex-col">
          <ScrollArea className="flex-1 p-4">
            <div className="space-y-4">
              {conversation.messages?.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    'flex gap-3',
                    msg.sender === 'customer' ? '' : 'flex-row-reverse'
                  )}
                >
                  <Avatar className="h-8 w-8 flex-shrink-0">
                    <AvatarFallback>
                      {senderIcons[msg.sender]}
                    </AvatarFallback>
                  </Avatar>
                  <div
                    className={cn(
                      'max-w-[70%] rounded-lg p-3',
                      msg.sender === 'customer'
                        ? 'bg-muted'
                        : msg.sender === 'ai'
                          ? 'bg-blue-100'
                          : 'bg-primary text-primary-foreground'
                    )}
                  >
                    <p className="text-sm">{msg.content}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs opacity-70">
                        {format(new Date(msg.created_at), 'HH:mm')}
                      </span>
                      {msg.confidence_score !== null && msg.sender === 'ai' && (
                        <span className="text-xs opacity-70">
                          ({Math.round(msg.confidence_score * 100)}% confidence)
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>

          {/* Message Input */}
          <div className="p-4 border-t">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleSendMessage()
              }}
              className="flex gap-2"
            >
              <Input
                placeholder="Type your message..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                disabled={sending}
              />
              <Button type="submit" disabled={sending || !message.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            </form>
            {!conversation.is_locked && (
              <p className="text-xs text-muted-foreground mt-2">
                💡 Click "Take Over" to disable AI and respond manually.
              </p>
            )}
          </div>
        </Card>

        {/* Customer Info Sidebar */}
        <Card className="w-80 flex-shrink-0">
          <CardHeader>
            <CardTitle className="text-sm">Customer Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-xs text-muted-foreground">Name</p>
              <p className="text-sm">{conversation.customer_name || 'Not provided'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Email</p>
              <p className="text-sm">{conversation.customer_email || 'Not provided'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Phone</p>
              <p className="text-sm">{conversation.customer_phone || 'Not provided'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Location</p>
              <p className="text-sm">{conversation.location_name || 'Not set'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Started</p>
              <p className="text-sm">
                {formatDistanceToNow(new Date(conversation.created_at), { addSuffix: true })}
              </p>
            </div>
            {conversation.intent && (
              <div>
                <p className="text-xs text-muted-foreground">Intent</p>
                <Badge variant="outline">{conversation.intent}</Badge>
              </div>
            )}
            {conversation.tags?.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground">Tags</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {conversation.tags.map((tag, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
