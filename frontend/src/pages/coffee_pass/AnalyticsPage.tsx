import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Coffee, Repeat, TrendingUp, AlertTriangle, Wallet,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

import { useAuthStore } from '@/store/auth'
import {
  coffeePassApi, type AnalyticsSummary, type Anomaly,
} from '@/services/coffeePass'

// Sentiment colours are semantic and fixed: green good, amber neutral, red bad.
const FEEDBACK_COLORS = ['#10b981', '#f59e0b', '#ef4444']

export function CoffeePassAnalyticsPage() {
  const { t } = useTranslation()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [anomalies, setAnomalies] = useState<Anomaly[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      // One parallel fetch, not a waterfall.
      const [summaryData, anomalyData] = await Promise.all([
        coffeePassApi.summary({ organization: orgId }),
        coffeePassApi.anomalies({ organization: orgId }),
      ])
      setSummary(summaryData)
      setAnomalies(anomalyData)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { refresh() }, [refresh])

  const feedbackData = useMemo(() => {
    if (!summary) return []
    return [
      { name: t('coffeePass.analytics.good'), value: summary.feedback.good },
      { name: t('coffeePass.analytics.okay'), value: summary.feedback.okay },
      { name: t('coffeePass.analytics.notGood'), value: summary.feedback.not_good },
    ].filter((row) => row.value > 0)
  }, [summary, t])

  const retentionData = useMemo(() => {
    if (!summary) return []
    const { retention } = summary
    return [
      {
        name: t('coffeePass.analytics.usedWithin7'),
        value: retention.first_redemption_within_7_days,
      },
      { name: t('coffeePass.analytics.repeatUsers'), value: retention.repeat_customers },
      { name: t('coffeePass.analytics.neverUsed'), value: retention.never_redeemed },
    ]
  }, [summary, t])

  if (loading) return <Loading variant="cards" count={4} />
  if (error) return <ErrorState message={error} onRetry={refresh} />
  if (!summary) return null

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('coffeePass.analytics.title')}</h1>
        <p className="text-sm text-muted-foreground">
          {t('coffeePass.analytics.subtitle')}
        </p>
      </div>

      {/* Anomalies first: these are the things an owner must ACT on. */}
      {anomalies.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-amber-900">
              <AlertTriangle className="h-4 w-4" />
              {t('coffeePass.analytics.anomalies')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {anomalies.map((anomaly, index) => (
              <div key={`${anomaly.code}-${index}`} className="text-sm text-amber-900">
                <span className="font-medium">
                  {t(`coffeePass.analytics.anomaly.${anomaly.code}`, {
                    defaultValue: anomaly.detail,
                  })}
                </span>
                {anomaly.count !== undefined && (
                  <span className="ml-1 opacity-75">({anomaly.count})</span>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Wallet}
          label={t('coffeePass.analytics.netRevenue')}
          value={`HK$${summary.sales.net_revenue_hkd}`}
          hint={t('coffeePass.analytics.purchasesPaid', {
            count: summary.sales.purchases_paid,
          })}
        />
        <StatCard
          icon={Coffee}
          label={t('coffeePass.analytics.activePasses')}
          value={String(summary.passes.active)}
          hint={t('coffeePass.analytics.ofTotal', { total: summary.passes.total })}
        />
        <StatCard
          icon={TrendingUp}
          label={t('coffeePass.analytics.discountGiven')}
          value={`HK$${summary.redemptions.total_discount_hkd}`}
          hint={t('coffeePass.analytics.redemptionCount', {
            count: summary.redemptions.count,
          })}
        />
        <StatCard
          icon={Repeat}
          label={t('coffeePass.analytics.repeatRate')}
          value={`${summary.retention.repeat_rate}%`}
          hint={t('coffeePass.analytics.repeatHint')}
          // Retention is the metric the whole product exists to move.
          highlight
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              {t('coffeePass.analytics.retention')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summary.retention.passes_measured === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">
                {t('coffeePass.analytics.noData')}
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={retentionData}>
                  <XAxis dataKey="name" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#0f766e" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              {t('coffeePass.analytics.feedback')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {feedbackData.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">
                {t('coffeePass.analytics.noData')}
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={feedbackData} dataKey="value" nameKey="name"
                    cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={2}
                  >
                    {feedbackData.map((entry, index) => (
                      <Cell key={entry.name} fill={FEEDBACK_COLORS[index]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            {t('coffeePass.analytics.details')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2 text-sm">
            <Row
              label={t('coffeePass.analytics.checkoutStarted')}
              value={String(summary.sales.checkout_started)}
            />
            <Row
              label={t('coffeePass.analytics.conversion')}
              value={`${summary.sales.conversion_rate}%`}
            />
            <Row
              label={t('coffeePass.analytics.refunded')}
              value={`HK$${summary.sales.refunded_hkd}`}
            />
            <Row
              label={t('coffeePass.analytics.averageSaving')}
              value={`HK$${summary.redemptions.average_saving_hkd}`}
            />
            <Row
              label={t('coffeePass.analytics.firstUseRate')}
              value={`${summary.retention.first_redemption_rate}%`}
            />
            <Row
              label={t('coffeePass.analytics.voided')}
              value={String(summary.redemptions.voided_count)}
            />
            <Row
              label={t('coffeePass.analytics.expiredPasses')}
              value={String(summary.passes.expired)}
            />
            <Row
              label={t('coffeePass.analytics.suspendedPasses')}
              value={String(summary.passes.suspended)}
            />
            {/* Flagged because a redemption without a receipt cannot be
                reconciled against the POS. */}
            <Row
              label={t('coffeePass.analytics.missingReceipt')}
              value={String(summary.redemptions.missing_receipt_reference)}
              warn={summary.redemptions.missing_receipt_reference > 0}
            />
          </dl>
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({
  icon: Icon, label, value, hint, highlight,
}: {
  icon: typeof Wallet
  label: string
  value: string
  hint?: string
  highlight?: boolean
}) {
  return (
    <Card className={highlight ? 'border-teal-300 bg-teal-50/40' : undefined}>
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Icon className="h-4 w-4" />
          <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
        </div>
        <div className="text-2xl font-semibold mt-2 tabular-nums">{value}</div>
        {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      </CardContent>
    </Card>
  )
}

function Row({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex justify-between border-b py-1.5 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`tabular-nums font-medium ${warn ? 'text-amber-600' : ''}`}>
        {value}
      </dd>
    </div>
  )
}
