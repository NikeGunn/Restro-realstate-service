/**
 * PlanGate — a company-standard "upgrade required / plan expired" screen.
 *
 * Power-plan-gated features (e.g. AI Content Studio) return HTTP 403 from the
 * backend (ContentStudioPermission → "AI Content Studio requires the Power plan.")
 * once an org is on / has lapsed to the Basic plan. Without this, the frontend
 * surfaces a raw AxiosError in the console and a broken/empty page.
 *
 * Usage in a page:
 *   const [planBlocked, setPlanBlocked] = useState(false)
 *   ...
 *   .catch(e => {
 *     if (isPlanGateError(e)) { setPlanBlocked(true); return }
 *     toast({ ... })
 *   })
 *   ...
 *   if (planBlocked) return <PlanGate feature={t('contentStudio.title')} />
 */
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AxiosError } from 'axios'
import { Lock, Sparkles, ArrowRight, Crown } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

/**
 * True when an error is a 403 that represents a plan/permission gate (as opposed
 * to a transient failure). We treat *any* 403 on a power-gated feature as a plan
 * gate, and additionally key off the backend's permission message when present.
 */
export function isPlanGateError(err: unknown): boolean {
  const e = err as AxiosError<{ detail?: string }>
  if (!e || e.isAxiosError !== true) return false
  if (e.response?.status !== 403) return false
  const detail = (e.response?.data?.detail || '').toLowerCase()
  // Heuristic: explicit plan message, OR any 403 (the feature is plan-gated, so
  // a 403 here almost always means "not on the right plan").
  if (detail.includes('plan') || detail.includes('power')) return true
  return true
}

interface PlanGateProps {
  /** Human label of the feature being gated, e.g. "AI Content Studio". */
  feature?: string
  /** Where the upgrade CTA points. Defaults to the billing/plan settings page. */
  upgradeTo?: string
}

export function PlanGate({ feature, upgradeTo = '/settings?tab=plan' }: PlanGateProps) {
  const { t } = useTranslation()
  const featureLabel = feature || t('planGate.defaultFeature')

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <Card className="relative w-full max-w-lg overflow-hidden p-8 text-center md:p-10">
        {/* Soft brand glow */}
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-violet-200/40 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 -left-16 h-48 w-48 rounded-full bg-indigo-200/40 blur-3xl" />

        <div className="relative">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 ring-1 ring-indigo-500/20">
            <Lock className="h-8 w-8 text-indigo-600" />
          </div>

          <Badge variant="secondary" className="mb-3 bg-amber-50 text-amber-700">
            <Crown className="mr-1 h-3 w-3" /> {t('planGate.powerBadge')}
          </Badge>

          <h1 className="text-2xl font-bold text-foreground">
            {t('planGate.title', { feature: featureLabel })}
          </h1>

          <p className="mx-auto mt-3 max-w-md text-muted-foreground">
            {t('planGate.body', { feature: featureLabel })}
          </p>

          <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg" className="w-full sm:w-auto">
              <Link to={upgradeTo}>
                <Sparkles className="mr-2 h-4 w-4" />
                {t('planGate.upgradeCta')}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="w-full sm:w-auto">
              <Link to="/dashboard">{t('planGate.backToDashboard')}</Link>
            </Button>
          </div>

          <p className="mt-6 text-xs text-muted-foreground">
            {t('planGate.contactHint')}
          </p>
        </div>
      </Card>
    </div>
  )
}
