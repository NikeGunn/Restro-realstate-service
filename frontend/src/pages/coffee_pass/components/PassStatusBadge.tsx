import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import type { PassStatus, PlanStatus, RedemptionStatus } from '@/services/coffeePass'

/**
 * Status colour is semantic, not decorative:
 *   emerald = money is flowing / entitlement is live
 *   amber   = paused or held — reversible, needs attention
 *   rose    = terminal / refused
 *   slate   = inert (draft, archived)
 * Staff scan these under time pressure, so the mapping must never vary by page.
 */
const PASS_VARIANT: Record<PassStatus, string> = {
  active: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100',
  pending_payment: 'bg-slate-200 text-slate-700 hover:bg-slate-200',
  expired: 'bg-slate-200 text-slate-600 hover:bg-slate-200',
  suspended: 'bg-amber-100 text-amber-700 hover:bg-amber-100',
  cancelled: 'bg-rose-100 text-rose-700 hover:bg-rose-100',
}

const PLAN_VARIANT: Record<PlanStatus, string> = {
  draft: 'bg-slate-200 text-slate-700 hover:bg-slate-200',
  active: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100',
  paused: 'bg-amber-100 text-amber-700 hover:bg-amber-100',
  archived: 'bg-slate-200 text-slate-500 hover:bg-slate-200',
}

const REDEMPTION_VARIANT: Record<RedemptionStatus, string> = {
  redeemed: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100',
  voided: 'bg-rose-100 text-rose-700 hover:bg-rose-100',
}

export function PassStatusBadge({ status }: { status: PassStatus }) {
  const { t } = useTranslation()
  return (
    <Badge className={PASS_VARIANT[status]}>
      {t(`coffeePass.passStatus.${status}`)}
    </Badge>
  )
}

export function PlanStatusBadge({ status }: { status: PlanStatus }) {
  const { t } = useTranslation()
  return (
    <Badge className={PLAN_VARIANT[status]}>
      {t(`coffeePass.planStatus.${status}`)}
    </Badge>
  )
}

export function RedemptionStatusBadge({ status }: { status: RedemptionStatus }) {
  const { t } = useTranslation()
  return (
    <Badge className={REDEMPTION_VARIANT[status]}>
      {t(`coffeePass.redemptionStatus.${status}`)}
    </Badge>
  )
}
