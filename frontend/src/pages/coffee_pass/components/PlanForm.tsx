import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Coffee, AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'

import { locationsApi, restaurantApi } from '@/services/api'
import { coffeePassApi, type CoffeePassPlan } from '@/services/coffeePass'
import { useAuthStore } from '@/store/auth'

interface Location { id: string; name: string }
interface MenuItem { id: string; name: string; price: string; item_type?: string }

const DEFAULTS = {
  name: 'Coffee Pass — 30 days',
  description: '',
  price_hkd: '120.00',
  discount_percent: '30.00',
  duration_days: 30,
}

export function PlanFormDialog({
  open, plan, onOpenChange, onSaved,
}: {
  open: boolean
  plan: CoffeePassPlan | null
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [locations, setLocations] = useState<Location[]>([])
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])
  const [form, setForm] = useState({ ...DEFAULTS, location: '' })
  const [selectedItems, setSelectedItems] = useState<string[]>([])
  const [allowNeutral, setAllowNeutral] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)
  const [saving, setSaving] = useState(false)

  // Load the pickers once per open. Locations and drink items are the two
  // things an owner needs to configure a plan.
  useEffect(() => {
    if (!open || !orgId) return
    let cancelled = false

    const load = async () => {
      try {
        const [locs, items] = await Promise.all([
          locationsApi.list(orgId),
          restaurantApi.items.list({ organization: orgId }),
        ])
        if (cancelled) return
        setLocations(locs as Location[])
        // Coffee Pass is a DRINK product — offering food items would make the
        // break-even promise meaningless.
        const drinks = (items as MenuItem[]).filter(
          (i) => !i.item_type || ['drink', 'cocktail', 'alcohol'].includes(i.item_type),
        )
        setMenuItems(drinks.length > 0 ? drinks : (items as MenuItem[]))
      } catch {
        if (!cancelled) toast({ title: t('coffeePass.plans.loadFailed'),
          variant: 'destructive' })
      }
    }
    load()
    return () => { cancelled = true }
  }, [open, orgId, t, toast])

  // Sync the form when the dialog opens for a specific plan (or a new one).
  useEffect(() => {
    if (!open) return
    if (plan) {
      setForm({
        name: plan.name,
        description: plan.description,
        price_hkd: plan.price_hkd,
        discount_percent: plan.discount_percent,
        duration_days: plan.duration_days,
        location: plan.location,
      })
      setSelectedItems(plan.eligible_items ?? [])
      setAllowNeutral(plan.allow_neutral_feedback)
      setAcknowledged(plan.break_even_acknowledged)
    } else {
      setForm({ ...DEFAULTS, location: '' })
      setSelectedItems([])
      setAllowNeutral(false)
      setAcknowledged(false)
    }
  }, [open, plan])

  // Live break-even mirrors the server formula so the owner sees the honest
  // number BEFORE saving. The server recomputes it authoritatively on activate.
  const breakEven = useMemo(() => {
    const chosen = menuItems.filter((i) => selectedItems.includes(i.id))
    const prices = chosen
      .map((i) => parseFloat(i.price))
      .filter((p) => Number.isFinite(p) && p > 0)
    if (prices.length === 0) return null

    const price = parseFloat(form.price_hkd)
    const pct = parseFloat(form.discount_percent)
    if (!Number.isFinite(price) || !Number.isFinite(pct) || price <= 0 || pct <= 0) {
      return null
    }
    const average = prices.reduce((a, b) => a + b, 0) / prices.length
    const savingPerVisit = (average * pct) / 100
    if (savingPerVisit <= 0) return null

    return {
      average: average.toFixed(2),
      savingPerVisit: savingPerVisit.toFixed(2),
      visits: Math.ceil(price / savingPerVisit),
    }
  }, [menuItems, selectedItems, form.price_hkd, form.discount_percent])

  const tooExpensive = breakEven !== null && breakEven.visits > 20

  const toggleItem = useCallback((id: string) => {
    setSelectedItems((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const handleSave = async () => {
    if (!orgId || !form.location) {
      toast({ title: t('coffeePass.plans.locationRequired'), variant: 'destructive' })
      return
    }
    setSaving(true)
    try {
      const payload = {
        organization: orgId,
        location: form.location,
        name: form.name,
        description: form.description,
        price_hkd: form.price_hkd,
        discount_percent: form.discount_percent,
        duration_days: Number(form.duration_days),
        eligible_items: selectedItems,
        allow_neutral_feedback: allowNeutral,
        break_even_acknowledged: acknowledged,
      }
      if (plan) {
        await coffeePassApi.updatePlan(plan.id, payload)
      } else {
        await coffeePassApi.createPlan(payload)
      }
      toast({ title: t('coffeePass.plans.saved') })
      onOpenChange(false)
      onSaved()
    } catch (e) {
      const data = (e as { response?: { data?: Record<string, unknown> } }).response?.data
      toast({
        title: t('coffeePass.plans.saveFailed'),
        description: data ? Object.values(data).flat().join(' ') : undefined,
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {plan ? t('coffeePass.plans.editTitle') : t('coffeePass.plans.createTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <Label htmlFor="cp-name">{t('coffeePass.plans.name')}</Label>
              <Input
                id="cp-name" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>

            <div>
              <Label htmlFor="cp-location">{t('coffeePass.plans.location')}</Label>
              <Select
                value={form.location}
                onValueChange={(v) => setForm({ ...form, location: v })}
              >
                <SelectTrigger id="cp-location">
                  <SelectValue placeholder={t('coffeePass.plans.selectLocation')} />
                </SelectTrigger>
                <SelectContent>
                  {locations.map((l) => (
                    <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                {t('coffeePass.plans.locationHint')}
              </p>
            </div>

            <div>
              <Label htmlFor="cp-price">{t('coffeePass.plans.price')}</Label>
              <Input
                id="cp-price" type="number" min="0" step="0.01" value={form.price_hkd}
                onChange={(e) => setForm({ ...form, price_hkd: e.target.value })}
              />
            </div>

            <div>
              <Label htmlFor="cp-discount">{t('coffeePass.plans.discount')}</Label>
              <Input
                id="cp-discount" type="number" min="0.01" max="50" step="0.01"
                value={form.discount_percent}
                onChange={(e) => setForm({ ...form, discount_percent: e.target.value })}
              />
              <p className="text-xs text-muted-foreground mt-1">
                {t('coffeePass.plans.discountHint')}
              </p>
            </div>

            <div>
              <Label htmlFor="cp-duration">{t('coffeePass.plans.duration')}</Label>
              <Input
                id="cp-duration" type="number" min="1" value={form.duration_days}
                onChange={(e) => setForm({
                  ...form, duration_days: Number(e.target.value),
                })}
              />
            </div>

            <div className="sm:col-span-2">
              <Label htmlFor="cp-desc">{t('coffeePass.plans.description')}</Label>
              <Textarea
                id="cp-desc" rows={2} value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
          </div>

          {/* Eligible items — required before the plan may activate. */}
          <div>
            <Label>{t('coffeePass.plans.eligibleItems')}</Label>
            <p className="text-xs text-muted-foreground mb-2">
              {t('coffeePass.plans.eligibleItemsHint')}
            </p>
            <div className="max-h-48 overflow-y-auto border rounded-md divide-y">
              {menuItems.length === 0 ? (
                <p className="p-3 text-sm text-muted-foreground">
                  {t('coffeePass.plans.noMenuItems')}
                </p>
              ) : menuItems.map((item) => (
                <label
                  key={item.id}
                  className="flex items-center gap-3 p-2.5 hover:bg-muted/50 cursor-pointer"
                >
                  <Checkbox
                    checked={selectedItems.includes(item.id)}
                    onCheckedChange={() => toggleItem(item.id)}
                  />
                  <Coffee className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="text-sm flex-1 truncate">{item.name}</span>
                  <span className="text-sm text-muted-foreground tabular-nums">
                    HK${item.price}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* The value guardrail, shown live as the owner types. */}
          {breakEven && (
            <div className={`rounded-md px-3 py-2.5 text-sm ${
              tooExpensive
                ? 'bg-amber-50 border border-amber-200 text-amber-900'
                : 'bg-emerald-50 border border-emerald-200 text-emerald-900'
            }`}>
              <div className="flex items-start gap-2">
                {tooExpensive && <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />}
                <div>
                  <p>
                    {t('coffeePass.plans.breakEven', {
                      price: breakEven.average, visits: breakEven.visits,
                    })}
                  </p>
                  {tooExpensive && (
                    <p className="mt-1 text-xs">{t('coffeePass.plans.breakEvenWarning')}</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* An owner may knowingly proceed past the guardrail — it's a warning,
              not a prohibition — but the acknowledgement is stored. */}
          {tooExpensive && (
            <label className="flex items-center gap-3 text-sm">
              <Checkbox
                checked={acknowledged}
                onCheckedChange={(v) => setAcknowledged(Boolean(v))}
              />
              {t('coffeePass.plans.acknowledgeBreakEven')}
            </label>
          )}

          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <Label htmlFor="cp-neutral">{t('coffeePass.plans.allowNeutral')}</Label>
              <p className="text-xs text-muted-foreground">
                {t('coffeePass.plans.allowNeutralHint')}
              </p>
            </div>
            <Switch id="cp-neutral" checked={allowNeutral} onCheckedChange={setAllowNeutral} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
