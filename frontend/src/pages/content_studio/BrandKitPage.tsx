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
  const [newColor, setNewColor] = useState('#E11D48')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

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
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId])

  function addColor() {
    if (colors.length >= 5 || !newColor) return
    if (!colors.includes(newColor)) setColors([...colors, newColor])
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

  if (loading) return <div className="p-10 text-slate-400">{t('common.loading')}</div>

  return (
    <div className="min-h-full bg-gradient-to-b from-slate-950 to-slate-900 p-6 md:p-10">
      <div className="mx-auto max-w-3xl">
        <div className="mb-6 flex items-center gap-2 text-white">
          <Palette className="h-6 w-6 text-fuchsia-300" />
          <h1 className="text-2xl font-bold">{t('contentStudio.brandKit')}</h1>
        </div>

        <Card className="space-y-6 border-white/10 bg-white/5 p-6">
          {/* Logo */}
          <div className="flex items-center gap-4">
            <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl bg-white/10 ring-1 ring-white/10">
              {kit?.logo_url
                ? <img src={kit.logo_url} alt="logo" className="h-full w-full object-contain p-1" />
                : <Palette className="h-7 w-7 text-slate-500" />}
            </div>
            <div>
              <input ref={fileRef} type="file" accept="image/*" className="hidden"
                onChange={e => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
              <Button variant="outline" className="border-white/20 text-slate-200"
                onClick={() => fileRef.current?.click()}>
                <Upload className="mr-2 h-4 w-4" /> {t('contentStudio.uploadLogo')}
              </Button>
            </div>
          </div>

          <Field label={t('contentStudio.restaurantName')}>
            <Input value={form.restaurant_name}
              onChange={e => setForm({ ...form, restaurant_name: e.target.value })} />
          </Field>

          {/* Colors */}
          <div className="space-y-2">
            <Label className="text-slate-200">{t('contentStudio.brandColors')}</Label>
            <div className="flex flex-wrap items-center gap-2">
              {colors.map(c => (
                <span key={c} className="flex items-center gap-1 rounded-full bg-white/10 py-1 pl-1 pr-2 text-xs text-slate-200">
                  <span className="h-5 w-5 rounded-full ring-1 ring-white/20" style={{ backgroundColor: c }} />
                  {c}
                  <button onClick={() => setColors(colors.filter(x => x !== c))}>
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
              {colors.length < 5 && (
                <div className="flex items-center gap-1">
                  <input type="color" value={newColor} onChange={e => setNewColor(e.target.value)}
                    className="h-8 w-8 cursor-pointer rounded bg-transparent" />
                  <Button size="icon" variant="outline" className="border-white/20" onClick={addColor}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
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
            className="bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white">
            {saving ? t('common.loading') : t('common.save')}
          </Button>
        </Card>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label className="text-slate-200">{label}</Label>
      {children}
    </div>
  )
}
