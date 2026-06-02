import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Download, Heart, RefreshCw, Loader2, AlertTriangle, Ban } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'
import { contentStudioApi, type GenerationJob } from '@/services/content_studio'

const POLL_MS = 2500
const ACTIVE = new Set(['queued', 'processing', 'draft'])

export function GenerationResultPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const { jobId } = useParams<{ jobId: string }>()

  const [job, setJob] = useState<GenerationJob | null>(null)
  const [regenOpen, setRegenOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const poll = useCallback(async () => {
    if (!jobId) return
    try {
      const j = await contentStudioApi.getJob(jobId)
      setJob(j)
      if (ACTIVE.has(j.status)) {
        timer.current = setTimeout(poll, POLL_MS)
      }
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }, [jobId, t, toast])

  useEffect(() => {
    poll()
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [poll])

  async function favorite(id: string) {
    const res = await contentStudioApi.favoriteOutput(id)
    setJob(j => j ? { ...j, outputs: j.outputs.map(o => o.id === id ? { ...o, is_favorite: res.is_favorite } : o) } : j)
  }

  async function download(id: string, url: string | null) {
    await contentStudioApi.downloadOutput(id)
    if (url) window.open(url, '_blank')
  }

  async function regenerate() {
    if (!job) return
    setRegenOpen(false)
    const newJob = await contentStudioApi.regenerateJob(job.id)
    navigate(`/content-studio/result/${newJob.id}`)
  }

  if (!job) {
    return <div className="p-10 text-slate-400">{t('common.loading')}</div>
  }

  const isActive = ACTIVE.has(job.status)
  const isFailed = job.status === 'failed'
  const isBlocked = job.status === 'blocked_by_cap'

  return (
    <div className="min-h-full bg-gradient-to-b from-slate-950 to-slate-900 p-6 md:p-10">
      <div className="mx-auto max-w-5xl">
        <Button variant="ghost" className="mb-4 text-slate-300 hover:text-white"
          onClick={() => navigate('/content-studio')}>
          <ArrowLeft className="mr-2 h-4 w-4" /> {t('contentStudio.backToGallery')}
        </Button>

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">{job.use_case_name}</h1>
            <p className="text-sm text-slate-400">{new Date(job.created_at).toLocaleString()}</p>
          </div>
          <StatusBadge status={job.status} />
        </div>

        {/* Active: animated generating state */}
        {isActive && (
          <Card className="mt-8 flex flex-col items-center justify-center gap-4 border-white/10 bg-white/5 py-20">
            <div className="relative">
              <div className="h-16 w-16 animate-spin rounded-full border-2 border-fuchsia-500/30 border-t-fuchsia-400" />
              <Loader2 className="absolute inset-0 m-auto h-6 w-6 animate-pulse text-fuchsia-300" />
            </div>
            <p className="text-slate-300">{t('contentStudio.generatingNow')}</p>
            <p className="text-xs text-slate-500">{t('contentStudio.generatingHint')}</p>
          </Card>
        )}

        {isBlocked && (
          <Card className="mt-8 flex items-center gap-3 border-amber-400/30 bg-amber-400/10 p-6 text-amber-200">
            <Ban className="h-5 w-5" /> {t('contentStudio.blockedByCap')}
          </Card>
        )}

        {isFailed && (
          <Card className="mt-8 flex items-center gap-3 border-rose-400/30 bg-rose-400/10 p-6 text-rose-200">
            <AlertTriangle className="h-5 w-5" />
            <div>
              <div>{t('contentStudio.generationFailed')}</div>
              {job.error_message && <div className="text-xs opacity-80">{job.error_message}</div>}
            </div>
          </Card>
        )}

        {/* Completed: image grid */}
        {job.status === 'completed' && (
          <>
            <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
              {job.outputs.map(out => (
                <Card key={out.id} className="group overflow-hidden border-white/10 bg-white/5">
                  <div className="relative aspect-square bg-slate-800">
                    {out.thumbnail_url && (
                      <img src={out.thumbnail_url} alt="" className="h-full w-full object-cover" />
                    )}
                    <div className="absolute inset-x-0 bottom-0 flex justify-end gap-2 bg-gradient-to-t from-black/70 to-transparent p-3 opacity-0 transition group-hover:opacity-100">
                      <Button size="icon" variant="secondary" onClick={() => favorite(out.id)}>
                        <Heart className={`h-4 w-4 ${out.is_favorite ? 'fill-rose-500 text-rose-500' : ''}`} />
                      </Button>
                      <Button size="icon" variant="secondary" onClick={() => download(out.id, out.asset_url)}>
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between px-3 py-2 text-xs text-slate-400">
                    <span>{out.width}×{out.height}</span>
                    <span>{out.download_count} {t('contentStudio.downloads')}</span>
                  </div>
                </Card>
              ))}
            </div>

            <div className="mt-6 flex justify-center">
              <Button variant="outline" className="border-white/20 text-slate-200"
                onClick={() => setRegenOpen(true)}>
                <RefreshCw className="mr-2 h-4 w-4" /> {t('contentStudio.regenerate')}
              </Button>
            </div>
          </>
        )}
      </div>

      <Dialog open={regenOpen} onOpenChange={setRegenOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('contentStudio.regenerate')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('contentStudio.regenerateConfirm')}</p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRegenOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={regenerate}>{t('contentStudio.regenerate')} · +1</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function StatusBadge({ status }: { status: GenerationJob['status'] }) {
  const { t } = useTranslation()
  const map: Record<string, string> = {
    completed: 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30',
    processing: 'bg-violet-500/20 text-violet-300 border-violet-400/30',
    queued: 'bg-sky-500/20 text-sky-300 border-sky-400/30',
    failed: 'bg-rose-500/20 text-rose-300 border-rose-400/30',
    blocked_by_cap: 'bg-amber-500/20 text-amber-300 border-amber-400/30',
    cancelled: 'bg-slate-500/20 text-slate-300 border-slate-400/30',
    refunded: 'bg-slate-500/20 text-slate-300 border-slate-400/30',
    draft: 'bg-slate-500/20 text-slate-300 border-slate-400/30',
  }
  return <Badge className={map[status] || map.draft}>{t(`contentStudio.status.${status}`)}</Badge>
}
