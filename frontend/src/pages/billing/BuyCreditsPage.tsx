import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Coins, Sparkles, Check, ShieldCheck, Lock, CreditCard, Zap,
  Loader2, ArrowRight, Receipt, BadgeCheck, AlertTriangle,
} from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { paymentsApi, type CreditPack, type CreditPurchase } from '@/services/payments'
import { hkd } from './format'

// Hoisted static trust badges — never re-allocated per render.
const TRUST = [
  { icon: ShieldCheck, key: 'securedByStripe' },
  { icon: Lock, key: 'pciCompliant' },
  { icon: Zap, key: 'instantCredits' },
] as const

const STATUS_THEME: Record<string, string> = {
  paid: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  pending: 'bg-sky-50 text-sky-700 border-sky-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  expired: 'bg-muted text-muted-foreground',
  refunded: 'bg-amber-50 text-amber-700 border-amber-200',
}

export function BuyCreditsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)
  const isOwner = useAuthStore(s =>
    s.user?.organizations?.find(o => o.id === s.currentOrganization?.id)?.role === 'owner')

  const [packs, setPacks] = useState<CreditPack[]>([])
  const [purchases, setPurchases] = useState<CreditPurchase[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [buying, setBuying] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId) return
    let active = true
    setLoading(true); setError(false)
    // No waterfall — fetch packs + purchases in parallel.
    Promise.all([paymentsApi.listPacks(), paymentsApi.listPurchases(orgId)])
      .then(([p, h]) => { if (active) { setPacks(p); setPurchases(h) } })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId])

  // Derive per-pack economics during render: unit price + savings vs the
  // cheapest pack's per-credit rate, and which pack is the best value.
  const enriched = useMemo(() => {
    if (packs.length === 0) return []
    const rates = packs.map(p => parseFloat(p.price_hkd) / Math.max(1, p.credits))
    const baseRate = Math.max(...rates) // worst (most expensive) per-credit rate
    let bestIdx = 0
    rates.forEach((r, i) => { if (r < rates[bestIdx]) bestIdx = i })
    return packs.map((p, i) => {
      const unit = rates[i]
      const savePct = baseRate > 0 ? Math.round((1 - unit / baseRate) * 100) : 0
      return { pack: p, unit, savePct, isBest: i === bestIdx }
    })
  }, [packs])

  async function buy(pack: CreditPack) {
    if (!orgId) return
    setBuying(pack.id)
    try {
      const res = await paymentsApi.createCheckout(orgId, pack.id)
      // Redirect to Stripe's hosted checkout — leaves our SPA entirely.
      window.location.href = res.checkout_url
    } catch (e: any) {
      const msg = e?.response?.status === 403
        ? t('payments.ownerOnly')
        : e?.response?.data?.detail || t('payments.checkoutFailed')
      toast({ title: t('common.error'), description: msg, variant: 'destructive' })
      setBuying(null)
    }
  }

  if (loading) return <BuySkeleton />
  if (error) {
    return (
      <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
        <AlertTriangle className="h-8 w-8 text-rose-400" /> {t('payments.loadError')}
      </Card>
    )
  }

  return (
    <div className="space-y-8">
      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-3xl border bg-gradient-to-br from-slate-900 via-indigo-950 to-violet-950 p-8 text-white md:p-10">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-violet-500/20 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="relative">
          <Badge className="mb-4 border-white/20 bg-white/10 text-white backdrop-blur">
            <Sparkles className="mr-1 h-3 w-3" /> {t('payments.badge')}
          </Badge>
          <h1 className="max-w-2xl text-3xl font-bold leading-tight md:text-4xl">
            {t('payments.heroTitle')}
          </h1>
          <p className="mt-3 max-w-xl text-white/70">{t('payments.heroSubtitle')}</p>
          <div className="mt-6 flex flex-wrap gap-5">
            {TRUST.map(({ icon: Icon, key }) => (
              <div key={key} className="flex items-center gap-2 text-sm text-white/80">
                <Icon className="h-4 w-4 text-emerald-300" /> {t(`payments.trust.${key}`)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Pack cards ────────────────────────────────────────────────── */}
      <div>
        <div className="mb-4 flex items-center gap-2">
          <Coins className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">{t('payments.choosePack')}</h2>
        </div>

        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          {enriched.map(({ pack, unit, savePct, isBest }) => (
            <Card
              key={pack.id}
              className={`relative flex flex-col p-6 transition-all ${
                isBest
                  ? 'border-indigo-400 shadow-lg shadow-indigo-500/10 ring-2 ring-indigo-400/40'
                  : 'hover:border-primary/50 hover:shadow-md'
              }`}
            >
              {isBest ? (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <Badge className="border-0 bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow">
                    <BadgeCheck className="mr-1 h-3 w-3" /> {t('payments.bestValue')}
                  </Badge>
                </div>
              ) : null}

              <div className={`mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl ${
                isBest ? 'bg-gradient-to-br from-indigo-500/20 to-violet-500/20 ring-1 ring-indigo-500/30'
                       : 'bg-muted'
              }`}>
                <Coins className={`h-6 w-6 ${isBest ? 'text-indigo-600' : 'text-muted-foreground'}`} />
              </div>

              <h3 className="text-lg font-semibold">{pack.name}</h3>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-3xl font-bold tabular-nums">{hkd(pack.price_hkd)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{pack.credits} {t('payments.credits')}</span>
                <span>·</span>
                <span>{hkd(unit)}/{t('payments.credit')}</span>
              </div>

              {savePct > 0 ? (
                <Badge variant="secondary" className="mt-3 w-fit bg-emerald-50 text-emerald-700">
                  {t('payments.save', { pct: savePct })}
                </Badge>
              ) : <div className="mt-3 h-[22px]" />}

              <p className="mt-3 flex-1 text-sm text-muted-foreground">{pack.description}</p>

              <Button
                onClick={() => buy(pack)}
                disabled={!isOwner || buying !== null}
                className={`mt-5 w-full ${
                  isBest ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500' : ''
                }`}
                variant={isBest ? 'default' : 'outline'}
              >
                {buying === pack.id ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t('payments.redirecting')}</>
                ) : (
                  <><CreditCard className="mr-2 h-4 w-4" /> {t('payments.buyNow')} <ArrowRight className="ml-2 h-4 w-4" /></>
                )}
              </Button>
            </Card>
          ))}
        </div>

        {!isOwner ? (
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {t('payments.ownerOnlyHint')}
          </p>
        ) : null}
      </div>

      {/* ── Recent purchases ──────────────────────────────────────────── */}
      {purchases.length > 0 ? (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <Receipt className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">{t('payments.recentPurchases')}</h2>
          </div>
          <Card className="divide-y">
            {purchases.slice(0, 6).map(p => (
              <div key={p.id} className="flex items-center gap-4 px-4 py-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                  {p.status === 'paid'
                    ? <Check className="h-4 w-4 text-emerald-600" />
                    : <Coins className="h-4 w-4 text-muted-foreground" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.pack_name} · {p.credits} {t('payments.credits')}</div>
                  <div className="text-xs text-muted-foreground">{new Date(p.created_at).toLocaleString()}</div>
                </div>
                <span className="text-sm tabular-nums">{hkd(p.amount_hkd)}</span>
                <Badge variant="outline" className={STATUS_THEME[p.status] || ''}>
                  {t(`payments.status.${p.status}`)}
                </Badge>
                {p.stripe_receipt_url ? (
                  <a href={p.stripe_receipt_url} target="_blank" rel="noreferrer"
                     className="text-xs font-medium text-primary hover:underline">
                    {t('payments.receipt')}
                  </a>
                ) : null}
              </div>
            ))}
          </Card>
        </div>
      ) : null}
    </div>
  )
}

function BuySkeleton() {
  return (
    <div className="space-y-8">
      <div className="h-44 animate-pulse rounded-3xl bg-muted" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-72 animate-pulse rounded-xl bg-muted" />)}
      </div>
    </div>
  )
}
