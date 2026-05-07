import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, X, Check, Send, Download } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  inventoryApi,
  type PurchaseOrder, type Supplier, type InventoryItem, type POStatus,
} from '@/services/inventory'

const STATUS_BADGE: Record<POStatus, string> = {
  draft: 'bg-slate-100 text-slate-700',
  sent: 'bg-blue-100 text-blue-800',
  partial: 'bg-amber-100 text-amber-800',
  received: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-rose-100 text-rose-800',
}

interface DraftLine {
  item: string
  quantity_ordered: string
  unit_cost: string
  notes: string
}

const emptyLine: DraftLine = {
  item: '', quantity_ordered: '0', unit_cost: '0', notes: '',
}

export function PurchaseOrdersPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<POStatus | 'all'>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [supplierId, setSupplierId] = useState('')
  const [notes, setNotes] = useState('')
  const [expectedDate, setExpectedDate] = useState('')
  const [lines, setLines] = useState<DraftLine[]>([{ ...emptyLine }])

  const [receiveOpen, setReceiveOpen] = useState<PurchaseOrder | null>(null)

  useEffect(() => {
    if (!orgId) return
    void load()
    void loadCatalog()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, statusFilter])

  async function load() {
    if (!orgId) return
    setLoading(true)
    try {
      const params: { organization: string; status?: POStatus } = { organization: orgId }
      if (statusFilter !== 'all') params.status = statusFilter
      const list = await inventoryApi.listPurchaseOrders(params)
      setOrders(list)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  async function loadCatalog() {
    if (!orgId) return
    const [s, i] = await Promise.all([
      inventoryApi.listSuppliers({ organization: orgId }),
      inventoryApi.listItems({ organization: orgId, is_active: true }),
    ])
    setSuppliers(s)
    setItems(i)
  }

  function resetForm() {
    setSupplierId('')
    setNotes('')
    setExpectedDate('')
    setLines([{ ...emptyLine }])
  }

  async function handleCreate() {
    if (!orgId || !supplierId) {
      toast({ title: t('inventory.po.supplierRequired'), variant: 'destructive' })
      return
    }
    const validLines = lines.filter(l => l.item && Number(l.quantity_ordered) > 0)
    if (validLines.length === 0) {
      toast({ title: t('inventory.po.linesRequired'), variant: 'destructive' })
      return
    }
    try {
      await inventoryApi.createPurchaseOrder({
        organization: orgId,
        supplier: supplierId,
        notes,
        expected_date: expectedDate || null,
        items: validLines.map(l => ({
          item: l.item,
          quantity_ordered: l.quantity_ordered,
          unit_cost: l.unit_cost,
          notes: l.notes,
        })),
      })
      toast({ title: t('inventory.po.created') })
      setCreateOpen(false)
      resetForm()
      void load()
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data ? JSON.stringify(e.response.data) : String(e),
        variant: 'destructive',
      })
    }
  }

  async function handleCancel(po: PurchaseOrder) {
    if (!confirm(t('inventory.po.confirmCancel'))) return
    try {
      await inventoryApi.cancelPurchaseOrder(po.id)
      toast({ title: t('inventory.po.cancelled') })
      void load()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('inventory.po.title')}</h1>
          <p className="text-sm text-slate-500">{t('inventory.po.subtitle')}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t('inventory.po.create')}
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <Label>{t('inventory.po.statusFilter')}</Label>
        <Select value={statusFilter} onValueChange={(v: POStatus | 'all') => setStatusFilter(v)}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.all')}</SelectItem>
            <SelectItem value="draft">{t('inventory.po.status.draft')}</SelectItem>
            <SelectItem value="sent">{t('inventory.po.status.sent')}</SelectItem>
            <SelectItem value="partial">{t('inventory.po.status.partial')}</SelectItem>
            <SelectItem value="received">{t('inventory.po.status.received')}</SelectItem>
            <SelectItem value="cancelled">{t('inventory.po.status.cancelled')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="p-3">{t('inventory.po.number')}</th>
                <th className="p-3">{t('inventory.po.supplier')}</th>
                <th className="p-3">{t('inventory.po.status_')}</th>
                <th className="p-3">{t('inventory.po.orderDate')}</th>
                <th className="p-3">{t('inventory.po.expected')}</th>
                <th className="p-3">{t('inventory.po.total')}</th>
                <th className="p-3">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} className="p-6 text-center text-slate-400">{t('common.loading')}</td></tr>
              )}
              {!loading && orders.length === 0 && (
                <tr><td colSpan={7} className="p-6 text-center text-slate-400">{t('inventory.po.empty')}</td></tr>
              )}
              {orders.map(po => (
                <tr key={po.id} className="border-t">
                  <td className="p-3 font-mono text-xs">{po.order_number}</td>
                  <td className="p-3">{po.supplier_name}</td>
                  <td className="p-3">
                    <Badge className={STATUS_BADGE[po.status]}>{po.status}</Badge>
                  </td>
                  <td className="p-3">{po.order_date}</td>
                  <td className="p-3">{po.expected_date || '—'}</td>
                  <td className="p-3 font-medium">${po.total_amount}</td>
                  <td className="p-3">
                    <div className="flex gap-1">
                      {(po.status === 'draft' || po.status === 'sent' || po.status === 'partial') && (
                        <Button size="sm" variant="outline" onClick={() => setReceiveOpen(po)}>
                          <Check className="h-3 w-3 mr-1" />
                          {t('inventory.po.receive')}
                        </Button>
                      )}
                      {po.status === 'draft' && (
                        <Button size="sm" variant="outline" onClick={async () => {
                          try {
                            await inventoryApi.sendPurchaseOrder(po.id)
                            toast({ title: t('inventory.po.sent') })
                            await load()
                          } catch (e: any) {
                            toast({
                              title: t('common.error'),
                              description: e?.response?.data?.detail || String(e),
                              variant: 'destructive',
                            })
                          }
                        }}>
                          <Send className="h-3 w-3 mr-1" />
                          {t('inventory.po.send')}
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={async () => {
                        const blob = await inventoryApi.downloadPoPdf(po.id)
                        const url = URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = `${po.order_number}.pdf`
                        a.click()
                        URL.revokeObjectURL(url)
                      }}>
                        <Download className="h-3 w-3" />
                      </Button>
                      {(po.status === 'draft' || po.status === 'sent' || po.status === 'partial') && (
                        <Button size="sm" variant="ghost" onClick={() => handleCancel(po)}>
                          <X className="h-3 w-3 mr-1" />
                          {t('common.cancel')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Create PO dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>{t('inventory.po.create')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>{t('inventory.po.supplier')}</Label>
                <Select value={supplierId} onValueChange={setSupplierId}>
                  <SelectTrigger><SelectValue placeholder={t('inventory.po.selectSupplier')} /></SelectTrigger>
                  <SelectContent>
                    {suppliers.map(s => (
                      <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{t('inventory.po.expected')}</Label>
                <Input type="date" value={expectedDate} onChange={e => setExpectedDate(e.target.value)} />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{t('inventory.po.lines')}</Label>
                <Button size="sm" variant="outline" onClick={() => setLines([...lines, { ...emptyLine }])}>
                  <Plus className="h-3 w-3 mr-1" />
                  {t('inventory.po.addLine')}
                </Button>
              </div>
              {lines.map((line, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-5">
                    <Select
                      value={line.item}
                      onValueChange={v => {
                        const next = [...lines]
                        next[i] = { ...next[i], item: v }
                        const item = items.find(it => it.id === v)
                        if (item && next[i].unit_cost === '0') next[i].unit_cost = item.unit_cost
                        setLines(next)
                      }}
                    >
                      <SelectTrigger><SelectValue placeholder={t('inventory.po.selectItem')} /></SelectTrigger>
                      <SelectContent>
                        {items.map(it => (
                          <SelectItem key={it.id} value={it.id}>{it.name} ({it.unit})</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number" step="0.01" placeholder="qty"
                      value={line.quantity_ordered}
                      onChange={e => {
                        const next = [...lines]
                        next[i] = { ...next[i], quantity_ordered: e.target.value }
                        setLines(next)
                      }}
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number" step="0.0001" placeholder="unit cost"
                      value={line.unit_cost}
                      onChange={e => {
                        const next = [...lines]
                        next[i] = { ...next[i], unit_cost: e.target.value }
                        setLines(next)
                      }}
                    />
                  </div>
                  <div className="col-span-1">
                    <Button
                      size="icon" variant="ghost"
                      onClick={() => setLines(lines.filter((_, j) => j !== i))}
                      disabled={lines.length === 1}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            <div className="space-y-1">
              <Label>{t('common.notes')}</Label>
              <Textarea value={notes} onChange={e => setNotes(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleCreate}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Receive dialog */}
      {receiveOpen && (
        <ReceiveDialog
          po={receiveOpen}
          onClose={() => setReceiveOpen(null)}
          onReceived={() => { setReceiveOpen(null); void load() }}
        />
      )}
    </div>
  )
}

function ReceiveDialog({
  po, onClose, onReceived,
}: { po: PurchaseOrder; onClose: () => void; onReceived: () => void }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [quantities, setQuantities] = useState<Record<string, string>>({})

  async function handleReceiveLine(lineId: string) {
    const qty = quantities[lineId]
    if (!qty || Number(qty) <= 0) {
      toast({ title: t('inventory.po.qtyRequired'), variant: 'destructive' })
      return
    }
    try {
      await inventoryApi.receivePurchaseOrder(po.id, {
        line_id: lineId,
        quantity_received: qty,
      })
      toast({ title: t('inventory.po.received') })
      onReceived()
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data?.detail || String(e),
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>{t('inventory.po.receivePO', { num: po.order_number })}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {po.items.map(line => {
            const remaining = Number(line.quantity_ordered) - Number(line.quantity_received)
            return (
              <div key={line.id} className="grid grid-cols-12 gap-2 items-end p-2 border rounded">
                <div className="col-span-5">
                  <div className="text-sm font-medium">{line.item_name}</div>
                  <div className="text-xs text-slate-500">
                    {t('inventory.po.ordered')}: {line.quantity_ordered} · {t('inventory.po.received')}: {line.quantity_received}
                  </div>
                </div>
                <div className="col-span-4">
                  <Input
                    type="number" step="0.01"
                    placeholder={String(remaining)}
                    value={quantities[line.id] || ''}
                    onChange={e => setQuantities({ ...quantities, [line.id]: e.target.value })}
                    disabled={remaining <= 0}
                  />
                </div>
                <div className="col-span-3">
                  <Button
                    size="sm"
                    onClick={() => handleReceiveLine(line.id)}
                    disabled={remaining <= 0}
                  >
                    {t('inventory.po.receive')}
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>{t('common.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
