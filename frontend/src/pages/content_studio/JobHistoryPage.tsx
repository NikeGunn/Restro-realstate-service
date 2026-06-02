import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { History, ImageOff } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { contentStudioApi, type GenerationJob } from '@/services/content_studio'
import { StatusBadge } from './GenerationResultPage'

export function JobHistoryPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [jobs, setJobs] = useState<GenerationJob[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    let active = true
    contentStudioApi.listJobs({ organization: orgId })
      .then(rows => { if (active) setJobs(rows) })
      .catch(e => toast({ title: t('common.error'), description: String(e), variant: 'destructive' }))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId, t, toast])

  return (
    <div className="min-h-full bg-gradient-to-b from-slate-950 to-slate-900 p-6 md:p-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex items-center gap-2 text-white">
          <History className="h-6 w-6 text-fuchsia-300" />
          <h1 className="text-2xl font-bold">{t('contentStudio.history')}</h1>
        </div>

        {loading ? (
          <div className="text-slate-400">{t('common.loading')}</div>
        ) : jobs.length === 0 ? (
          <Card className="flex flex-col items-center gap-3 border-white/10 bg-white/5 py-16 text-slate-400">
            <ImageOff className="h-8 w-8" />
            {t('contentStudio.noJobs')}
          </Card>
        ) : (
          <div className="space-y-3">
            {jobs.map(job => {
              const thumb = job.outputs?.[0]?.thumbnail_url
              return (
                <Card
                  key={job.id}
                  onClick={() => navigate(`/content-studio/result/${job.id}`)}
                  className="flex cursor-pointer items-center gap-4 border-white/10 bg-white/5 p-3 transition hover:bg-white/[0.08]"
                >
                  <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-slate-800">
                    {thumb
                      ? <img src={thumb} alt="" className="h-full w-full object-cover" />
                      : <div className="flex h-full w-full items-center justify-center text-slate-600"><ImageOff className="h-5 w-5" /></div>}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-white">{job.use_case_name}</div>
                    <div className="text-xs text-slate-400">
                      {new Date(job.created_at).toLocaleString()} · {job.output_count} {t('contentStudio.images')}
                    </div>
                  </div>
                  <StatusBadge status={job.status} />
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
