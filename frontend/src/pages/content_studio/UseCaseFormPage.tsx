import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Sparkles, Palette } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import {
  contentStudioApi, type ContentUseCase, type BrandKit, type UseCaseField,
} from '@/services/content_studio'
import { useCaseIcon } from './icons'

const ASPECTS = ['square', 'portrait', 'landscape'] as const

export function UseCaseFormPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const { useCaseKey } = useParams<{ useCaseKey: string }>()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [useCase, setUseCase] = useState<ContentUseCase | null>(null)
  const [brandKit, setBrandKit] = useState<BrandKit | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [aspect, setAspect] = useState<string>('square')
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    let active = true
    Promise.all([
      contentStudioApi.listUseCases(),
      contentStudioApi.getBrandKit(orgId).catch(() => null),
    ]).then(([cases, kit]) => {
      if (!active) return
      const found = cases.find(c => c.use_case_key === useCaseKey) || null
      setUseCase(found)
      setBrandKit(kit)
      if (found?.supported_formats?.length) setAspect(found.supported_formats[0])
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId, useCaseKey])

  const allFields = useMemo<UseCaseField[]>(
    () => useCase ? [...useCase.required_fields, ...useCase.optional_fields] : [],
    [useCase],
  )

  const set = (key: string, v: unknown) => setValues(prev => ({ ...prev, [key]: v }))

  async function handleGenerate() {
    if (!orgId || !useCase) return
    setSubmitting(true)
    try {
      const job = await contentStudioApi.createJob({
        organization: orgId,
        use_case: useCase.id,
        input_payload: values,
        aspect,
      })
      navigate(`/content-studio/result/${job.id}`)
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data ? JSON.stringify(e.response.data) : String(e),
        variant: 'destructive',
      })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="py-10 text-muted-foreground">{t('common.loading')}</div>
  }
  if (!useCase) {
    return <div className="py-10 text-muted-foreground">{t('contentStudio.useCaseNotFound')}</div>
  }

  const Icon = useCaseIcon(useCase.icon)

  return (
    <div className="space-y-6">
      <Button variant="ghost" className="-ml-2"
        onClick={() => navigate('/content-studio')}>
        <ArrowLeft className="mr-2 h-4 w-4" /> {t('contentStudio.backToGallery')}
      </Button>

      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500/10 to-violet-500/10 ring-1 ring-indigo-500/15">
          <Icon className="h-6 w-6 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">{useCase.display_name}</h1>
          <p className="text-sm text-muted-foreground">{useCase.description}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Form */}
        <Card className="p-6 lg:col-span-2">
          <div className="space-y-5">
            {allFields.map(field => (
              <FieldInput
                key={field.key}
                field={field}
                required={useCase.required_fields.some(f => f.key === field.key)}
                value={values[field.key]}
                onChange={(v) => set(field.key, v)}
              />
            ))}

            <div className="space-y-2">
              <Label>{t('contentStudio.aspect')}</Label>
              <div className="flex gap-2">
                {(useCase.supported_formats.length ? useCase.supported_formats : ASPECTS).map(a => (
                  <Badge
                    key={a}
                    variant={aspect === a ? 'default' : 'outline'}
                    onClick={() => setAspect(a)}
                    className="cursor-pointer"
                  >
                    {t(`contentStudio.aspectType.${a}`)}
                  </Badge>
                ))}
              </div>
            </div>

            <Button
              onClick={handleGenerate}
              disabled={submitting}
              className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {submitting ? t('contentStudio.generating') : t('contentStudio.generate')}
              <span className="ml-2 opacity-80">· {useCase.credit_cost} {t('contentStudio.credits')}</span>
            </Button>
          </div>
        </Card>

        {/* Brand kit preview */}
        <Card className="h-fit p-6">
          <div className="mb-3 flex items-center gap-2">
            <Palette className="h-4 w-4 text-indigo-600" />
            <h3 className="font-semibold">{t('contentStudio.brandContext')}</h3>
          </div>
          {brandKit ? (
            <div className="space-y-3 text-sm text-muted-foreground">
              {brandKit.logo_url && (
                <img src={brandKit.logo_url} alt="logo" className="h-12 rounded border bg-muted object-contain p-1" />
              )}
              <div className="text-foreground">{brandKit.restaurant_name || t('contentStudio.noBrandName')}</div>
              <div className="flex flex-wrap gap-2">
                {brandKit.brand_colors.map(c => (
                  <span key={c} className="h-6 w-6 rounded-full ring-1 ring-border"
                    style={{ backgroundColor: c }} title={c} />
                ))}
              </div>
              {brandKit.default_cta && (
                <div className="text-xs">CTA: “{brandKit.default_cta}”</div>
              )}
              <div className="text-xs">{t('contentStudio.language')}: {brandKit.preferred_language}</div>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              {t('contentStudio.noBrandKit')}{' '}
              <button className="font-medium text-primary underline" onClick={() => navigate('/content-studio/brand-kit')}>
                {t('contentStudio.setUpBrandKit')}
              </button>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function FieldInput({ field, required, value, onChange }: {
  field: UseCaseField
  required: boolean
  value: unknown
  onChange: (v: unknown) => void
}) {
  const label = (
    <Label>
      {field.label}{required && <span className="ml-1 text-destructive">*</span>}
    </Label>
  )
  if (field.type === 'checkbox') {
    return (
      <label className="flex items-start gap-3 rounded-lg border bg-muted/40 p-3">
        <Checkbox checked={!!value} onCheckedChange={(c) => onChange(!!c)} className="mt-0.5" />
        <span className="text-sm text-muted-foreground">{field.label}</span>
      </label>
    )
  }
  if (field.type === 'select') {
    return (
      <div className="space-y-2">
        {label}
        <Select value={(value as string) || ''} onValueChange={onChange}>
          <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
          <SelectContent>
            {(field.choices || []).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
    )
  }
  if (field.type === 'textarea') {
    return (
      <div className="space-y-2">
        {label}
        <Textarea value={(value as string) || ''} maxLength={field.max_length}
          onChange={e => onChange(e.target.value)} />
      </div>
    )
  }
  if (field.type === 'image_upload') {
    // Optional reference image — captured for future provider support; not blocking.
    return (
      <div className="space-y-2">
        {label}
        <Input type="file" accept="image/*" onChange={e => onChange(e.target.files?.[0]?.name || '')} />
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {label}
      <Input
        type={field.type === 'number' ? 'number' : 'text'}
        value={(value as string) || ''}
        maxLength={field.max_length}
        onChange={e => onChange(e.target.value)}
      />
    </div>
  )
}
