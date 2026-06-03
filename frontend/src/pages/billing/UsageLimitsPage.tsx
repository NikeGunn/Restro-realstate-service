import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Gauge, Save, ShieldAlert, Info } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { billingApi, type UsageLimit } from '@/services/billing'
import { hkd } from './format'

export function UsageLimitsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)
  const isOwner = useAuthStore(s =>
    s.user?.organizations?.find(o => o.id === s.currentOrganization?.id)?.role === 'owner')

  const [limit, setLimit] = useState<UsageLimit | null>(null)
  const [cap, setCap] = useState('')
  const [alertPct, setAlertPct] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!orgId) return
    let active = true
    billingApi.getLimit(orgId).then(l => {
      if (!active) return
      setLimit(l)
      setCap(l.monthly_ai_spend_cap_hkd)
      setAlertPct(String(l.alert_at_percent))
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId])

  async function save() {
    if (!orgId) return
    setSaving(true)
    try {
      const updated = await billingApi.updateLimit(orgId, {
        monthly_ai_spend_cap_hkd: cap,
        alert_at_percent: Math.max(1, Math.min(100, parseInt(alertPct, 10) || 80)),
      })
      setLimit(updated)
      toast({ title: t('billing.limitSaved') })
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.status === 403 ? t('billing.ownerOnly') : String(e),
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="py-10 text-muted-foreground">{t('common.loading')}</div>

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Gauge className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-semibold">{t('billing.limits')}</h1>
      </div>

      <Card className="max-w-2xl space-y-6 p-6">
        {/* Explainer */}
        <div className="flex items-start gap-3 rounded-xl border bg-muted/40 p-4 text-sm text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
          <p>{t('billing.capExplainer')}</p>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('billing.monthlyCap')}</Label>
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">HK$</span>
              <Input
                type="number" min="0" step="50" value={cap}
                onChange={e => setCap(e.target.value)} disabled={!isOwner}
                className="pl-11"
              />
            </div>
            <p className="text-xs text-muted-foreground">{t('billing.currentCap', { value: hkd(limit?.monthly_ai_spend_cap_hkd || 0) })}</p>
          </div>

          <div className="space-y-2">
            <Label>{t('billing.alertThreshold')}</Label>
            <div className="relative">
              <Input
                type="number" min="1" max="100" value={alertPct}
                onChange={e => setAlertPct(e.target.value)} disabled={!isOwner}
                className="pr-8"
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
            </div>
            <p className="text-xs text-muted-foreground">{t('billing.alertHint')}</p>
          </div>
        </div>

        {!isOwner ? (
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
            <ShieldAlert className="h-4 w-4" /> {t('billing.ownerOnly')}
          </div>
        ) : (
          <Button onClick={save} disabled={saving}
            className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500">
            <Save className="mr-2 h-4 w-4" /> {saving ? t('common.loading') : t('common.save')}
          </Button>
        )}
      </Card>
    </div>
  )
}
