import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Users, Cake, MoonStar, ShieldCheck } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuthStore } from '@/store/auth'
import { crmApi, type CRMCustomer, type CustomerSource } from '@/services/crm'
import {
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

interface Stats {
  total: number
  newThisMonth: number
  consentRate: number
  bySource: { source: string; count: number }[]
  birthdayThisMonth: number
  inactive: number
}

function computeStats(customers: CRMCustomer[]): Stats {
  const now = new Date()
  const month = now.getMonth() + 1
  const sourceCounts: Record<string, number> = {}
  let consenting = 0
  let newThisMonth = 0
  let birthdays = 0

  for (const c of customers) {
    sourceCounts[c.source] = (sourceCounts[c.source] || 0) + 1
    if (c.marketing_consent_status === 'given') consenting += 1
    if (c.birthday_month === month) birthdays += 1
    const created = new Date(c.created_at)
    if (created.getMonth() === now.getMonth() && created.getFullYear() === now.getFullYear()) {
      newThisMonth += 1
    }
  }

  const inactiveCutoff = new Date(now.getTime() - 90 * 24 * 3600 * 1000)
  const inactive = customers.filter((c) =>
    !c.last_visit_date || new Date(c.last_visit_date) < inactiveCutoff,
  ).length

  return {
    total: customers.length,
    newThisMonth,
    consentRate: customers.length ? Math.round((consenting / customers.length) * 100) : 0,
    bySource: Object.entries(sourceCounts).map(([source, count]) => ({ source, count })),
    birthdayThisMonth: birthdays,
    inactive,
  }
}

export function CRMDashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      // Pull a representative page of customers for client-side KPIs.
      const data = await crmApi.listCustomers({ organization: orgId })
      setStats(computeStats(data.results))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { refresh() }, [refresh])

  if (loading) return <Loading variant="cards" count={4} />
  if (error) return <ErrorState message={error} onRetry={refresh} />
  if (!stats) return null

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{t('crm.dashboard.title')}</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Kpi icon={Users} label={t('crm.dashboard.totalCustomers')} value={stats.total} />
        <Kpi icon={Users} label={t('crm.dashboard.newThisMonth')} value={stats.newThisMonth} />
        <Kpi icon={ShieldCheck} label={t('crm.dashboard.consentRate')} value={`${stats.consentRate}%`} />
      </div>

      {/* Ready-to-engage cards (loops 4) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() => navigate('/crm/customers')}
          className="text-left"
        >
          <Card className="hover:border-primary transition-colors">
            <CardContent className="py-5 flex items-center gap-4">
              <Cake className="h-8 w-8 text-pink-500" />
              <div>
                <div className="text-2xl font-semibold">{stats.birthdayThisMonth}</div>
                <div className="text-sm text-muted-foreground">{t('crm.dashboard.birthdayThisMonth')}</div>
              </div>
            </CardContent>
          </Card>
        </button>
        <button
          type="button"
          onClick={() => navigate('/crm/customers')}
          className="text-left"
        >
          <Card className="hover:border-primary transition-colors">
            <CardContent className="py-5 flex items-center gap-4">
              <MoonStar className="h-8 w-8 text-slate-500" />
              <div>
                <div className="text-2xl font-semibold">{stats.inactive}</div>
                <div className="text-sm text-muted-foreground">{t('crm.dashboard.inactive')}</div>
              </div>
            </CardContent>
          </Card>
        </button>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">{t('crm.dashboard.bySource')}</CardTitle></CardHeader>
        <CardContent className="h-64">
          {stats.bySource.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">{t('common.noData')}</p>
          ) : (
            <ResponsiveContainer>
              <BarChart data={stats.bySource.map((s) => ({
                ...s, label: t(`crm.source.${s.source as CustomerSource}`, s.source),
              }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366F1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Kpi({ icon: Icon, label, value }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
}) {
  return (
    <Card>
      <CardContent className="py-5 flex items-center gap-4">
        <Icon className="h-8 w-8 text-primary" />
        <div>
          <div className="text-2xl font-semibold">{value}</div>
          <div className="text-sm text-muted-foreground">{label}</div>
        </div>
      </CardContent>
    </Card>
  )
}
