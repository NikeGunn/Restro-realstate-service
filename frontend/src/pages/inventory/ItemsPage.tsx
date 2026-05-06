import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Plus, Search, AlertTriangle, TrendingDown, Boxes, DollarSign,
  Edit, Trash2, Wrench,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  inventoryApi, type InventoryItem, type Supplier, type InventoryCategory,
  type InventoryDashboard, type Unit, type StockStatus,
} from '@/services/inventory'

const UNITS: Unit[] = ['kg', 'g', 'liter', 'ml', 'piece', 'box', 'bag', 'dozen', 'pack']

const STATUS_BADGE: Record<StockStatus, string> = {
  ok: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  low: 'bg-amber-100 text-amber-800 border-amber-200',
  critical: 'bg-orange-100 text-orange-800 border-orange-200',
  negative: 'bg-rose-100 text-rose-800 border-rose-200',
}

const emptyForm = {
  name: '',
  description: '',
  category: '',
  unit: 'kg' as Unit,
  unit_cost: '0',
  selling_price: '',
  reorder_level: '0',
  reorder_quantity: '0',
  tolerance_percent: '0.5',
  is_perishable: false,
  expiry_days: '',
  supplier: '',
  barcode: '',
  is_active: true,
}

export function ItemsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [items, setItems] = useState<InventoryItem[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [categories, setCategories] = useState<InventoryCategory[]>([])
  const [dashboard, setDashboard] = useState<InventoryDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'critical' | 'negative'>('all')

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<InventoryItem | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)

  const [adjustOpen, setAdjustOpen] = useState(false)
  const [adjustItem, setAdjustItem] = useState<InventoryItem | null>(null)
  const [adjustForm, setAdjustForm] = useState({ quantity: '', reason: '' })

  const refresh = async () => {
    if (!orgId) return
    setLoading(true)
    try {
      const [itemsRes, supRes, catRes, dashRes] = await Promise.all([
        inventoryApi.listItems({ organization: orgId }),
        inventoryApi.listSuppliers({ organization: orgId }),
        inventoryApi.listCategories({ organization: orgId }),
        inventoryApi.dashboard({ organization: orgId }),
      ])
      setItems(itemsRes)
      setSuppliers(supRes)
      setCategories(catRes)
      setDashboard(dashRes)
    } catch (e: unknown) {
      console.error(e)
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId])

  const filtered = useMemo(() => {
    let list = items
    if (search.trim()) {
      const term = search.toLowerCase()
      list = list.filter(
        i =>
          i.name.toLowerCase().includes(term) ||
          i.sku.toLowerCase().includes(term) ||
          (i.barcode || '').toLowerCase().includes(term),
      )
    }
    if (statusFilter !== 'all') {
      list = list.filter(i => i.stock_status === statusFilter)
    }
    return list
  }, [items, search, statusFilter])

  const openCreate = () => {
    setEditing(null)
    setForm(emptyForm)
    setFormOpen(true)
  }

  const openEdit = (item: InventoryItem) => {
    setEditing(item)
    setForm({
      name: item.name,
      description: item.description,
      category: item.category || '',
      unit: item.unit,
      unit_cost: item.unit_cost,
      selling_price: item.selling_price || '',
      reorder_level: item.reorder_level,
      reorder_quantity: item.reorder_quantity,
      tolerance_percent: item.tolerance_percent,
      is_perishable: item.is_perishable,
      expiry_days: item.expiry_days?.toString() || '',
      supplier: item.supplier || '',
      barcode: item.barcode || '',
      is_active: item.is_active,
    })
    setFormOpen(true)
  }

  const submit = async () => {
    if (!orgId) return
    if (!form.name.trim()) {
      toast({ title: t('common.error'), description: 'Name required', variant: 'destructive' })
      return
    }
    setSaving(true)
    try {
      const payload = {
        organization: orgId,
        name: form.name.trim(),
        description: form.description,
        category: form.category || null,
        unit: form.unit,
        unit_cost: form.unit_cost || '0',
        selling_price: form.selling_price || null,
        reorder_level: form.reorder_level || '0',
        reorder_quantity: form.reorder_quantity || '0',
        tolerance_percent: form.tolerance_percent || '0',
        is_perishable: form.is_perishable,
        expiry_days: form.expiry_days ? parseInt(form.expiry_days, 10) : null,
        supplier: form.supplier || null,
        barcode: form.barcode || null,
        is_active: form.is_active,
      }
      if (editing) {
        // Cannot change unit on update — strip it.
        const { unit: _unit, ...rest } = payload
        await inventoryApi.updateItem(editing.id, rest)
      } else {
        await inventoryApi.createItem(payload)
      }
      toast({ title: t('inventory.saved') })
      setFormOpen(false)
      await refresh()
    } catch (e: unknown) {
      const err = e as { response?: { data?: unknown } }
      toast({
        title: t('inventory.saveFailed'),
        description: JSON.stringify(err?.response?.data || e),
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  const remove = async (item: InventoryItem) => {
    if (!confirm(t('inventory.deleteConfirm'))) return
    try {
      await inventoryApi.deleteItem(item.id)
      await refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  const openAdjust = (item: InventoryItem) => {
    setAdjustItem(item)
    setAdjustForm({ quantity: '', reason: '' })
    setAdjustOpen(true)
  }

  const submitAdjust = async () => {
    if (!adjustItem) return
    if (adjustForm.reason.trim().length < 5) {
      toast({
        title: t('common.error'),
        description: 'Reason must be at least 5 characters.',
        variant: 'destructive',
      })
      return
    }
    try {
      await inventoryApi.adjustStock(adjustItem.id, {
        quantity: adjustForm.quantity,
        reason: adjustForm.reason,
      })
      setAdjustOpen(false)
      await refresh()
    } catch (e) {
      const err = e as { response?: { data?: unknown } }
      toast({
        title: t('inventory.saveFailed'),
        description: JSON.stringify(err?.response?.data || e),
        variant: 'destructive',
      })
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t('inventory.title')}</h1>
          <p className="text-muted-foreground">{t('inventory.subtitle')}</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4 mr-2" />
          {t('inventory.addItem')}
        </Button>
      </div>

      {/* Dashboard cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <DashCard
          icon={<Boxes className="h-5 w-5" />}
          label={t('inventory.totalItems')}
          value={dashboard?.total_items ?? '—'}
        />
        <DashCard
          icon={<AlertTriangle className="h-5 w-5 text-orange-600" />}
          label={t('inventory.criticalCount')}
          value={dashboard?.critical_count ?? '—'}
          tone={dashboard && dashboard.critical_count > 0 ? 'warn' : undefined}
        />
        <DashCard
          icon={<TrendingDown className="h-5 w-5 text-rose-600" />}
          label={t('inventory.negativeCount')}
          value={dashboard?.negative_count ?? '—'}
          tone={dashboard && dashboard.negative_count > 0 ? 'danger' : undefined}
        />
        <DashCard
          icon={<DollarSign className="h-5 w-5" />}
          label={t('inventory.totalValue')}
          value={dashboard?.total_inventory_value ?? '—'}
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t('inventory.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.all')}</SelectItem>
            <SelectItem value="critical">{t('inventory.stockStatus.critical')}</SelectItem>
            <SelectItem value="negative">{t('inventory.stockStatus.negative')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* List */}
      {loading ? (
        <p className="text-muted-foreground">{t('common.loading')}</p>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            {items.length === 0 ? t('inventory.empty') : t('common.noData')}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/30 border-b">
                  <tr className="text-left">
                    <th className="px-4 py-3">{t('inventory.fields.sku')}</th>
                    <th className="px-4 py-3">{t('inventory.fields.name')}</th>
                    <th className="px-4 py-3">{t('inventory.fields.category')}</th>
                    <th className="px-4 py-3 text-right">{t('inventory.fields.currentStock')}</th>
                    <th className="px-4 py-3 text-right">{t('inventory.fields.reorderLevel')}</th>
                    <th className="px-4 py-3">{t('common.status')}</th>
                    <th className="px-4 py-3 text-right">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr key={item.id} className="border-b last:border-0 hover:bg-muted/20">
                      <td className="px-4 py-3 font-mono text-xs">{item.sku}</td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{item.name}</div>
                        {item.supplier_name && (
                          <div className="text-xs text-muted-foreground">{item.supplier_name}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {item.category_name || '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {item.effective_stock.reported} {item.unit}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-muted-foreground">
                        {Number(item.reorder_level).toFixed(2)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="outline" className={STATUS_BADGE[item.stock_status]}>
                          {t(`inventory.stockStatus.${item.stock_status}`)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <Button size="icon" variant="ghost" onClick={() => openAdjust(item)} title={t('inventory.adjustStock')}>
                            <Wrench className="h-4 w-4" />
                          </Button>
                          <Button size="icon" variant="ghost" onClick={() => openEdit(item)}>
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button size="icon" variant="ghost" onClick={() => remove(item)}>
                            <Trash2 className="h-4 w-4 text-rose-600" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Item dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editing ? t('common.edit') : t('inventory.addItem')}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <Label>{t('inventory.fields.name')}</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.fields.unit')}</Label>
              <Select
                value={form.unit}
                onValueChange={(v) => setForm({ ...form, unit: v as Unit })}
                disabled={!!editing}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {UNITS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                </SelectContent>
              </Select>
              {editing && (
                <p className="text-xs text-muted-foreground mt-1">
                  Unit is locked after creation.
                </p>
              )}
            </div>
            <div>
              <Label>{t('inventory.fields.category')}</Label>
              <Select value={form.category || 'none'} onValueChange={(v) => setForm({ ...form, category: v === 'none' ? '' : v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('inventory.fields.unitCost')}</Label>
              <Input type="number" step="0.0001" value={form.unit_cost} onChange={(e) => setForm({ ...form, unit_cost: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.fields.sellingPrice')}</Label>
              <Input type="number" step="0.0001" value={form.selling_price} onChange={(e) => setForm({ ...form, selling_price: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.fields.reorderLevel')}</Label>
              <Input type="number" step="0.0001" value={form.reorder_level} onChange={(e) => setForm({ ...form, reorder_level: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.fields.reorderQuantity')}</Label>
              <Input type="number" step="0.0001" value={form.reorder_quantity} onChange={(e) => setForm({ ...form, reorder_quantity: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.fields.tolerance')}</Label>
              <Input type="number" step="0.01" min="0" max="5" value={form.tolerance_percent} onChange={(e) => setForm({ ...form, tolerance_percent: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.fields.supplier')}</Label>
              <Select value={form.supplier || 'none'} onValueChange={(v) => setForm({ ...form, supplier: v === 'none' ? '' : v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {suppliers.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('inventory.fields.barcode')}</Label>
              <Input value={form.barcode} onChange={(e) => setForm({ ...form, barcode: e.target.value })} />
            </div>
            <div className="flex items-center gap-2 pt-6">
              <Switch checked={form.is_perishable} onCheckedChange={(v) => setForm({ ...form, is_perishable: v })} />
              <Label>{t('inventory.fields.isPerishable')}</Label>
            </div>
            {form.is_perishable && (
              <div>
                <Label>{t('inventory.fields.expiryDays')}</Label>
                <Input type="number" value={form.expiry_days} onChange={(e) => setForm({ ...form, expiry_days: e.target.value })} />
              </div>
            )}
            <div className="sm:col-span-2">
              <Label>{t('inventory.fields.description')}</Label>
              <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} />
              <Label>{t('inventory.fields.isActive')}</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={submit} disabled={saving}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Adjust dialog */}
      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('inventory.adjustStock')} — {adjustItem?.name}
            </DialogTitle>
          </DialogHeader>
          {adjustItem && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {t('inventory.fields.currentStock')}:{' '}
                <span className="font-mono">{adjustItem.current_stock} {adjustItem.unit}</span>
              </p>
              <div>
                <Label>{t('inventory.adjustForm.quantity')}</Label>
                <Input
                  type="number"
                  step="0.0001"
                  value={adjustForm.quantity}
                  onChange={(e) => setAdjustForm({ ...adjustForm, quantity: e.target.value })}
                  placeholder="-5 or 10"
                />
              </div>
              <div>
                <Label>{t('inventory.adjustForm.reason')}</Label>
                <Textarea
                  rows={3}
                  value={adjustForm.reason}
                  onChange={(e) => setAdjustForm({ ...adjustForm, reason: e.target.value })}
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={submitAdjust}>{t('inventory.adjustForm.submit')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function DashCard({
  icon, label, value, tone,
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  tone?: 'warn' | 'danger'
}) {
  const ring =
    tone === 'danger' ? 'border-rose-200 bg-rose-50/40'
    : tone === 'warn' ? 'border-orange-200 bg-orange-50/40'
    : ''
  return (
    <Card className={ring}>
      <CardContent className="py-4 flex items-center gap-3">
        <div className="rounded-md bg-muted p-2">{icon}</div>
        <div>
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="text-xl font-semibold">{value}</div>
        </div>
      </CardContent>
    </Card>
  )
}
