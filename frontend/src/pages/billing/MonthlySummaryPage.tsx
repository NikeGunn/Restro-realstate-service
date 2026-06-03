import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CalendarRange, AlertTriangle } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip as RechartTooltip, Legend,
} from 'recharts'

import { Card } from '@/components/ui/card'
import { useAuthStore } from '@/store/auth'
import { billingApi, type MonthlySummary } from '@/services/billing'
import { hkd, monthName } from './format'

export function MonthlySummaryPage() {
  const { t } = useTranslation()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [rows, setRows] = useState<MonthlySummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!orgId) return
    let active = true
    billingApi.listMonthlySummaries(orgId)
      .then(r => { if (active) setRows(r) })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId])

  // Chronological for the chart (API returns newest-first).
  const chartData = useMemo(
    () => [...rows].reverse().map(r => ({
      label: `${monthName(r.month)} '${String(r.year).slice(2)}`,
      free: r.free_credits_used,
      paid: r.paid_credits_used,
      billable: parseFloat(r.total_billable_hkd),
    })),
    [rows],
  )

  if (loading) return <div className="py-10 text-muted-foreground">{t('common.loading')}</div>

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <CalendarRange className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-semibold">{t('billing.monthlySummary')}</h1>
      </div>

      {error ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <AlertTriangle className="h-8 w-8 text-rose-400" /> {t('billing.loadError')}
        </Card>
      ) : rows.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <CalendarRange className="h-8 w-8 opacity-40" /> {t('billing.noSummaries')}
        </Card>
      ) : (
        <>
          <Card className="p-6">
            <h3 className="mb-4 font-semibold">{t('billing.creditsUsedByMonth')}</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <RechartTooltip />
                <Legend />
                <Bar dataKey="free" name={t('billing.freeCredits')} stackId="c" fill="#34d399" radius={[0, 0, 0, 0]} />
                <Bar dataKey="paid" name={t('billing.paidCredits')} stackId="c" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">{t('billing.col.period')}</th>
                    <th className="px-4 py-3 text-right">{t('billing.freeCredits')}</th>
                    <th className="px-4 py-3 text-right">{t('billing.paidCredits')}</th>
                    <th className="px-4 py-3 text-right">{t('billing.images')}</th>
                    <th className="px-4 py-3 text-right">{t('billing.aiQueries')}</th>
                    <th className="px-4 py-3 text-right">{t('billing.billable')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rows.map(r => (
                    <tr key={r.id} className="transition-colors hover:bg-muted/30">
                      <td className="px-4 py-3 font-medium">{monthName(r.month)} {r.year}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.free_credits_used}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.paid_credits_used}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.image_generations}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.ai_queries}</td>
                      <td className="px-4 py-3 text-right font-medium tabular-nums">{hkd(r.total_billable_hkd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
