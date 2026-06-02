import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Sparkles, Coins, ArrowRight, Wand2 } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { contentStudioApi, type ContentUseCase } from '@/services/content_studio'
import { useCaseIcon } from './icons'

export function ContentStudioHomePage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [useCases, setUseCases] = useState<ContentUseCase[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    contentStudioApi.listUseCases()
      .then(rows => { if (active) setUseCases(rows) })
      .catch(e => toast({ title: t('common.error'), description: String(e), variant: 'destructive' }))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId, t, toast])

  return (
    <div className="space-y-6">
      {/* Hero — light, soft brand gradient; keeps an "AI studio" feel without
          going dark. Uses the app's indigo/violet accents on a white surface. */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-indigo-50 via-violet-50 to-sky-50 p-8 md:p-10">
        <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-violet-200/40 blur-3xl" />
        <div className="absolute -bottom-20 -left-10 h-48 w-48 rounded-full bg-sky-200/40 blur-3xl" />
        <div className="relative">
          <Badge variant="secondary" className="mb-4 bg-white/70 text-indigo-700 backdrop-blur">
            <Sparkles className="mr-1 h-3 w-3" /> {t('contentStudio.badge')}
          </Badge>
          <h1 className="max-w-2xl text-3xl font-bold leading-tight text-foreground md:text-4xl">
            {t('contentStudio.tagline')}
          </h1>
          <p className="mt-3 max-w-xl text-base text-muted-foreground">
            {t('contentStudio.subtitle')}
          </p>
        </div>
      </div>

      {/* Use-case gallery */}
      <div className="flex items-center gap-2">
        <Wand2 className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-semibold">{t('contentStudio.chooseUseCase')}</h2>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl border bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {useCases.map(uc => {
            const Icon = useCaseIcon(uc.icon)
            return (
              <Card
                key={uc.id}
                onClick={() => navigate(`/content-studio/create/${uc.use_case_key}`)}
                className="group cursor-pointer p-5 transition-colors hover:border-primary"
              >
                <div className="flex items-start justify-between">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500/10 to-violet-500/10 ring-1 ring-indigo-500/15">
                    <Icon className="h-6 w-6 text-indigo-600" />
                  </div>
                  <Badge variant="secondary" className="bg-amber-50 text-amber-700">
                    <Coins className="mr-1 h-3 w-3" />
                    {uc.credit_cost} {t('contentStudio.credits')}
                  </Badge>
                </div>
                <h3 className="mt-4 font-semibold text-foreground">{uc.display_name}</h3>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{uc.description || ' '}</p>
                <div className="mt-4 flex items-center gap-1 text-sm font-medium text-primary opacity-0 transition group-hover:opacity-100">
                  {t('contentStudio.create')} <ArrowRight className="h-4 w-4" />
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
