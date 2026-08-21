import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Coffee, Copy, Pause, Play, Plus, QrCode, AlertTriangle, Users,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/hooks/use-toast'
import {
  InventoryEmpty as Empty,
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

import { useAuthStore } from '@/store/auth'
import {
  coffeePassApi, publicPassUrl, type ActivationReadiness, type CoffeePassPlan,
} from '@/services/coffeePass'

import { PlanStatusBadge } from './components/PassStatusBadge'
import { PlanFormDialog } from './components/PlanForm'
import { PlanQrDialog } from './components/PlanQrDialog'

export function CoffeePassPlansPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [plans, setPlans] = useState<CoffeePassPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<CoffeePassPlan | null>(null)
  const [qrPlan, setQrPlan] = useState<CoffeePassPlan | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      setPlans(await coffeePassApi.listPlans({ organization: orgId }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { refresh() }, [refresh])

  const handleActivate = async (plan: CoffeePassPlan) => {
    setBusyId(plan.id)
    try {
      await coffeePassApi.activatePlan(plan.id)
      toast({ title: t('coffeePass.plans.activated') })
      await refresh()
    } catch (e) {
      // The backend returns the readiness detail so the owner learns WHY —
      // "break-even too high" is actionable, "400" is not.
      const detail = (e as { response?: { data?: ActivationReadiness & { detail?: string } } })
        .response?.data
      const reasons = detail?.errors?.length
        ? detail.errors.map((code) => t(`coffeePass.plans.errors.${code}`)).join(' · ')
        : t('coffeePass.plans.activateFailed')
      toast({ title: t('coffeePass.plans.activateFailed'), description: reasons,
        variant: 'destructive' })
    } finally {
      setBusyId(null)
    }
  }

  const handlePause = async (plan: CoffeePassPlan) => {
    setBusyId(plan.id)
    try {
      await coffeePassApi.pausePlan(plan.id)
      toast({
        title: t('coffeePass.plans.paused'),
        // Reassure the owner: pausing is not a revocation.
        description: t('coffeePass.plans.pausedHint'),
      })
      await refresh()
    } catch {
      toast({ title: t('coffeePass.plans.pauseFailed'), variant: 'destructive' })
    } finally {
      setBusyId(null)
    }
  }

  const copyQrLink = async (plan: CoffeePassPlan) => {
    try {
      await navigator.clipboard.writeText(publicPassUrl(plan))
      toast({ title: t('coffeePass.plans.linkCopied') })
    } catch {
      toast({ title: t('coffeePass.plans.copyFailed'), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('coffeePass.plans.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('coffeePass.plans.subtitle')}</p>
        </div>
        <Button onClick={() => { setEditing(null); setDialogOpen(true) }}>
          <Plus className="h-4 w-4 mr-2" />{t('coffeePass.plans.create')}
        </Button>
      </div>

      {loading ? (
        <Loading variant="cards" count={3} />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : plans.length === 0 ? (
        <Empty icon={Coffee} message={t('coffeePass.plans.empty')} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {plans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              busy={busyId === plan.id}
              onEdit={() => { setEditing(plan); setDialogOpen(true) }}
              onActivate={() => handleActivate(plan)}
              onPause={() => handlePause(plan)}
              onShowQr={() => setQrPlan(plan)}
              onCopyLink={() => copyQrLink(plan)}
            />
          ))}
        </div>
      )}

      <PlanQrDialog
        open={qrPlan !== null}
        plan={qrPlan}
        onOpenChange={(o) => { if (!o) setQrPlan(null) }}
      />

      <PlanFormDialog
        open={dialogOpen}
        plan={editing}
        onOpenChange={setDialogOpen}
        onSaved={refresh}
      />
    </div>
  )
}

function PlanCard({
  plan, busy, onEdit, onActivate, onPause, onShowQr, onCopyLink,
}: {
  plan: CoffeePassPlan
  busy: boolean
  onEdit: () => void
  onActivate: () => void
  onPause: () => void
  onShowQr: () => void
  onCopyLink: () => void
}) {
  const { t } = useTranslation()

  // Derive during render — no effect, no extra state (Vercel React guidance).
  const breakEvenVisits = plan.break_even?.break_even_visits ?? null
  const maxRecommended = plan.break_even?.max_recommended_visits ?? 20
  const unprofitable = breakEvenVisits !== null && breakEvenVisits > maxRecommended
  const itemCount = plan.eligible_items_detail?.length ?? 0

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base leading-tight">{plan.name}</CardTitle>
          <PlanStatusBadge status={plan.status} />
        </div>
        <p className="text-xs text-muted-foreground">{plan.location_name}</p>
      </CardHeader>

      <CardContent className="flex-1 space-y-3">
        {/* The offer in one line, the way the customer sees it. */}
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums">
            HK${plan.price_hkd}
          </span>
          <span className="text-sm text-muted-foreground">
            {t('coffeePass.plans.terms', {
              pct: parseFloat(plan.discount_percent),
              days: plan.duration_days,
            })}
          </span>
        </div>

        {/* Break-even is the honesty check: can a customer actually win? */}
        {breakEvenVisits !== null && (
          <div className={`rounded-md px-3 py-2 text-xs ${
            unprofitable
              ? 'bg-amber-50 text-amber-800 border border-amber-200'
              : 'bg-muted text-muted-foreground'
          }`}>
            {unprofitable && <AlertTriangle className="h-3.5 w-3.5 inline mr-1 -mt-0.5" />}
            {t('coffeePass.plans.breakEven', {
              price: plan.break_even?.average_eligible_price ?? '—',
              visits: breakEvenVisits,
            })}
          </div>
        )}

        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="outline" className="font-normal">
            <Coffee className="h-3 w-3 mr-1" />
            {t('coffeePass.plans.itemCount', { count: itemCount })}
          </Badge>
          <Badge variant="outline" className="font-normal">
            <Users className="h-3 w-3 mr-1" />
            {t('coffeePass.plans.activeMembers', { count: plan.active_pass_count })}
          </Badge>
        </div>
      </CardContent>

      <div className="p-4 pt-0 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onEdit} disabled={busy}>
          {t('common.edit')}
        </Button>

        {plan.status === 'active' ? (
          <Button size="sm" variant="outline" onClick={onPause} disabled={busy}>
            <Pause className="h-3.5 w-3.5 mr-1" />{t('coffeePass.plans.pause')}
          </Button>
        ) : plan.status !== 'archived' ? (
          <Button size="sm" onClick={onActivate} disabled={busy}>
            <Play className="h-3.5 w-3.5 mr-1" />{t('coffeePass.plans.activate')}
          </Button>
        ) : null}

        {/* Only an active plan has a QR worth handing to a customer.
            Two separate affordances on purpose: copy the link for a chat or an
            email, open the QR dialog to preview and download something to print. */}
        {plan.status === 'active' && (
          <>
            <Button size="sm" variant="ghost" onClick={onCopyLink} disabled={busy}>
              <Copy className="h-3.5 w-3.5 mr-1" />{t('coffeePass.plans.copyLink')}
            </Button>
            <Button size="sm" variant="ghost" onClick={onShowQr} disabled={busy}>
              <QrCode className="h-3.5 w-3.5 mr-1" />{t('coffeePass.plans.qrButton')}
            </Button>
          </>
        )}
      </div>
    </Card>
  )
}
