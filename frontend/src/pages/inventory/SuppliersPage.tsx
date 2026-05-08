import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Edit, Trash2, Truck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type Supplier } from '@/services/inventory'
import {
  InventoryEmpty, InventoryError, InventoryLoading,
} from '@/components/inventory/InventoryStates'

const TERMS: Supplier['payment_terms'][] = ['cod', 'net7', 'net15', 'net30', 'net60']

const empty = {
  name: '', contact_name: '', email: '', phone: '', address: '',
  tax_id: '', payment_terms: 'cod' as Supplier['payment_terms'],
  notes: '', is_active: true,
}

export function SuppliersPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Supplier | null>(null)
  const [form, setForm] = useState(empty)

  const refresh = async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      setSuppliers(await inventoryApi.listSuppliers({ organization: orgId }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() /* eslint-disable-line */ }, [orgId])

  const startCreate = () => { setEditing(null); setForm(empty); setOpen(true) }
  const startEdit = (s: Supplier) => {
    setEditing(s)
    setForm({
      name: s.name, contact_name: s.contact_name, email: s.email, phone: s.phone,
      address: s.address, tax_id: s.tax_id, payment_terms: s.payment_terms,
      notes: s.notes, is_active: s.is_active,
    })
    setOpen(true)
  }

  const submit = async () => {
    if (!orgId || !form.name.trim()) return
    try {
      const payload = { organization: orgId, ...form }
      if (editing) await inventoryApi.updateSupplier(editing.id, payload)
      else await inventoryApi.createSupplier(payload)
      setOpen(false)
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

  const remove = async (s: Supplier) => {
    if (!confirm(t('inventory.supplierForm.deleteConfirm', { name: s.name }))) return
    try {
      await inventoryApi.deleteSupplier(s.id)
      await refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t('inventory.suppliers')}</h1>
          <p className="text-muted-foreground">{t('inventory.subtitle')}</p>
        </div>
        <Button onClick={startCreate}>
          <Plus className="h-4 w-4 mr-2" />
          {t('inventory.addSupplier')}
        </Button>
      </div>

      {error ? (
        <InventoryError message={error} onRetry={refresh} />
      ) : loading ? (
        <InventoryLoading variant="cards" />
      ) : suppliers.length === 0 ? (
        <InventoryEmpty icon={Truck} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {suppliers.map((s) => (
            <Card key={s.id}>
              <CardContent className="py-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{s.name}</div>
                    {s.contact_name && (
                      <div className="text-sm text-muted-foreground">{s.contact_name}</div>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <Button size="icon" variant="ghost" onClick={() => startEdit(s)}>
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button size="icon" variant="ghost" onClick={() => remove(s)}>
                      <Trash2 className="h-4 w-4 text-rose-600" />
                    </Button>
                  </div>
                </div>
                <div className="mt-3 space-y-1 text-sm text-muted-foreground">
                  {s.phone && <div>📞 {s.phone}</div>}
                  {s.email && <div>✉️ {s.email}</div>}
                  <div>{t('inventory.supplierForm.terms')}: <span className="font-mono">{s.payment_terms}</span></div>
                  <div>{t('inventory.supplierForm.items')}: {s.item_count}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {editing ? t('common.edit') : t('inventory.addSupplier')}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <Label>{t('inventory.fields.name')}</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.supplierForm.contact')}</Label>
              <Input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.supplierForm.email')}</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.supplierForm.phone')}</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.supplierForm.taxId')}</Label>
              <Input value={form.tax_id} onChange={(e) => setForm({ ...form, tax_id: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <Label>{t('inventory.supplierForm.address')}</Label>
              <Textarea rows={2} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </div>
            <div>
              <Label>{t('inventory.supplierForm.paymentTerms')}</Label>
              <Select value={form.payment_terms} onValueChange={(v) => setForm({ ...form, payment_terms: v as Supplier['payment_terms'] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TERMS.map((tr) => <SelectItem key={tr} value={tr}>{tr}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2 pt-6">
              <Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} />
              <Label>{t('inventory.fields.isActive')}</Label>
            </div>
            <div className="sm:col-span-2">
              <Label>{t('inventory.supplierForm.notes')}</Label>
              <Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={submit}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
