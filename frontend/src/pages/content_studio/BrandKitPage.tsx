import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Palette, Upload, Plus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { contentStudioApi, type BrandKit } from '@/services/content_studio'
import { PlanGate, isPlanGateError } from '@/components/PlanGate'
import { parseColor, toPickerHex } from '@/lib/color'

const LANGS = ['zh-TW', 'zh-CN', 'en']
const WATERMARKS = ['none', 'logo', 'text'] as const

export function BrandKitPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)
  const fileRef = useRef<HTMLInputElement>(null)

  const [kit, setKit] = useState<BrandKit | null>(null)
  const [form, setForm] = useState({
    restaurant_name: '', preferred_language: 'zh-TW', default_cta: '',
    phone: '', whatsapp: '', address: '', website_url: '',
    watermark_preference: 'none' as BrandKit['watermark_preference'],
  })
  const [colors, setColors] = useState<string[]>([])
  const [colorInput, setColorInput] = useState('')
  const [swatch, setSwatch] = useState('#E11D48')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [planBlocked, setPlanBlocked] = useState(false)

  // Live parse of whatever the user typed/pasted — null while invalid.
  const parsedInput = colorInput.trim() ? parseColor(colorInput) : null

  useEffect(() => {
    if (!orgId) return
    let active = true
    contentStudioApi.getBrandKit(orgId).then(k => {
      if (!active) return
      setKit(k)
      if (k) {
        setForm({
          restaurant_name: k.restaurant_name, preferred_language: k.preferred_language,
          default_cta: k.default_cta, phone: k.phone, whatsapp: k.whatsapp,
          address: k.address, website_url: k.website_url,
          watermark_preference: k.watermark_preference,
        })
        setColors(k.brand_colors || [])
      }
    }).catch(e => {
      if (active && isPlanGateError(e)) setPlanBlocked(true)
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId])

  function addColor(raw: string) {
    if (colors.length >= 5) return
    const hex = parseColor(raw)
    if (!hex) {
      toast({ title: t('contentStudio.invalidColor'), variant: 'destructive' })
      return
    }
    if (!colors.includes(hex)) setColors([...colors, hex])
    setColorInput('')
  }

  async function save() {
    if (!orgId) return
    setSaving(true)
    try {
      const payload = { ...form, brand_colors: colors }
      const saved = kit
        ? await contentStudioApi.updateBrandKit(kit.id, payload)
        : await contentStudioApi.createBrandKit({ organization: orgId, ...payload })
      setKit(saved)
      toast({ title: t('contentStudio.brandKitSaved') })
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data ? JSON.stringify(e.response.data) : String(e),
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  async function uploadLogo(file: File) {
    if (!kit) {
      toast({ title: t('contentStudio.saveKitFirst'), variant: 'destructive' })
      return
    }
    const saved = await contentStudioApi.uploadLogo(kit.id, file)
    setKit(saved)
    toast({ title: t('contentStudio.logoUploaded') })
  }

  if (planBlocked) return <PlanGate feature={t('contentStudio.title')} />
  if (loading) return <div className="py-10 text-muted-foreground">{t('common.loading')}</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Palette className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-semibold">{t('contentStudio.brandKit')}</h1>
      </div>

      <Card className="max-w-3xl space-y-6 p-6">
        {/* Logo */}
        <div className="flex items-center gap-4">
          <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl border bg-muted">
            {kit?.logo_url
              ? <img src={kit.logo_url} alt="logo" className="h-full w-full object-contain p-1" />
              : <Palette className="h-7 w-7 text-muted-foreground" />}
          </div>
          <div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden"
              onChange={e => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
            <Button variant="outline" onClick={() => fileRef.current?.click()}>
              <Upload className="mr-2 h-4 w-4" /> {t('contentStudio.uploadLogo')}
            </Button>
          </div>
        </div>

        <Field label={t('contentStudio.restaurantName')}>
          <Input value={form.restaurant_name}
            onChange={e => setForm({ ...form, restaurant_name: e.target.value })} />
        </Field>

        {/* Colors — paste any format (hex, rgb, hsl, name) from any tool */}
        <div className="space-y-2">
          <Label>{t('contentStudio.brandColors')}</Label>

          {colors.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {colors.map(c => (
                <button
                  key={c}
                  type="button"
                  onClick={() => { navigator.clipboard?.writeText(c); toast({ title: t('contentStudio.colorCopied', { color: c }) }) }}
                  className="group flex items-center gap-1.5 rounded-full border bg-muted py-1 pl-1 pr-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted/70"
                  title={t('contentStudio.clickToCopy')}
                >
                  <span className="h-5 w-5 rounded-full ring-1 ring-border" style={{ backgroundColor: c }} />
                  <span className="tabular-nums">{c}</span>
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(e) => { e.stopPropagation(); setColors(colors.filter(x => x !== c)) }}
                    className="ml-0.5 rounded-full p-0.5 text-muted-foreground hover:bg-background hover:text-destructive"
                  >
                    <X className="h-3 w-3" />
                  </span>
                </button>
              ))}
            </div>
          )}

          {colors.length < 5 ? (
            <div className="flex items-center gap-2">
              {/* Native swatch — picks a color, the input reflects it live */}
              <label
                className="relative h-9 w-9 shrink-0 cursor-pointer overflow-hidden rounded-md border ring-1 ring-border"
                style={{ backgroundColor: parsedInput || swatch }}
                title={t('contentStudio.pickSwatch')}
              >
                <input
                  type="color"
                  value={parsedInput ? toPickerHex(parsedInput) : swatch}
                  onChange={e => { setSwatch(e.target.value); setColorInput(e.target.value) }}
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                />
              </label>

              {/* Paste-anything input: hex / rgb / hsl / name */}
              <div className="relative flex-1">
                <Input
                  value={colorInput}
                  placeholder={t('contentStudio.colorPlaceholder')}
                  spellCheck={false}
                  onChange={e => setColorInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addColor(colorInput) } }}
                  className={
                    colorInput && !parsedInput
                      ? 'border-destructive pr-9 focus-visible:ring-destructive'
                      : 'pr-9'
                  }
                />
                {parsedInput && (
                  <span
                    className="pointer-events-none absolute right-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full ring-1 ring-border"
                    style={{ backgroundColor: parsedInput }}
                  />
                )}
              </div>

              <Button
                type="button"
                variant="outline"
                disabled={!parsedInput}
                onClick={() => addColor(colorInput)}
              >
                <Plus className="mr-1 h-4 w-4" /> {t('contentStudio.addColor')}
              </Button>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{t('contentStudio.colorLimitReached')}</p>
          )}

          <p className="text-xs text-muted-foreground">{t('contentStudio.colorHint')}</p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t('contentStudio.language')}>
            <Select value={form.preferred_language}
              onValueChange={v => setForm({ ...form, preferred_language: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {LANGS.map(l => <SelectItem key={l} value={l}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label={t('contentStudio.watermark')}>
            <Select value={form.watermark_preference}
              onValueChange={v => setForm({ ...form, watermark_preference: v as BrandKit['watermark_preference'] })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {WATERMARKS.map(w => (
                  <SelectItem key={w} value={w}>{t(`contentStudio.watermarkType.${w}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label={t('contentStudio.defaultCta')}>
            <Input value={form.default_cta} onChange={e => setForm({ ...form, default_cta: e.target.value })} />
          </Field>
          <Field label={t('contentStudio.phone')}>
            <Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <Field label={t('contentStudio.whatsapp')}>
            <Input value={form.whatsapp} onChange={e => setForm({ ...form, whatsapp: e.target.value })} />
          </Field>
          <Field label={t('contentStudio.website')}>
            <Input value={form.website_url} onChange={e => setForm({ ...form, website_url: e.target.value })} />
          </Field>
        </div>
        <Field label={t('contentStudio.address')}>
          <Input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} />
        </Field>

        <Button onClick={save} disabled={saving}
          className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500">
          {saving ? t('common.loading') : t('common.save')}
        </Button>
      </Card>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  )
}
