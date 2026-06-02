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
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <History className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-semibold">{t('contentStudio.history')}</h1>
      </div>

      {loading ? (
        <div className="text-muted-foreground">{t('common.loading')}</div>
      ) : jobs.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
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
                className="flex cursor-pointer items-center gap-4 p-3 transition-colors hover:border-primary"
              >
                <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-muted">
                  {thumb
                    ? <img src={thumb} alt="" className="h-full w-full object-cover" />
                    : <div className="flex h-full w-full items-center justify-center text-muted-foreground"><ImageOff className="h-5 w-5" /></div>}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-foreground">{job.use_case_name}</div>
                  <div className="text-xs text-muted-foreground">
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
  )
}
