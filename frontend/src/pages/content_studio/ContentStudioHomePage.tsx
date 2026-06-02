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
    <div className="min-h-full bg-gradient-to-b from-slate-950 via-slate-900 to-slate-900 p-6 md:p-10">
      {/* Hero */}
      <div className="mx-auto max-w-6xl">
        <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-violet-600/20 via-fuchsia-600/10 to-cyan-500/10 p-8 md:p-12">
          <div className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-fuchsia-500/20 blur-3xl" />
          <div className="absolute -bottom-20 -left-10 h-56 w-56 rounded-full bg-cyan-400/20 blur-3xl" />
          <div className="relative">
            <Badge className="mb-4 border-white/20 bg-white/10 text-white backdrop-blur">
              <Sparkles className="mr-1 h-3 w-3" /> {t('contentStudio.badge')}
            </Badge>
            <h1 className="max-w-2xl text-3xl font-bold leading-tight text-white md:text-5xl">
              {t('contentStudio.tagline')}
            </h1>
            <p className="mt-3 max-w-xl text-base text-slate-300">
              {t('contentStudio.subtitle')}
            </p>
          </div>
        </div>

        {/* Use-case gallery */}
        <div className="mt-10 flex items-center gap-2 text-slate-200">
          <Wand2 className="h-5 w-5 text-fuchsia-400" />
          <h2 className="text-lg font-semibold">{t('contentStudio.chooseUseCase')}</h2>
        </div>

        {loading ? (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-40 animate-pulse rounded-2xl border border-white/10 bg-white/5" />
            ))}
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {useCases.map(uc => {
              const Icon = useCaseIcon(uc.icon)
              return (
                <Card
                  key={uc.id}
                  onClick={() => navigate(`/content-studio/create/${uc.use_case_key}`)}
                  className="group cursor-pointer overflow-hidden border-white/10 bg-white/5 p-5 transition hover:border-fuchsia-400/40 hover:bg-white/[0.08]"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/30 to-fuchsia-500/20 ring-1 ring-white/10">
                      <Icon className="h-6 w-6 text-fuchsia-300" />
                    </div>
                    <Badge className="border-amber-400/30 bg-amber-400/10 text-amber-300">
                      <Coins className="mr-1 h-3 w-3" />
                      {uc.credit_cost} {t('contentStudio.credits')}
                    </Badge>
                  </div>
                  <h3 className="mt-4 font-semibold text-white">{uc.display_name}</h3>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-400">{uc.description || ' '}</p>
                  <div className="mt-4 flex items-center gap-1 text-sm font-medium text-fuchsia-300 opacity-0 transition group-hover:opacity-100">
                    {t('contentStudio.create')} <ArrowRight className="h-4 w-4" />
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
