import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, CartesianGrid, PieChart, Pie, Cell,
} from 'recharts'
import { Boxes, AlertTriangle, TrendingDown, Bell, DollarSign } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  inventoryApi,
  type InventoryDashboard, type StockHealthReport,
  type MovementTimeline, type TopConsumed, type StockAlert,
} from '@/services/inventory'

const HEALTH_COLORS: Record<string, string> = {
  critical: '#f97316',
  low: '#fbbf24',
  normal: '#10b981',
  overstock: '#3b82f6',
  negative: '#e11d48',
}

export function InventoryDashboardPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [kpis, setKpis] = useState<InventoryDashboard | null>(null)
  const [health, setHealth] = useState<StockHealthReport | null>(null)
  const [timeline, setTimeline] = useState<MovementTimeline | null>(null)
  const [topOut, setTopOut] = useState<TopConsumed[]>([])
  const [alerts, setAlerts] = useState<StockAlert[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId])

  async function load() {
    if (!orgId) return
    setLoading(true)
    try {
      const [k, h, tl, tc, al] = await Promise.all([
        inventoryApi.dashboard({ organization: orgId }),
        inventoryApi.stockHealth({ organization: orgId }),
        inventoryApi.movementTimeline({ organization: orgId, days: 14 }),
        inventoryApi.topConsumed({ organization: orgId, days: 7 }),
        inventoryApi.listAlerts({ organization: orgId, resolved: false }),
      ])
      setKpis(k); setHealth(h); setTimeline(tl); setTopOut(tc); setAlerts(al.slice(0, 5))
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  async function resolveAlert(id: string) {
    try {
      await inventoryApi.resolveAlert(id)
      void load()
    } catch (e) { toast({ title: t('common.error'), description: String(e), variant: 'destructive' }) }
  }

  const todayInOut = (() => {
    if (!timeline?.series.length) return { in: 0, out: 0 }
    const last = timeline.series[timeline.series.length - 1]
    return { in: Number(last.in), out: Number(last.out) }
  })()

  const healthChartData = health
    ? Object.entries(health.totals).map(([k, v]) => ({ name: k, value: v }))
    : []

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">{t('inventory.dashboard.title')}</h1>
        <p className="text-sm text-slate-500">{t('inventory.dashboard.subtitle')}</p>
      </div>

      {/* KPI cards */}
      <div className="grid gap-3 md:grid-cols-5">
        <KpiCard
          icon={<Boxes className="h-4 w-4" />}
          label={t('inventory.dashboard.totalItems')}
          value={loading ? '…' : kpis?.total_items ?? 0}
        />
        <KpiCard
          icon={<AlertTriangle className="h-4 w-4 text-orange-600" />}
          label={t('inventory.dashboard.lowStock')}
          value={loading ? '…' : kpis?.critical_count ?? 0}
          tone={(kpis?.critical_count ?? 0) > 0 ? 'orange' : undefined}
        />
        <KpiCard
          icon={<Bell className="h-4 w-4 text-rose-600" />}
          label={t('inventory.dashboard.activeAlerts')}
          value={loading ? '…' : kpis?.open_alerts ?? 0}
          tone={(kpis?.open_alerts ?? 0) > 0 ? 'rose' : undefined}
        />
        <KpiCard
          icon={<TrendingDown className="h-4 w-4" />}
          label={t('inventory.dashboard.todayIn')}
          value={loading ? '…' : todayInOut.in}
        />
        <KpiCard
          icon={<DollarSign className="h-4 w-4" />}
          label={t('inventory.dashboard.totalValue')}
          value={loading ? '…' : `$${kpis?.total_inventory_value ?? '0'}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Health pie */}
        <Card>
          <CardContent className="p-4">
            <h3 className="font-semibold mb-2">{t('inventory.dashboard.stockHealth')}</h3>
            <div className="h-64">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={healthChartData} dataKey="value" nameKey="name"
                    cx="50%" cy="50%" outerRadius={90} label>
                    {healthChartData.map(entry => (
                      <Cell key={entry.name} fill={HEALTH_COLORS[entry.name] || '#94a3b8'} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Timeline */}
        <Card>
          <CardContent className="p-4">
            <h3 className="font-semibold mb-2">{t('inventory.dashboard.movementTimeline')}</h3>
            <div className="h-64">
              <ResponsiveContainer>
                <LineChart data={timeline?.series || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="in" stroke="#10b981" name={t('inventory.dashboard.in')} />
                  <Line type="monotone" dataKey="out" stroke="#e11d48" name={t('inventory.dashboard.out')} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Top consumed */}
        <Card>
          <CardContent className="p-4">
            <h3 className="font-semibold mb-2">{t('inventory.dashboard.topConsumed')}</h3>
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={topOut} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="item_name" width={120} tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="consumed" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Recent alerts */}
        <Card>
          <CardContent className="p-4">
            <h3 className="font-semibold mb-2">{t('inventory.dashboard.recentAlerts')}</h3>
            {alerts.length === 0 && (
              <div className="text-sm text-slate-400 py-8 text-center">
                {t('inventory.dashboard.noAlerts')}
              </div>
            )}
            <div className="space-y-2">
              {alerts.map(a => (
                <div key={a.id} className="flex items-start gap-2 p-2 rounded border">
                  <Badge className="bg-orange-100 text-orange-800">{a.alert_type}</Badge>
                  <div className="flex-1 text-sm">
                    <div className="font-medium">{a.item_name}</div>
                    <div className="text-xs text-slate-500">{a.message}</div>
                  </div>
                  <button
                    onClick={() => resolveAlert(a.id)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    {t('inventory.dashboard.resolve')}
                  </button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function KpiCard({
  icon, label, value, tone,
}: { icon: React.ReactNode; label: string; value: React.ReactNode; tone?: 'orange' | 'rose' }) {
  const ring = tone === 'orange' ? 'ring-1 ring-orange-200' : tone === 'rose' ? 'ring-1 ring-rose-200' : ''
  return (
    <Card className={ring}>
      <CardContent className="p-4 space-y-1">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {icon}
          {label}
        </div>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}
