import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MapPin, Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type InventoryItem } from '@/services/inventory'

export function LocationPricingPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)
  const org = useAuthStore(s => s.currentOrganization)

  const [rows, setRows] = useState<any[]>([])
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState({ item: '', location: '', unit_cost: '', selling_price: '' })

  const locations = (org as any)?.locations || []

  useEffect(() => { if (orgId) void load() }, [orgId])

  async function load() {
    if (!orgId) return
    setLoading(true)
    try {
      const [r, it] = await Promise.all([
        inventoryApi.listLocationPricing(),
        inventoryApi.listItems({ organization: orgId, is_active: true }),
      ])
      setRows((r.results ?? r) as any[])
      setItems(it)
    } finally {
      setLoading(false)
    }
  }

  async function save() {
    if (!draft.item || !draft.location) {
      toast({ title: t('common.error'), description: 'Pick item and location', variant: 'destructive' })
      return
    }
    try {
      await inventoryApi.createLocationPricing({
        item: draft.item, location: draft.location,
        unit_cost: draft.unit_cost || undefined,
        selling_price: draft.selling_price || undefined,
      })
      setOpen(false)
      setDraft({ item: '', location: '', unit_cost: '', selling_price: '' })
      await load()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  async function remove(id: string) {
    await inventoryApi.deleteLocationPricing(id)
    await load()
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <MapPin className="h-6 w-6" />{t('inventory.pricing.title')}
        </h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="h-4 w-4 mr-1" />{t('common.add')}</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>{t('inventory.pricing.add')}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div>
                <Label>{t('common.item')}</Label>
                <Select value={draft.item} onValueChange={v => setDraft(d => ({ ...d, item: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {items.map(i => (
                      <SelectItem key={i.id} value={i.id}>{i.name} ({i.sku})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{t('common.location')}</Label>
                <Select value={draft.location} onValueChange={v => setDraft(d => ({ ...d, location: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {locations.map((l: any) => (
                      <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>{t('inventory.items.unitCost')}</Label>
                  <Input value={draft.unit_cost} onChange={e =>
                    setDraft(d => ({ ...d, unit_cost: e.target.value }))} />
                </div>
                <div>
                  <Label>{t('inventory.items.sellingPrice')}</Label>
                  <Input value={draft.selling_price} onChange={e =>
                    setDraft(d => ({ ...d, selling_price: e.target.value }))} />
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={save}>{t('common.save')}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card><CardContent className="p-0 overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left p-2">{t('common.item')}</th>
              <th className="text-left p-2">{t('common.location')}</th>
              <th className="text-right p-2">{t('inventory.items.unitCost')}</th>
              <th className="text-right p-2">{t('inventory.items.sellingPrice')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="p-4 text-center text-slate-500">{t('common.loading')}</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5} className="p-6 text-center text-slate-500">
                {t('inventory.pricing.empty')}</td></tr>
            ) : rows.map(r => (
              <tr key={r.id} className="border-t">
                <td className="p-2">{r.item_name}</td>
                <td className="p-2">{r.location_name}</td>
                <td className="p-2 text-right tabular-nums">{r.unit_cost ?? '—'}</td>
                <td className="p-2 text-right tabular-nums">{r.selling_price ?? '—'}</td>
                <td className="p-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => remove(r.id)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent></Card>
    </div>
  )
}
