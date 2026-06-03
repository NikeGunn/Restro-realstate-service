import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Wallet, Coins, Sparkles, TrendingUp, AlertTriangle, ArrowRight,
  Gauge, Clock, Infinity as InfinityIcon, CreditCard,
} from 'lucide-react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartTooltip,
} from 'recharts'

import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { billingApi, type UsageSummary } from '@/services/billing'
import { MODULE_LABELS, MODULE_COLORS, CAP_THEME, hkd } from './format'

export function BillingDashboardPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)
  const [searchParams, setSearchParams] = useSearchParams()

  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // Returning from Stripe Checkout: show the outcome, then strip the params.
  useEffect(() => {
    if (searchParams.get('session_id')) {
      toast({ title: t('payments.successToast'), description: t('payments.successBody') })
      searchParams.delete('session_id'); searchParams.delete('purchase')
      setSearchParams(searchParams, { replace: true })
    } else if (searchParams.get('cancelled')) {
      toast({ title: t('payments.cancelledToast'), variant: 'destructive' })
      searchParams.delete('cancelled'); searchParams.delete('purchase')
      setSearchParams(searchParams, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!orgId) return
    let active = true
    setLoading(true); setError(false)
    billingApi.getSummary(orgId)
      .then(s => { if (active) setSummary(s) })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId])

  // Derive chart + display data during render (no effect, no extra state).
  const moduleData = useMemo(() => {
    if (!summary) return []
    return Object.entries(summary.by_module)
      .map(([key, v]) => ({
        key,
        name: MODULE_LABELS[key] || key,
        value: v.count,
        billable: parseFloat(v.billable_hkd),
        color: MODULE_COLORS[key] || '#94a3b8',
      }))
      .filter(d => d.value > 0)
  }, [summary])

  if (loading) return <DashboardSkeleton />
  if (error || !summary) {
    return (
      <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
        <AlertTriangle className="h-8 w-8 text-rose-400" />
        {t('billing.loadError')}
      </Card>
    )
  }

  const theme = CAP_THEME[summary.cap_status]
  const pct = Math.min(100, summary.spend_percent_of_cap)
  const totalCredits = summary.free_credits_remaining + summary.paid_credits_remaining
  const usedThisMonth = summary.free_credits_used_this_month + summary.paid_credits_used_this_month

  return (
    <div className="space-y-6">
      {/* ── Hero: spend gauge + headline ─────────────────────────────── */}
      <div className="relative overflow-hidden rounded-3xl border bg-gradient-to-br from-slate-900 via-indigo-950 to-violet-950 p-6 text-white md:p-8">
        <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-violet-500/20 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="relative grid grid-cols-1 items-center gap-8 md:grid-cols-[auto,1fr]">
          <SpendGauge percent={pct} status={summary.cap_status} />
          <div>
            <Badge className="mb-3 border-white/20 bg-white/10 text-white backdrop-blur">
              <Sparkles className="mr-1 h-3 w-3" /> {t('billing.title')}
            </Badge>
            <h1 className="text-2xl font-bold leading-tight md:text-3xl">
              {hkd(summary.current_estimated_spend_hkd)}
              <span className="ml-2 text-base font-normal text-white/60">
                / {hkd(summary.monthly_ai_spend_cap_hkd)} {t('billing.thisMonth')}
              </span>
            </h1>
            <p className="mt-2 max-w-lg text-sm text-white/70">
              {summary.cap_status === 'blocked'
                ? t('billing.heroBlocked')
                : t('billing.heroBody', { pct: Math.round(pct) })}
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button asChild size="sm" className="bg-white text-indigo-700 hover:bg-white/90">
                <Link to="/billing/buy">
                  <CreditCard className="mr-2 h-4 w-4" /> {t('payments.buyCredits')}
                </Link>
              </Button>
              <Button asChild variant="secondary" size="sm">
                <Link to="/billing/limits">
                  <Gauge className="mr-2 h-4 w-4" /> {t('billing.adjustCap')}
                </Link>
              </Button>
              <Button asChild variant="ghost" size="sm" className="text-white hover:bg-white/10 hover:text-white">
                <Link to="/billing/usage">
                  {t('billing.viewUsage')} <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Cap status banner (only when not healthy) ────────────────── */}
      {summary.cap_status !== 'active' ? (
        <div className={`flex items-start gap-3 rounded-2xl border p-4 ${theme.bg} ${theme.text} ring-1 ${theme.ring}`}>
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="text-sm">
            <div className="font-semibold">{t(`billing.capBanner.${summary.cap_status}.title`)}</div>
            <div className="opacity-90">{t(`billing.capBanner.${summary.cap_status}.body`)}</div>
          </div>
        </div>
      ) : null}

      {/* ── Credit wallet cards ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Coins className="h-5 w-5" />} accent="from-emerald-500/15 to-emerald-500/5 text-emerald-600"
          label={t('billing.freeCredits')} value={summary.free_credits_remaining}
          sub={t('billing.usedCount', { n: summary.free_credits_used_this_month })}
        />
        <StatCard
          icon={<Wallet className="h-5 w-5" />} accent="from-indigo-500/15 to-indigo-500/5 text-indigo-600"
          label={t('billing.paidCredits')} value={summary.paid_credits_remaining}
          sub={t('billing.usedCount', { n: summary.paid_credits_used_this_month })}
        />
        <StatCard
          icon={<Clock className="h-5 w-5" />} accent="from-amber-500/15 to-amber-500/5 text-amber-600"
          label={t('billing.reserved')} value={summary.reserved_credits}
          sub={t('billing.inFlight')}
        />
        <StatCard
          icon={<TrendingUp className="h-5 w-5" />} accent="from-violet-500/15 to-violet-500/5 text-violet-600"
          label={t('billing.totalAvailable')} value={summary.total_available}
          sub={t('billing.creditsOf', { total: totalCredits })}
        />
      </div>

      {/* ── Spend vs cap bar + by-module donut ───────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-6 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-semibold">{t('billing.spendVsCap')}</h3>
            <Badge variant="outline" className={`${theme.text} ${theme.bg}`}>{t(`billing.cap.${summary.cap_status}`)}</Badge>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>{hkd(summary.current_estimated_spend_hkd)}</span>
              <span>{hkd(summary.monthly_ai_spend_cap_hkd)}</span>
            </div>
            <div className="relative h-4 w-full overflow-hidden rounded-full bg-muted">
              {/* Threshold ticks at 50/80% */}
              <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
              <div className="absolute inset-y-0 left-[80%] w-px bg-border" />
              <div
                className={`h-full rounded-full transition-all duration-700 ${theme.bar}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {t('billing.spendBarHint', { pct: Math.round(pct), used: usedThisMonth })}
            </p>
          </div>

          {/* Per-module billable breakdown rows */}
          <div className="mt-6 space-y-3">
            {moduleData.length > 0 ? moduleData.map(m => (
              <div key={m.key} className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full" style={{ backgroundColor: m.color }} />
                <span className="flex-1 text-sm">{m.name}</span>
                <span className="text-sm text-muted-foreground">{m.value} {t('billing.calls')}</span>
                <span className="w-24 text-right text-sm font-medium">{hkd(m.billable)}</span>
              </div>
            )) : (
              <p className="text-sm text-muted-foreground">{t('billing.noUsageYet')}</p>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="mb-4 font-semibold">{t('billing.byModule')}</h3>
          {moduleData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={moduleData} dataKey="value" nameKey="name"
                  innerRadius={55} outerRadius={85} paddingAngle={3} strokeWidth={0}
                >
                  {moduleData.map(d => <Cell key={d.key} fill={d.color} />)}
                </Pie>
                <RechartTooltip
                  formatter={((v: unknown, n: unknown) => [`${v} ${t('billing.calls')}`, n]) as never}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[220px] flex-col items-center justify-center gap-2 text-muted-foreground">
              <InfinityIcon className="h-8 w-8 opacity-40" />
              <span className="text-sm">{t('billing.noUsageYet')}</span>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

/* ── Circular spend gauge (pure SVG, animated stroke) ───────────────── */
function SpendGauge({ percent, status }: { percent: number; status: UsageSummary['cap_status'] }) {
  const R = 52
  const C = 2 * Math.PI * R
  const dash = (Math.min(100, percent) / 100) * C
  const stroke = status === 'blocked' ? '#fb7185'
    : status === 'warning_80' ? '#fb923c'
    : status === 'warning_50' ? '#fbbf24' : '#34d399'
  return (
    <div className="relative h-36 w-36 shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={R} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="10" />
        <circle
          cx="60" cy="60" r={R} fill="none" stroke={stroke} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`} className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold">{Math.round(percent)}%</span>
        <span className="text-[11px] uppercase tracking-wide text-white/60">of cap</span>
      </div>
    </div>
  )
}

function StatCard({ icon, label, value, sub, accent }: {
  icon: React.ReactNode; label: string; value: number; sub: string; accent: string
}) {
  return (
    <Card className="p-5">
      <div className={`mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${accent}`}>
        {icon}
      </div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      <div className="text-sm font-medium text-foreground">{label}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>
    </Card>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-48 animate-pulse rounded-3xl bg-muted" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-32 animate-pulse rounded-xl bg-muted" />)}
      </div>
      <div className="h-72 animate-pulse rounded-xl bg-muted" />
    </div>
  )
}
