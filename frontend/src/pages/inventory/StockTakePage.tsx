import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ClipboardList, Plus, Check, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type InventoryItem } from '@/services/inventory'

interface DraftLine {
  item: string
  item_name: string
  unit: string
  system_count: string
  counted: string
}

export function StockTakePage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [takes, setTakes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [items, setItems] = useState<InventoryItem[]>([])
  const [draft, setDraft] = useState<{ name: string; notes: string; lines: DraftLine[] }>({
    name: '', notes: '', lines: [],
  })

  useEffect(() => { if (orgId) void load() }, [orgId])

  async function load() {
    if (!orgId) return
    setLoading(true)
    try {
      const [takesRes, itemsRes] = await Promise.all([
        inventoryApi.listStockTakes({ organization: orgId }),
        inventoryApi.listItems({ organization: orgId, is_active: true }),
      ])
      const list = (takesRes.results ?? takesRes) as any[]
      setTakes(list)
      setItems(itemsRes)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  function addAllItemsToDraft() {
    setDraft(d => ({
      ...d,
      lines: items.map(i => ({
        item: i.id, item_name: i.name, unit: i.unit,
        system_count: i.current_stock, counted: i.current_stock,
      })),
    }))
  }

  async function createTake() {
    if (!orgId) return
    if (draft.lines.length === 0) {
      toast({ title: t('inventory.stockTake.noLines'), variant: 'destructive' })
      return
    }
    try {
      await inventoryApi.createStockTake({
        organization: orgId,
        name: draft.name,
        notes: draft.notes,
        lines: draft.lines.map(l => ({
          item: l.item, system_count: l.system_count, counted: l.counted,
        })),
      })
      toast({ title: t('inventory.stockTake.created') })
      setDialogOpen(false)
      setDraft({ name: '', notes: '', lines: [] })
      await load()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  async function commitTake(id: string) {
    try {
      const res = await inventoryApi.commitStockTake(id)
      toast({
        title: t('inventory.stockTake.committed'),
        description: `${res.result.adjustments_created} adjustments`,
      })
      await load()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  async function cancelTake(id: string) {
    try {
      await inventoryApi.cancelStockTake(id)
      await load()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <ClipboardList className="h-6 w-6" />
          {t('inventory.stockTake.title')}
        </h1>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="mr-1 h-4 w-4" />{t('inventory.stockTake.new')}</Button>
          </DialogTrigger>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>{t('inventory.stockTake.new')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <Label>{t('common.name')}</Label>
                <Input value={draft.name}
                  onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} />
              </div>
              <div>
                <Label>{t('common.notes')}</Label>
                <Input value={draft.notes}
                  onChange={e => setDraft(d => ({ ...d, notes: e.target.value }))} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {t('inventory.stockTake.lines')} ({draft.lines.length})
                </span>
                <Button size="sm" variant="outline" onClick={addAllItemsToDraft}>
                  {t('inventory.stockTake.addAllItems')}
                </Button>
              </div>
              <div className="max-h-72 overflow-auto border rounded">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left p-2">{t('common.item')}</th>
                      <th className="text-right p-2">{t('inventory.stockTake.system')}</th>
                      <th className="text-right p-2">{t('inventory.stockTake.counted')}</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {draft.lines.map((l, i) => (
                      <tr key={l.item} className="border-t">
                        <td className="p-2">{l.item_name} <span className="text-slate-400">({l.unit})</span></td>
                        <td className="p-2 text-right tabular-nums">{l.system_count}</td>
                        <td className="p-2 text-right">
                          <Input
                            className="w-24 text-right tabular-nums"
                            type="number" step="0.0001"
                            value={l.counted}
                            onChange={e => {
                              const v = e.target.value
                              setDraft(d => ({
                                ...d,
                                lines: d.lines.map((x, idx) =>
                                  idx === i ? { ...x, counted: v } : x),
                              }))
                            }}
                          />
                        </td>
                        <td className="p-2">
                          <Button size="sm" variant="ghost" onClick={() =>
                            setDraft(d => ({ ...d, lines: d.lines.filter((_, idx) => idx !== i) }))
                          }><X className="h-3 w-3" /></Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex justify-end">
                <Button onClick={createTake}>{t('common.create')}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="text-slate-500">{t('common.loading')}</div>
      ) : takes.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-slate-500">
          {t('inventory.stockTake.empty')}
        </CardContent></Card>
      ) : (
        <div className="grid gap-4">
          {takes.map(st => (
            <Card key={st.id}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-base">
                  {st.name || `Stock-take ${st.id.slice(0, 8)}`}{' '}
                  <Badge variant="outline">{st.status}</Badge>
                </CardTitle>
                {st.status === 'in_progress' && (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => commitTake(st.id)}>
                      <Check className="h-4 w-4 mr-1" />{t('common.commit')}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => cancelTake(st.id)}>
                      {t('common.cancel')}
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent className="text-sm text-slate-600">
                <div>{t('inventory.stockTake.lines')}: {st.lines?.length || 0}</div>
                {st.committed_at && <div>{t('inventory.stockTake.committedAt')}: {st.committed_at}</div>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
