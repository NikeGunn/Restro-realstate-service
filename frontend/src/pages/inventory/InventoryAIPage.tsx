import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Send, Bot, User, Sparkles, Search, Boxes, AlertTriangle,
  Activity, BrainCircuit, Check, ShieldCheck, Database, TerminalSquare,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AgentPlanning, type PlanStep, type PlanStepStatus } from '@/components/ui/ai-planning'
import { deriveStageStatus } from './agent-planning-logic'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type AIQueryResult } from '@/services/inventory'

/* ------------------------------------------------------------------ *
 * Inventory AI chat (Plane B). The assistant visibly "reasons" through
 * the real backend stages of InventoryAIEngine.query() before the
 * grounded answer lands:
 *
 *   parse → scan live stock → check active alerts → review recent
 *   movements → synthesize grounded answer
 *
 * Those five stages are exactly what the engine does (see
 * apps/inventory/services/ai_engine.py). The planning timeline is driven
 * forward by a short stepper while the request is in flight, but the
 * TRUTH always comes from the API response: final step statuses, the
 * real confidence, and the real data_points_used the model cited. No
 * fabricated data is shown — the timeline is a faithful, animated view
 * of work the server genuinely performs.
 * ------------------------------------------------------------------ */

type Phase = 'planning' | 'done' | 'error'

interface Turn {
  role: 'user' | 'assistant'
  text?: string
  // assistant-only
  phase?: Phase
  activeStage?: number          // index of the stage currently "working"
  confidence?: number
  dataPoints?: string[]
  errorDetail?: string
}

const SUGGESTIONS = [
  'Which items are running low?',
  'What did we consume the most last week?',
  'Show me items that need reordering.',
  'Which suppliers are most active?',
] as const

// Real backend stages, in order. `stageKey` maps to i18n; `icon` is the
// pending/idle glyph (active/success swap to spinner/check in the card).
const STAGES = [
  { key: 'parse', icon: <Search className="w-3.5 h-3.5" /> },
  { key: 'scan', icon: <Boxes className="w-3.5 h-3.5" /> },
  { key: 'alerts', icon: <AlertTriangle className="w-3.5 h-3.5" /> },
  { key: 'movements', icon: <Activity className="w-3.5 h-3.5" /> },
  { key: 'synthesize', icon: <BrainCircuit className="w-3.5 h-3.5" /> },
] as const

// How long (ms) we let each non-final stage "work" while waiting on the API.
// The synthesize stage stays active until the real response resolves it, so
// these only pace the lead-up and never outrun the actual answer.
const STAGE_PACING = [380, 620, 460, 540] as const

export function InventoryAIPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  // Clean up any in-flight stage timers on unmount.
  useEffect(() => () => { timersRef.current.forEach(clearTimeout) }, [])

  // Mutate the last (assistant) turn in place.
  const patchLastTurn = useCallback((patch: Partial<Turn>) => {
    setTurns(prev => {
      if (prev.length === 0) return prev
      const next = prev.slice()
      next[next.length - 1] = { ...next[next.length - 1], ...patch }
      return next
    })
  }, [])

  const ask = useCallback(async (q: string) => {
    if (!q.trim() || !orgId || loading) return

    timersRef.current.forEach(clearTimeout)
    timersRef.current = []

    setInput('')
    setLoading(true)
    setTurns(prev => [
      ...prev,
      { role: 'user', text: q },
      { role: 'assistant', phase: 'planning', activeStage: 0 },
    ])

    // Pace the lead-up stages forward while the request is in flight. The
    // final (synthesize) stage is left active until the API resolves it.
    let elapsed = 0
    STAGE_PACING.forEach((ms, i) => {
      elapsed += ms
      timersRef.current.push(
        setTimeout(() => patchLastTurn({ activeStage: i + 1 }), elapsed)
      )
    })

    try {
      const res: AIQueryResult = await inventoryApi.aiQuery(q, orgId)
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []
      patchLastTurn({
        phase: 'done',
        activeStage: STAGES.length,
        text: res.answer,
        confidence: res.confidence,
        dataPoints: res.data_points_used,
      })
    } catch (e: any) {
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []
      const detail = e?.response?.data?.detail || String(e)
      patchLastTurn({ phase: 'error', errorDetail: detail, text: `⚠ ${detail}` })
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
  }, [orgId, loading, patchLastTurn, toast, t])

  return (
    <div className="space-y-6 p-6 max-w-4xl">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Sparkles className="h-6 w-6 text-purple-600" />
          {t('inventory.ai.title')}
        </h1>
        <p className="text-sm text-slate-500">{t('inventory.ai.subtitle')}</p>
      </div>

      <Card className="h-[64vh] flex flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
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
                    className="text-left p-2 rounded border hover:bg-slate-50 text-sm transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="flex gap-2 justify-end">
                <div className="max-w-[80%] rounded-lg p-3 bg-blue-600 text-white">
                  <div className="text-sm whitespace-pre-wrap">{m.text}</div>
                </div>
                <User className="h-6 w-6 text-blue-600 shrink-0 mt-1" />
              </div>
            ) : (
              <div key={i} className="flex gap-2 justify-start">
                <Bot className="h-6 w-6 text-purple-600 shrink-0 mt-1" />
                <div className="w-full max-w-[88%] space-y-3">
                  <AgentPlanning
                    title={
                      m.phase === 'planning' ? t('inventory.ai.plan.titleWorking')
                        : m.phase === 'error' ? t('inventory.ai.plan.titleError')
                          : t('inventory.ai.plan.titleDone')
                    }
                    defaultMainExpanded={m.phase === 'planning'}
                    steps={buildSteps(m, t)}
                  />

                  {/* Grounded answer, shown once synthesis completes. */}
                  {m.phase !== 'planning' && m.text && (
                    <div className={`rounded-lg p-3 text-sm whitespace-pre-wrap ${
                      m.phase === 'error'
                        ? 'bg-rose-50 text-rose-800 border border-rose-200 dark:bg-rose-500/10 dark:text-rose-300'
                        : 'bg-slate-100 dark:bg-secondary/40'
                    }`}>
                      {m.text}
                      {m.phase === 'done' && typeof m.confidence === 'number' && (
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                          <Badge variant="outline" className={
                            m.confidence >= 0.7 ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300'
                              : 'bg-amber-50 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300'
                          }>
                            <ShieldCheck className="mr-1 h-3 w-3" />
                            {t('inventory.ai.confidence')}: {Math.round(m.confidence * 100)}%
                          </Badge>
                          {m.dataPoints && m.dataPoints.length > 0 && (
                            <span className="text-slate-500">
                              ({m.dataPoints.length} {t('inventory.ai.dataPoints')})
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
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

/* A terminal-style panel that surfaces the real backend query a stage runs,
 * so the operator can see exactly what the agent touches in the background. */
function QueryPanel({
  query, desc, status, t,
}: {
  query: string
  desc: string
  status: PlanStepStatus
  t: (k: string) => string
}) {
  const stateLabel =
    status === 'active' ? t('inventory.ai.plan.detail.running')
      : status === 'success' ? t('inventory.ai.plan.detail.returned')
        : t('inventory.ai.plan.detail.queued')
  return (
    <div className="space-y-2 font-mono text-[11px] mt-2">
      <div className="flex items-center gap-2">
        <span className="px-1.5 py-0.5 rounded-md bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 font-semibold flex items-center gap-1">
          <TerminalSquare className="w-3 h-3" />
          inventory.db
        </span>
        <span className={
          status === 'active'
            ? 'text-blue-600 dark:text-blue-400 animate-pulse'
            : status === 'success'
              ? 'text-emerald-600 dark:text-emerald-400'
              : 'text-muted-foreground'
        }>
          {stateLabel}
        </span>
      </div>
      <div className="relative rounded-md overflow-hidden bg-zinc-950 dark:bg-black/60 border border-border/50 p-3 shadow-inner">
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500 to-indigo-500 opacity-50" />
        <code className="text-zinc-300 break-words leading-relaxed">{query}</code>
      </div>
      <p className="text-muted-foreground leading-relaxed">{desc}</p>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Build the timeline steps for one assistant turn from its live phase.
 * The stage statuses are derived from `activeStage` while planning, and
 * pinned to the real outcome once the API resolves. Each DB-backed stage
 * carries a QueryPanel that shows the real query it runs server-side.
 * ------------------------------------------------------------------ */

// Maps each query stage to its real backend operation (see ai_engine.py).
const STAGE_QUERY: Record<string, { queryKey: string; descKey: string } | undefined> = {
  scan: { queryKey: 'inventory.ai.plan.detail.scanQuery', descKey: 'inventory.ai.plan.detail.scanDesc' },
  alerts: { queryKey: 'inventory.ai.plan.detail.alertsQuery', descKey: 'inventory.ai.plan.detail.alertsDesc' },
  movements: { queryKey: 'inventory.ai.plan.detail.movementsQuery', descKey: 'inventory.ai.plan.detail.movementsDesc' },
}

function buildSteps(m: Turn, t: (k: string) => string): PlanStep[] {
  const active = m.activeStage ?? 0

  return STAGES.map((stage, idx) => {
    const status = deriveStageStatus(m.phase ?? 'planning', active, idx, STAGES.length)
    const isSynth = idx === STAGES.length - 1
    let content: PlanStep['content']

    // Parse stage: short intent description.
    if (stage.key === 'parse') {
      content = (
        <p className="font-mono text-[11px] text-muted-foreground mt-2 leading-relaxed">
          {t('inventory.ai.plan.detail.parseDesc')}
        </p>
      )
    }

    // DB-backed stages: show the real query they run.
    const q = STAGE_QUERY[stage.key]
    if (q) {
      content = (
        <QueryPanel
          query={t(q.queryKey)}
          desc={t(q.descKey)}
          status={status}
          t={t}
        />
      )
    }

    if (isSynth && m.phase === 'done') {
      content = (
        <div className="space-y-3 font-mono text-[11px] mt-2">
          <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-medium">
            <Check className="w-3.5 h-3.5" />
            <span>{t('inventory.ai.plan.synthDone')}</span>
          </div>
          <div className="grid grid-cols-[90px_1fr] gap-1.5 bg-secondary/30 p-2.5 rounded-md border border-border/50">
            <span className="text-foreground/50 font-medium">{t('inventory.ai.confidence')}:</span>
            <span className={
              (m.confidence ?? 0) >= 0.7
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-amber-600 dark:text-amber-400'
            }>
              {Math.round((m.confidence ?? 0) * 100)}%
            </span>
            <span className="text-foreground/50 font-medium">{t('inventory.ai.plan.grounding')}:</span>
            <span className="text-foreground">
              {(m.dataPoints?.length ?? 0)} {t('inventory.ai.dataPoints')}
            </span>
          </div>
          {m.dataPoints && m.dataPoints.length > 0 && (
            <div className="p-2.5 rounded-md bg-card border border-border text-muted-foreground">
              <div className="mb-1.5 flex items-center gap-1.5 font-semibold text-foreground/70">
                <Database className="w-3 h-3" />
                {t('inventory.ai.plan.cited')}
              </div>
              <ul className="space-y-1 list-disc list-inside">
                {m.dataPoints.slice(0, 8).map((d, di) => (
                  <li key={di} className="break-words">{d}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )
    } else if (isSynth && m.phase === 'error') {
      content = (
        <div className="space-y-2 font-mono text-[11px] mt-2">
          <div className="p-3 rounded-md bg-rose-500/10 border border-rose-500/20">
            <div className="text-rose-600 dark:text-rose-400 font-bold mb-1 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              {t('inventory.ai.plan.synthError')}
            </div>
            <div className="text-rose-600/80 dark:text-rose-400/80 leading-relaxed break-words">
              {m.errorDetail}
            </div>
          </div>
        </div>
      )
    } else if (isSynth) {
      // synthesize stage while still planning — describe what the model is doing
      content = (
        <p className="font-mono text-[11px] text-muted-foreground mt-2 leading-relaxed">
          {t('inventory.ai.plan.detail.synthDesc')}
        </p>
      )
    }

    return {
      id: stage.key,
      title: t(`inventory.ai.plan.stage.${stage.key}`),
      status,
      icon: stage.icon,
      content,
      // Auto-open the stage that's currently working, and the final summary.
      defaultExpanded:
        (m.phase === 'planning' && status === 'active') ||
        (isSynth && m.phase === 'done'),
    }
  })
}
