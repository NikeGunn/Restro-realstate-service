import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Copy, Download, Loader2, QrCode } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'

import { coffeePassApi, type CoffeePassPlan } from '@/services/coffeePass'

/**
 * Generate, preview, and download a plan's QR code.
 *
 * The guide used to tell owners to paste the link into "any generator" — this
 * dialog closes that gap so a printable card comes straight from the dashboard.
 *
 * Both images are fetched as blobs through the authed axios instance: the
 * endpoints require a Bearer token, so a plain <a href> would 401. Every object
 * URL created here is revoked, otherwise reopening the dialog leaks blobs for
 * the lifetime of the tab.
 */
export function PlanQrDialog({
  open, plan, onOpenChange,
}: {
  open: boolean
  plan: CoffeePassPlan | null
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const { toast } = useToast()

  const [previewUrl, setPreviewUrl] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState<'qr' | 'poster' | null>(null)
  const [failed, setFailed] = useState(false)

  // Track the live object URL so cleanup never depends on render order.
  const previewRef = useRef<string>('')

  const releasePreview = useCallback(() => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current)
      previewRef.current = ''
    }
  }, [])

  useEffect(() => {
    if (!open || !plan) return
    let cancelled = false
    setLoading(true)
    setFailed(false)

    coffeePassApi.fetchPlanQrObjectUrl(plan.id)
      .then((url) => {
        if (cancelled) {
          // The dialog closed mid-flight — drop the blob we just created.
          URL.revokeObjectURL(url)
          return
        }
        releasePreview()
        previewRef.current = url
        setPreviewUrl(url)
      })
      .catch(() => { if (!cancelled) setFailed(true) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [open, plan, releasePreview])

  // Revoke on unmount / close so blobs don't accumulate across openings.
  useEffect(() => {
    if (!open) {
      releasePreview()
      setPreviewUrl('')
    }
    return releasePreview
  }, [open, releasePreview])

  const publicUrl = plan
    ? `${window.location.origin}${plan.public_url_path}`
    : ''

  const triggerDownload = async (kind: 'qr' | 'poster') => {
    if (!plan) return
    setDownloading(kind)
    let url = ''
    try {
      url = kind === 'qr'
        ? await coffeePassApi.fetchPlanQrObjectUrl(plan.id)
        : await coffeePassApi.fetchPlanPosterObjectUrl(plan.id)

      const link = document.createElement('a')
      link.href = url
      link.download = `${plan.name || 'coffee-pass'}-${kind}.png`
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch {
      toast({ title: t('coffeePass.plans.qrFailed'), variant: 'destructive' })
    } finally {
      // Revoke after the click has been dispatched; the browser has already
      // taken its own reference to the blob by then.
      if (url) URL.revokeObjectURL(url)
      setDownloading(null)
    }
  }

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(publicUrl)
      toast({ title: t('coffeePass.plans.linkCopied') })
    } catch {
      toast({ title: t('coffeePass.plans.copyFailed'), variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <QrCode className="h-4 w-4" />
            {t('coffeePass.plans.qrTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {t('coffeePass.plans.qrHint')}
          </p>

          <div className="flex items-center justify-center rounded-lg border bg-white p-4 min-h-[240px]">
            {loading ? (
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            ) : failed ? (
              <p className="text-sm text-destructive">
                {t('coffeePass.plans.qrFailed')}
              </p>
            ) : previewUrl ? (
              <img
                src={previewUrl}
                alt={t('coffeePass.plans.qrTitle')}
                className="h-52 w-52 object-contain"
              />
            ) : null}
          </div>

          <div className="rounded-md bg-muted/50 p-2">
            <p className="text-[11px] font-mono break-all text-muted-foreground">
              {publicUrl}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="outline" size="sm" onClick={() => triggerDownload('qr')}
              disabled={downloading !== null || failed}
            >
              {downloading === 'qr'
                ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                : <Download className="h-3.5 w-3.5 mr-1" />}
              {t('coffeePass.plans.downloadQr')}
            </Button>
            <Button
              size="sm" onClick={() => triggerDownload('poster')}
              disabled={downloading !== null || failed}
            >
              {downloading === 'poster'
                ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                : <Download className="h-3.5 w-3.5 mr-1" />}
              {t('coffeePass.plans.downloadPoster')}
            </Button>
          </div>

          <Button variant="ghost" size="sm" className="w-full" onClick={copyLink}>
            <Copy className="h-3.5 w-3.5 mr-1" />
            {t('coffeePass.plans.copyLink')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
