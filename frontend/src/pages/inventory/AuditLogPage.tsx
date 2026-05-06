import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Download } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type AuditLogEntry } from '@/services/inventory'

const ACTION_TONES: Record<string, string> = {
  create: 'bg-emerald-100 text-emerald-800',
  update: 'bg-blue-100 text-blue-800',
  delete: 'bg-rose-100 text-rose-800',
  adjust: 'bg-purple-100 text-purple-800',
  consume: 'bg-amber-100 text-amber-800',
  reverse: 'bg-orange-100 text-orange-800',
  ai_query: 'bg-slate-100 text-slate-700',
  cancel: 'bg-slate-100 text-slate-700',
}

export function AuditLogPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [actionFilter, setActionFilter] = useState<string>('all')
  const [modelFilter, setModelFilter] = useState<string>('all')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!orgId) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, actionFilter, modelFilter, start, end])

  async function load() {
    if (!orgId) return
    setLoading(true)
    try {
      const params: any = { organization: orgId }
      if (actionFilter !== 'all') params.action = actionFilter
      if (modelFilter !== 'all') params.model_name = modelFilter
      if (start) params.start = start
      if (end) params.end = end
      const list = await inventoryApi.listAuditLog(params)
      setEntries(list)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  function toggle(id: string) {
    const next = new Set(expanded)
    next.has(id) ? next.delete(id) : next.add(id)
    setExpanded(next)
  }

  function downloadCsv() {
    const header = ['timestamp', 'action', 'model_name', 'object_repr', 'performed_by_email', 'ip_address']
    const rows = entries.map(e => header.map(h => `"${String((e as any)[h] ?? '').replace(/"/g, '""')}"`).join(','))
    const csv = [header.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `inventory-audit-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t('inventory.audit.title')}</h1>
        <Button variant="outline" onClick={downloadCsv}>
          <Download className="h-4 w-4 mr-1" />
          {t('inventory.audit.download')}
        </Button>
      </div>

      <Card>
        <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="space-y-1">
            <Label>{t('inventory.audit.action')}</Label>
            <Select value={actionFilter} onValueChange={setActionFilter}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('common.all')}</SelectItem>
                {Object.keys(ACTION_TONES).map(k => (
                  <SelectItem key={k} value={k}>{k}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>{t('inventory.audit.model')}</Label>
            <Select value={modelFilter} onValueChange={setModelFilter}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('common.all')}</SelectItem>
                <SelectItem value="InventoryItem">InventoryItem</SelectItem>
                <SelectItem value="Supplier">Supplier</SelectItem>
                <SelectItem value="PurchaseOrder">PurchaseOrder</SelectItem>
                <SelectItem value="Recipe">Recipe</SelectItem>
                <SelectItem value="StockMovement">StockMovement</SelectItem>
                <SelectItem value="InventoryAIEngine">InventoryAIEngine</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>{t('inventory.audit.startDate')}</Label>
            <Input type="datetime-local" value={start} onChange={e => setStart(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>{t('inventory.audit.endDate')}</Label>
            <Input type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="p-3">{t('inventory.audit.time')}</th>
                <th className="p-3">{t('inventory.audit.action')}</th>
                <th className="p-3">{t('inventory.audit.model')}</th>
                <th className="p-3">{t('inventory.audit.object')}</th>
                <th className="p-3">{t('inventory.audit.user')}</th>
                <th className="p-3">{t('inventory.audit.ip')}</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="p-6 text-center text-slate-400">{t('common.loading')}</td></tr>}
              {!loading && entries.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-slate-400">{t('inventory.audit.empty')}</td></tr>
              )}
              {entries.map(e => (
                <>
                  <tr key={e.id} className="border-t cursor-pointer hover:bg-slate-50"
                    onClick={() => toggle(e.id)}>
                    <td className="p-3 font-mono text-xs">{new Date(e.timestamp).toLocaleString()}</td>
                    <td className="p-3">
                      <Badge className={ACTION_TONES[e.action] || 'bg-slate-100 text-slate-700'}>
                        {e.action}
                      </Badge>
                    </td>
                    <td className="p-3 text-xs">{e.model_name}</td>
                    <td className="p-3">{e.object_repr}</td>
                    <td className="p-3 text-xs">{e.performed_by_email || '—'}</td>
                    <td className="p-3 text-xs text-slate-500">{e.ip_address || '—'}</td>
                  </tr>
                  {expanded.has(e.id) && (
                    <tr className="bg-slate-50">
                      <td colSpan={6} className="p-3">
                        <div className="grid grid-cols-2 gap-3 text-xs">
                          <div>
                            <div className="font-semibold mb-1">{t('inventory.audit.before')}</div>
                            <pre className="p-2 bg-white rounded border max-h-48 overflow-y-auto">
                              {JSON.stringify(e.before || {}, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="font-semibold mb-1">{t('inventory.audit.after')}</div>
                            <pre className="p-2 bg-white rounded border max-h-48 overflow-y-auto">
                              {JSON.stringify(e.after || {}, null, 2)}
                            </pre>
                          </div>
                          {e.diff && (
                            <div className="col-span-2">
                              <div className="font-semibold mb-1">{t('inventory.audit.diff')}</div>
                              <pre className="p-2 bg-amber-50 rounded border max-h-48 overflow-y-auto">
                                {JSON.stringify(e.diff, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}
