import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { Plus, Trash2, ArrowLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  luckyDrawApi, LUCKY_DRAW_LANGUAGES, REFERRAL_BONUS_TYPES,
  type LuckyDrawLanguage, type ReferralBonusType, type LuckyDrawPrize,
} from '@/services/lucky_draw'
import {
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

interface PrizeDraft {
  id?: string
  label: string
  discount_percent: string
  weight: string
}

const today = () => new Date().toISOString().slice(0, 10)

export function CampaignFormPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { toast } = useToast()
  const { id } = useParams<{ id: string }>()
  const isEdit = !!id
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [loading, setLoading] = useState(isEdit)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [form, setForm] = useState({
    name: '', description: '', start_date: today(), end_date: '',
    daily_entry_limit_per_customer: 1,
    requires_name: true, requires_phone: true, requires_email: false,
    consent_text: '', privacy_notice_text: '',
    default_language: 'zh-TW' as LuckyDrawLanguage,
    deliver_coupon_via_whatsapp: true,
    referral_enabled: true,
    referral_bonus_type: 'extra_entry' as ReferralBonusType,
    coupon_validity_days: 14,
    tag_redeemers_as_buffet: false,
  })
  const [prizes, setPrizes] = useState<PrizeDraft[]>([
    { label: '', discount_percent: '5', weight: '50' },
  ])

  const load = useCallback(async () => {
    if (!isEdit || !id) return
    setLoading(true)
    setError(null)
    try {
      const c = await luckyDrawApi.getCampaign(id)
      setForm({
        name: c.name, description: c.description, start_date: c.start_date,
        end_date: c.end_date || '',
        daily_entry_limit_per_customer: c.daily_entry_limit_per_customer,
        requires_name: c.requires_name, requires_phone: c.requires_phone,
        requires_email: c.requires_email, consent_text: c.consent_text,
        privacy_notice_text: c.privacy_notice_text, default_language: c.default_language,
        deliver_coupon_via_whatsapp: c.deliver_coupon_via_whatsapp,
        referral_enabled: c.referral_enabled, referral_bonus_type: c.referral_bonus_type,
        coupon_validity_days: c.coupon_validity_days,
        tag_redeemers_as_buffet: c.tag_redeemers_as_buffet,
      })
      setPrizes(
        c.prizes.length
          ? c.prizes.map((p) => ({
              id: p.id, label: p.label,
              discount_percent: String(p.discount_percent), weight: String(p.weight),
            }))
          : [{ label: '', discount_percent: '5', weight: '50' }],
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [id, isEdit])

  useEffect(() => { load() }, [load])

  const totalWeight = prizes.reduce((s, p) => s + (parseInt(p.weight, 10) || 0), 0)

  const setPrize = (i: number, patch: Partial<PrizeDraft>) =>
    setPrizes((prev) => prev.map((p, idx) => (idx === i ? { ...p, ...patch } : p)))
  const addPrize = () =>
    setPrizes((prev) => [...prev, { label: '', discount_percent: '1', weight: '10' }])
  const removePrize = (i: number) =>
    setPrizes((prev) => prev.filter((_, idx) => idx !== i))

  const save = async () => {
    if (!orgId || !form.name.trim() || !form.consent_text.trim()) {
      toast({ title: t('common.error'), description: t('luckyDraw.form.requiredHint'), variant: 'destructive' })
      return
    }
    setSaving(true)
    try {
      const payload = {
        organization: orgId, ...form,
        end_date: form.end_date || null,
      }
      let campaignId = id
      if (isEdit && id) {
        await luckyDrawApi.updateCampaign(id, payload)
      } else {
        const created = await luckyDrawApi.createCampaign(payload)
        campaignId = created.id
      }

      // Sync prizes (create new ones; update existing on edit).
      if (campaignId) {
        for (const p of prizes) {
          const data: Partial<LuckyDrawPrize> = {
            label: p.label,
            discount_percent: p.discount_percent,
            weight: parseInt(p.weight, 10) || 0,
          }
          if (p.id) {
            await luckyDrawApi.updatePrize(p.id, data)
          } else {
            await luckyDrawApi.addPrize(campaignId, data)
          }
        }
      }

      toast({ title: t('common.success') })
      navigate(campaignId ? `/lucky-draw/${campaignId}` : '/lucky-draw')
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Loading variant="rows" />
  if (error) return <ErrorState message={error} onRetry={load} />

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => navigate('/lucky-draw')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-semibold">
          {isEdit ? t('luckyDraw.form.editTitle') : t('luckyDraw.form.createTitle')}
        </h1>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">{t('luckyDraw.form.basics')}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label>{t('luckyDraw.form.name')} *</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <Label>{t('luckyDraw.form.description')}</Label>
            <Textarea value={form.description} rows={2}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>{t('luckyDraw.form.startDate')}</Label>
              <Input type="date" value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </div>
            <div>
              <Label>{t('luckyDraw.form.endDate')}</Label>
              <Input type="date" value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>{t('luckyDraw.form.dailyLimit')}</Label>
              <Input type="number" min={1} value={form.daily_entry_limit_per_customer}
                onChange={(e) => setForm({ ...form, daily_entry_limit_per_customer: parseInt(e.target.value, 10) || 1 })} />
            </div>
            <div>
              <Label>{t('luckyDraw.form.couponValidity')}</Label>
              <Input type="number" min={1} value={form.coupon_validity_days}
                onChange={(e) => setForm({ ...form, coupon_validity_days: parseInt(e.target.value, 10) || 1 })} />
            </div>
          </div>
          <div>
            <Label>{t('luckyDraw.form.language')}</Label>
            <Select value={form.default_language}
              onValueChange={(v) => setForm({ ...form, default_language: v as LuckyDrawLanguage })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {LUCKY_DRAW_LANGUAGES.map((l) => (
                  <SelectItem key={l} value={l}>{t(`luckyDraw.lang.${l}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Required fields + consent */}
      <Card>
        <CardHeader><CardTitle className="text-base">{t('luckyDraw.form.fieldsConsent')}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <ToggleRow label={t('luckyDraw.form.requireName')} checked={form.requires_name}
            onChange={(v) => setForm({ ...form, requires_name: v })} />
          <ToggleRow label={t('luckyDraw.form.requirePhone')} checked={form.requires_phone}
            onChange={(v) => setForm({ ...form, requires_phone: v })} />
          <ToggleRow label={t('luckyDraw.form.requireEmail')} checked={form.requires_email}
            onChange={(v) => setForm({ ...form, requires_email: v })} />
          <div>
            <Label>{t('luckyDraw.form.consentText')} *</Label>
            <Textarea value={form.consent_text} rows={2}
              onChange={(e) => setForm({ ...form, consent_text: e.target.value })} />
          </div>
          <div>
            <Label>{t('luckyDraw.form.privacyText')}</Label>
            <Textarea value={form.privacy_notice_text} rows={2}
              onChange={(e) => setForm({ ...form, privacy_notice_text: e.target.value })} />
          </div>
        </CardContent>
      </Card>

      {/* Loops */}
      <Card>
        <CardHeader><CardTitle className="text-base">{t('luckyDraw.form.deliveryReferral')}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <ToggleRow label={t('luckyDraw.form.deliverWhatsapp')} checked={form.deliver_coupon_via_whatsapp}
            onChange={(v) => setForm({ ...form, deliver_coupon_via_whatsapp: v })} />
          <ToggleRow label={t('luckyDraw.form.enableReferral')} checked={form.referral_enabled}
            onChange={(v) => setForm({ ...form, referral_enabled: v })} />
          {form.referral_enabled && (
            <div>
              <Label>{t('luckyDraw.form.bonusType')}</Label>
              <Select value={form.referral_bonus_type}
                onValueChange={(v) => setForm({ ...form, referral_bonus_type: v as ReferralBonusType })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {REFERRAL_BONUS_TYPES.map((b) => (
                    <SelectItem key={b} value={b}>{t(`luckyDraw.bonusType.${b}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <ToggleRow label={t('luckyDraw.form.tagBuffet')} checked={form.tag_redeemers_as_buffet}
            onChange={(v) => setForm({ ...form, tag_redeemers_as_buffet: v })} />
        </CardContent>
      </Card>

      {/* Prize builder */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{t('luckyDraw.form.prizes')}</CardTitle>
            <Button variant="outline" size="sm" onClick={addPrize}>
              <Plus className="h-4 w-4 mr-1" />{t('luckyDraw.form.addPrize')}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {prizes.map((p, i) => {
            const w = parseInt(p.weight, 10) || 0
            const pct = totalWeight ? Math.round((w / totalWeight) * 100) : 0
            return (
              <div key={i} className="flex items-end gap-2">
                <div className="flex-1">
                  <Label className="text-xs">{t('luckyDraw.form.prizeLabel')}</Label>
                  <Input value={p.label} placeholder={`${p.discount_percent}%`}
                    onChange={(e) => setPrize(i, { label: e.target.value })} />
                </div>
                <div className="w-24">
                  <Label className="text-xs">{t('luckyDraw.form.discount')}</Label>
                  <Input type="number" min={1} max={100} value={p.discount_percent}
                    onChange={(e) => setPrize(i, { discount_percent: e.target.value })} />
                </div>
                <div className="w-24">
                  <Label className="text-xs">{t('luckyDraw.form.weight')}</Label>
                  <Input type="number" min={0} value={p.weight}
                    onChange={(e) => setPrize(i, { weight: e.target.value })} />
                </div>
                <div className="w-16 text-center text-sm text-muted-foreground pb-2">{pct}%</div>
                <Button variant="ghost" size="icon" className="mb-0.5"
                  onClick={() => removePrize(i)} disabled={prizes.length === 1}>
                  <Trash2 className="h-4 w-4 text-rose-500" />
                </Button>
              </div>
            )
          })}
          <p className="text-xs text-muted-foreground">{t('luckyDraw.form.weightHint')}</p>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => navigate('/lucky-draw')}>{t('common.cancel')}</Button>
        <Button onClick={save} disabled={saving}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

function ToggleRow({ label, checked, onChange }: {
  label: string; checked: boolean; onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <Label className="font-normal">{label}</Label>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}
