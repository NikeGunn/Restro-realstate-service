import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TrendingUp, Users, ChefHat, Trash2, Sparkles } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi } from '@/services/inventory'

export function Phase5ReportsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [forecast, setForecast] = useState<any>(null)
  const [scorecards, setScorecards] = useState<any[]>([])
  const [profit, setProfit] = useState<any[]>([])
  const [waste, setWaste] = useState<any>(null)
  const [insight, setInsight] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { if (orgId) void load() }, [orgId])

  async function load() {
    if (!orgId) return
    setLoading(true)
    try {
      const [f, s, p, w, i] = await Promise.all([
        inventoryApi.reorderForecast({ organization: orgId, days: 30 }),
        inventoryApi.supplierScorecards({ organization: orgId }),
        inventoryApi.recipeProfitability({ organization: orgId }),
        inventoryApi.wasteAnalysis({ organization: orgId, days: 30 }),
        inventoryApi.weeklyInsights({ organization: orgId }).catch(() => null),
      ])
      setForecast(f); setScorecards(s); setProfit(p); setWaste(w); setInsight(i)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-6 text-slate-500">{t('common.loading')}</div>

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold">{t('inventory.analytics.title')}</h1>

      {insight && (
        <Card className="border-violet-200 bg-violet-50">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-violet-600" />
              {t('inventory.analytics.weeklyInsight')}
              <Badge variant="outline">conf {Math.round((insight.confidence || 0) * 100)}%</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="whitespace-pre-wrap text-sm">{insight.answer}</CardContent>
        </Card>
      )}

      <Tabs defaultValue="forecast">
        <TabsList>
          <TabsTrigger value="forecast"><TrendingUp className="h-4 w-4 mr-1" />
            {t('inventory.analytics.forecast')}</TabsTrigger>
          <TabsTrigger value="suppliers"><Users className="h-4 w-4 mr-1" />
            {t('inventory.analytics.suppliers')}</TabsTrigger>
          <TabsTrigger value="profit"><ChefHat className="h-4 w-4 mr-1" />
            {t('inventory.analytics.profit')}</TabsTrigger>
          <TabsTrigger value="waste"><Trash2 className="h-4 w-4 mr-1" />
            {t('inventory.analytics.waste')}</TabsTrigger>
        </TabsList>

        <TabsContent value="forecast">
          <Card><CardContent className="p-0 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left p-2">{t('common.item')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.currentStock')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.avgPerDay')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.daysCover')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.reorder')}</th>
                </tr>
              </thead>
              <tbody>
                {forecast?.rows?.map((r: any) => (
                  <tr key={r.item_id} className="border-t">
                    <td className="p-2">
                      <div>{r.item_name}</div>
                      <div className="text-xs text-slate-500">{r.sku}</div>
                    </td>
                    <td className="p-2 text-right tabular-nums">{r.current_stock} {r.unit}</td>
                    <td className="p-2 text-right tabular-nums">{r.avg_daily_consumption}</td>
                    <td className="p-2 text-right tabular-nums">
                      {r.days_of_cover ?? '—'}
                    </td>
                    <td className="p-2 text-right">
                      {r.recommended_to_reorder
                        ? <Badge className="bg-amber-100 text-amber-800">⚠ {t('inventory.analytics.reorderNow')}</Badge>
                        : <span className="text-slate-400">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="suppliers">
          <Card><CardContent className="p-0 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left p-2">{t('inventory.po.supplier')}</th>
                  <th className="text-right p-2">PO</th>
                  <th className="text-right p-2">{t('inventory.analytics.leadTime')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.accuracy')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.spend')}</th>
                </tr>
              </thead>
              <tbody>
                {scorecards.map(s => (
                  <tr key={s.supplier_id} className="border-t">
                    <td className="p-2">{s.supplier_name}</td>
                    <td className="p-2 text-right">{s.po_count}</td>
                    <td className="p-2 text-right tabular-nums">
                      {s.avg_lead_time_days ?? '—'}
                    </td>
                    <td className="p-2 text-right tabular-nums">
                      {s.receive_accuracy_percent !== null ? `${s.receive_accuracy_percent}%` : '—'}
                    </td>
                    <td className="p-2 text-right tabular-nums">{s.total_spend}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="profit">
          <Card><CardContent className="p-0 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left p-2">{t('inventory.recipes.name')}</th>
                  <th className="text-left p-2">{t('inventory.recipes.outputItem')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.cost')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.sellingPrice')}</th>
                  <th className="text-right p-2">{t('inventory.analytics.margin')}</th>
                </tr>
              </thead>
              <tbody>
                {profit.map(r => (
                  <tr key={r.recipe_id} className="border-t">
                    <td className="p-2">{r.recipe_name}</td>
                    <td className="p-2">{r.output_item}</td>
                    <td className="p-2 text-right tabular-nums">{r.cost_per_unit}</td>
                    <td className="p-2 text-right tabular-nums">{r.selling_price}</td>
                    <td className="p-2 text-right tabular-nums">
                      {r.margin_per_unit}{' '}
                      {r.margin_percent !== null && (
                        <span className="text-xs text-slate-500">({r.margin_percent}%)</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="waste">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('inventory.analytics.topWastedItems')}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left p-2">{t('common.item')}</th>
                      <th className="text-right p-2">{t('inventory.analytics.wasted')}</th>
                      <th className="text-right p-2">{t('inventory.analytics.events')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waste?.top_items?.map((w: any) => (
                      <tr key={w.item_id} className="border-t">
                        <td className="p-2">{w.item_name}</td>
                        <td className="p-2 text-right tabular-nums">{w.wasted} {w.unit}</td>
                        <td className="p-2 text-right">{w.event_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('inventory.analytics.byWeek')}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left p-2">{t('inventory.analytics.week')}</th>
                      <th className="text-right p-2">{t('inventory.analytics.wasted')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waste?.by_week?.map((w: any) => (
                      <tr key={w.week} className="border-t">
                        <td className="p-2">{w.week}</td>
                        <td className="p-2 text-right tabular-nums">{w.wasted}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
