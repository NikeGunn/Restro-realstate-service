import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Bot, User, Loader2, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type AIQueryResult } from '@/services/inventory'

interface Turn {
  role: 'user' | 'assistant'
  text: string
  confidence?: number
  data_points?: string[]
}

const SUGGESTIONS = [
  'Which items are running low?',
  'What did we consume the most last week?',
  'Show me items that need reordering.',
  'Which suppliers are most active?',
]

export function InventoryAIPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  async function ask(q: string) {
    if (!q.trim()) return
    if (!orgId) return
    setTurns(prev => [...prev, { role: 'user', text: q }])
    setInput('')
    setLoading(true)
    try {
      const res: AIQueryResult = await inventoryApi.aiQuery(q, orgId)
      setTurns(prev => [...prev, {
        role: 'assistant',
        text: res.answer,
        confidence: res.confidence,
        data_points: res.data_points_used,
      }])
    } catch (e: any) {
      const detail = e?.response?.data?.detail || String(e)
      setTurns(prev => [...prev, { role: 'assistant', text: `⚠ ${detail}` }])
      if (e?.response?.status === 403) {
        toast({
          title: t('inventory.ai.upgradeRequired'),
          description: t('inventory.ai.powerOnly'),
          variant: 'destructive',
        })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 p-6 max-w-4xl">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Sparkles className="h-6 w-6 text-purple-600" />
          {t('inventory.ai.title')}
        </h1>
        <p className="text-sm text-slate-500">{t('inventory.ai.subtitle')}</p>
      </div>

      <Card className="h-[60vh] flex flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {turns.length === 0 && (
            <div className="text-center py-12">
              <Bot className="h-12 w-12 mx-auto text-purple-400 mb-3" />
              <h3 className="font-semibold mb-2">{t('inventory.ai.greet')}</h3>
              <p className="text-sm text-slate-500 mb-4">{t('inventory.ai.tryAsking')}</p>
              <div className="grid gap-2 max-w-md mx-auto">
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => void ask(s)}
                    className="text-left p-2 rounded border hover:bg-slate-50 text-sm"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((m, i) => (
            <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {m.role === 'assistant' && <Bot className="h-6 w-6 text-purple-600 shrink-0 mt-1" />}
              <div className={`max-w-[80%] rounded-lg p-3 ${
                m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-slate-100'
              }`}>
                <div className="text-sm whitespace-pre-wrap">{m.text}</div>
                {m.role === 'assistant' && typeof m.confidence === 'number' && (
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <Badge variant="outline" className={
                      m.confidence >= 0.7 ? 'bg-emerald-50 text-emerald-800'
                        : 'bg-amber-50 text-amber-800'
                    }>
                      {t('inventory.ai.confidence')}: {Math.round(m.confidence * 100)}%
                    </Badge>
                    {m.data_points && m.data_points.length > 0 && (
                      <span className="text-slate-500">
                        ({m.data_points.length} {t('inventory.ai.dataPoints')})
                      </span>
                    )}
                  </div>
                )}
              </div>
              {m.role === 'user' && <User className="h-6 w-6 text-blue-600 shrink-0 mt-1" />}
            </div>
          ))}
          {loading && (
            <div className="flex gap-2">
              <Bot className="h-6 w-6 text-purple-600 shrink-0 mt-1" />
              <div className="bg-slate-100 rounded-lg p-3">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            </div>
          )}
        </div>
        <CardContent className="p-3 border-t">
          <form
            onSubmit={e => { e.preventDefault(); void ask(input) }}
            className="flex gap-2"
          >
            <Input
              placeholder={t('inventory.ai.placeholder')}
              value={input}
              onChange={e => setInput(e.target.value)}
              disabled={loading}
            />
            <Button type="submit" disabled={loading || !input.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </CardContent>
      </Card>

      <p className="text-xs text-slate-400">
        {t('inventory.ai.disclaimer')}
      </p>
    </div>
  )
}
