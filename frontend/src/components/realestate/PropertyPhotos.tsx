import { useRef, useState } from 'react'
import { ImagePlus, Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { realEstateApi } from '@/services/api'

const MAX_PHOTOS = 15
const MAX_BYTES = 10 * 1024 * 1024

/**
 * Real listing photos. Stored on Cloudflare R2 (server-side, EXIF stripped) and sent by the
 * AI agent to customers who ask ("photo pathaunu"). The first photo is the cover image.
 */
export function PropertyPhotos({ propertyId, images, onChange }: {
  propertyId: string
  images: string[]
  onChange: (images: string[]) => void
}) {
  const { toast } = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    const list = Array.from(files)
    const tooBig = list.filter(f => f.size > MAX_BYTES)
    const ok = list.filter(f => f.size <= MAX_BYTES && f.type.startsWith('image/')).slice(0, MAX_PHOTOS - images.length)
    if (tooBig.length) toast({ variant: 'destructive', title: 'Too large', description: `${tooBig.length} photo(s) over 10 MB were skipped.` })
    if (!ok.length) return
    setBusy(true)
    try {
      const res = await realEstateApi.properties.uploadPhotos(propertyId, ok)
      onChange(res.images)
      toast({ title: 'Photos uploaded', description: `${res.added.length} added${res.errors.length ? `, ${res.errors.length} rejected` : ''}.` })
      if (res.errors.length) toast({ variant: 'destructive', title: 'Some photos were rejected', description: res.errors.join(' · ') })
    } catch (e: any) {
      toast({ variant: 'destructive', title: 'Upload failed', description: e?.response?.data?.errors?.join(' · ') || e?.response?.data?.error || 'Please try again.' })
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  const remove = async (url: string) => {
    setRemoving(url)
    try {
      onChange((await realEstateApi.properties.deletePhoto(propertyId, url)).images)
    } catch {
      toast({ variant: 'destructive', title: 'Could not remove photo' })
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>Photos <span className="text-muted-foreground font-normal">({images.length}/{MAX_PHOTOS}) — the AI sends these when customers ask</span></Label>
        <Button type="button" size="sm" variant="outline" disabled={busy || images.length >= MAX_PHOTOS}
          onClick={() => input.current?.click()}>
          {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ImagePlus className="h-4 w-4 mr-1" />}
          {busy ? 'Uploading…' : 'Add photos'}
        </Button>
        <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
          onChange={e => upload(e.target.files)} />
      </div>
      {images.length === 0 ? (
        <button type="button" onClick={() => input.current?.click()}
          className="w-full rounded-lg border-2 border-dashed p-6 text-sm text-muted-foreground hover:bg-muted/50">
          No photos yet. Click to upload JPG, PNG or WebP (max 10 MB each).
        </button>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {images.map((url, i) => (
            <div key={url} className="relative group aspect-square overflow-hidden rounded-md border bg-muted">
              <img src={url} alt={`Listing photo ${i + 1}`} loading="lazy" className="h-full w-full object-cover" />
              {i === 0 && <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 text-[10px] text-white">Cover</span>}
              <button type="button" aria-label="Remove photo" disabled={removing === url} onClick={() => remove(url)}
                className="absolute right-1 top-1 rounded bg-white/90 p-1 opacity-0 shadow group-hover:opacity-100 focus:opacity-100">
                {removing === url ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 text-red-600" />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
