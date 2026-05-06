import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  CartesianGrid,
} from 'recharts'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi } from '@/services/inventory'
import { StockDisplay } from '@/components/inventory/StockDisplay'

export function InventoryReportsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [perCat, setPerCat] = useState<any[]>([])
  const [variance, setVariance] = useState<any[]>([])
  const [days, setDays] = useState(14)
  const [timelineData, setTimelineData] = useState<any[]>([])

  useEffect(() => {
    if (!orgId) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, days])

  async function load() {
    if (!orgId) return
    try {
      const [h, v, t] = await Promise.all([
        inventoryApi.stockHealth({ organization: orgId }),
        inventoryApi.variance({ organization: orgId }),
        inventoryApi.movementTimeline({ organization: orgId, days }),
      ])
      setPerCat(h.per_category)
      setVariance(v)
      setTimelineData(t.series)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold">{t('inventory.reports.title')}</h1>

      <Tabs defaultValue="stock">
        <TabsList>
          <TabsTrigger value="stock">{t('inventory.reports.stock')}</TabsTrigger>
          <TabsTrigger value="movement">{t('inventory.reports.movement')}</TabsTrigger>
          <TabsTrigger value="variance">{t('inventory.reports.variance')}</TabsTrigger>
        </TabsList>

        <TabsContent value="stock">
          <Card>
            <CardContent className="p-4">
              <h3 className="font-semibold mb-2">{t('inventory.reports.byCategory')}</h3>
              <div className="h-80">
                <ResponsiveContainer>
                  <BarChart data={perCat}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="category" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="critical" stackId="a" fill="#f97316" />
                    <Bar dataKey="low" stackId="a" fill="#fbbf24" />
                    <Bar dataKey="normal" stackId="a" fill="#10b981" />
                    <Bar dataKey="overstock" stackId="a" fill="#3b82f6" />
                    <Bar dataKey="negative" stackId="a" fill="#e11d48" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="movement">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3 mb-3">
                <Label>{t('inventory.reports.days')}</Label>
                <Input
                  type="number" min="1" max="180"
                  value={days}
                  onChange={e => setDays(Number(e.target.value) || 14)}
                  className="w-24"
                />
              </div>
              <div className="h-80">
                <ResponsiveContainer>
                  <BarChart data={timelineData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="in" fill="#10b981" />
                    <Bar dataKey="out" fill="#e11d48" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="variance">
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="p-3 text-left">{t('inventory.reports.item')}</th>
                    <th className="p-3 text-left">SKU</th>
                    <th className="p-3 text-right">{t('inventory.reports.reported')}</th>
                    <th className="p-3 text-right">{t('inventory.reports.range')}</th>
                    <th className="p-3 text-right">{t('inventory.reports.reorder')}</th>
                    <th className="p-3 text-left">{t('inventory.reports.status_')}</th>
                  </tr>
                </thead>
                <tbody>
                  {variance.length === 0 && (
                    <tr><td colSpan={6} className="p-6 text-center text-slate-400">
                      {t('inventory.reports.varianceEmpty')}
                    </td></tr>
                  )}
                  {variance.map(v => (
                    <tr key={v.item_id} className="border-t">
                      <td className="p-3">{v.item_name}</td>
                      <td className="p-3 font-mono text-xs">{v.sku}</td>
                      <td className="p-3 text-right">
                        <StockDisplay
                          reported={v.reported}
                          raw={v.reported}
                          lowerBound={v.lower_bound}
                          upperBound={v.upper_bound}
                          tolerancePercent="0"
                          unit={v.unit}
                          isCritical={v.is_critical}
                          isNegative={v.is_negative}
                        />
                      </td>
                      <td className="p-3 text-right text-xs">{v.lower_bound} – {v.upper_bound}</td>
                      <td className="p-3 text-right">{v.reorder_level}</td>
                      <td className="p-3">
                        {v.is_negative ? <Badge className="bg-rose-100 text-rose-800">negative</Badge>
                          : <Badge className="bg-orange-100 text-orange-800">critical</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
