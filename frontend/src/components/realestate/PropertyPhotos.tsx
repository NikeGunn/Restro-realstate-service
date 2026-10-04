import { useEffect, useMemo, useRef, useState } from 'react'
import { GripVertical, ImagePlus, Loader2, Star, Trash2, UploadCloud } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { realEstateApi } from '@/services/api'

const MAX_PHOTOS = 15
const MAX_BYTES = 10 * 1024 * 1024
const ACCEPT = ['image/jpeg', 'image/png', 'image/webp']

type Uploading = { id: string; name: string; preview: string; progress: number }

function apiError(e: any): string {
  const d = e?.response?.data
  return d?.errors?.join(' · ') || d?.error || d?.detail || 'Please try again.'
}

/**
 * Listing photos with drag-and-drop: drop files anywhere on the panel, drag thumbnails to
 * reorder (the first is the cover the website, dashboard and AI agent use), set cover, remove.
 *
 * Two modes:
 *  - saved listing (`propertyId`): every change goes straight to the API (R2, EXIF stripped).
 *  - new listing (no id yet): files are queued locally (`queued` / `onQueueChange`) and the
 *    page uploads them right after the listing is created.
 */
export function PropertyPhotos({ propertyId, images, onChange, queued = [], onQueueChange }: {
  propertyId?: string | null
  images: string[]
  onChange: (images: string[]) => void
  queued?: File[]
  onQueueChange?: (files: File[]) => void
}) {
  const { toast } = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [dragDepth, setDragDepth] = useState(0)
  const [uploading, setUploading] = useState<Uploading[]>([])
  const [busyUrl, setBusyUrl] = useState<string | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)

  const queueMode = !propertyId
  const queuedPreviews = useMemo(() => queued.map(f => URL.createObjectURL(f)), [queued])
  useEffect(() => () => queuedPreviews.forEach(u => URL.revokeObjectURL(u)), [queuedPreviews])

  const tiles = queueMode ? queuedPreviews : images
  const used = tiles.length + uploading.length
  const full = used >= MAX_PHOTOS

  const accept = (list: File[]): File[] => {
    const wrongType = list.filter(f => !ACCEPT.includes(f.type))
    const tooBig = list.filter(f => ACCEPT.includes(f.type) && f.size > MAX_BYTES)
    const ok = list.filter(f => ACCEPT.includes(f.type) && f.size <= MAX_BYTES)
    const room = Math.max(0, MAX_PHOTOS - used)
    const skipped: string[] = []
    if (wrongType.length) skipped.push(`${wrongType.length} not JPG/PNG/WebP`)
    if (tooBig.length) skipped.push(`${tooBig.length} over 10 MB`)
    if (ok.length > room) skipped.push(`${ok.length - room} over the ${MAX_PHOTOS}-photo limit`)
    if (skipped.length) toast({ variant: 'destructive', title: 'Some files were skipped', description: skipped.join(' · ') })
    return ok.slice(0, room)
  }

  const addFiles = async (list: File[]) => {
    const files = accept(list)
    if (!files.length) return
    if (queueMode) {
      onQueueChange?.([...queued, ...files])
      return
    }
    // One request per photo, in order: per-file progress, and one bad file never sinks the rest.
    const pending = files.map(f => ({ id: `${f.name}-${f.size}-${Math.random()}`, name: f.name, preview: URL.createObjectURL(f), progress: 0 }))
    setUploading(prev => [...prev, ...pending])
    let latest = images
    let added = 0
    const errors: string[] = []
    for (const [i, file] of files.entries()) {
      const tile = pending[i]
      try {
        const res = await realEstateApi.properties.uploadPhotos(propertyId!, [file], p =>
          setUploading(prev => prev.map(u => (u.id === tile.id ? { ...u, progress: p } : u))))
        latest = res.images
        added += res.added.length
        errors.push(...res.errors)
        onChange(latest)
      } catch (e) {
        errors.push(`${file.name}: ${apiError(e)}`)
      } finally {
        URL.revokeObjectURL(tile.preview)
        setUploading(prev => prev.filter(u => u.id !== tile.id))
      }
    }
    if (added) toast({ title: 'Photos uploaded', description: `${added} photo${added > 1 ? 's' : ''} added.` })
    if (errors.length) toast({ variant: 'destructive', title: 'Some photos were not uploaded', description: errors.join(' · ') })
  }

  const remove = async (index: number) => {
    if (queueMode) {
      onQueueChange?.(queued.filter((_, i) => i !== index))
      return
    }
    const url = images[index]
    setBusyUrl(url)
    try {
      onChange((await realEstateApi.properties.deletePhoto(propertyId!, url)).images)
    } catch (e) {
      toast({ variant: 'destructive', title: 'Could not remove photo', description: apiError(e) })
    } finally {
      setBusyUrl(null)
    }
  }

  const move = async (from: number, to: number) => {
    if (from === to || to < 0 || to >= tiles.length) return
    if (queueMode) {
      const next = [...queued]
      next.splice(to, 0, next.splice(from, 1)[0])
      onQueueChange?.(next)
      return
    }
    const next = [...images]
    next.splice(to, 0, next.splice(from, 1)[0])
    const before = images
    onChange(next) // optimistic; rolled back if the server refuses
    try {
      onChange((await realEstateApi.properties.reorderPhotos(propertyId!, next)).images)
    } catch (e) {
      onChange(before)
      toast({ variant: 'destructive', title: 'Could not reorder photos', description: apiError(e) })
    }
  }

  // ---- drag & drop: files from the OS vs. thumbnails within the grid
  const isFileDrag = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes('Files')
  const onPanelDragEnter = (e: React.DragEvent) => { if (isFileDrag(e)) { e.preventDefault(); setDragDepth(d => d + 1) } }
  const onPanelDragLeave = (e: React.DragEvent) => { if (isFileDrag(e)) setDragDepth(d => Math.max(0, d - 1)) }
  const onPanelDragOver = (e: React.DragEvent) => { if (isFileDrag(e)) { e.preventDefault(); e.dataTransfer.dropEffect = full ? 'none' : 'copy' } }
  const onPanelDrop = (e: React.DragEvent) => {
    if (!isFileDrag(e)) return
    e.preventDefault()
    setDragDepth(0)
    if (!full) addFiles(Array.from(e.dataTransfer.files))
  }
  const fileHover = dragDepth > 0

  return (
    <div
      className={`space-y-3 rounded-xl border p-4 transition-colors ${fileHover ? 'border-primary bg-primary/5 ring-2 ring-primary/30' : 'bg-muted/20'}`}
      onDragEnter={onPanelDragEnter}
      onDragLeave={onPanelDragLeave}
      onDragOver={onPanelDragOver}
      onDrop={onPanelDrop}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Label className="text-sm font-semibold">Photos <span className="font-normal text-muted-foreground">({used}/{MAX_PHOTOS})</span></Label>
          <p className="text-xs text-muted-foreground">
            Drag to reorder — the first photo is the cover on the website and in WhatsApp chats.
            {queueMode && ' Photos upload as soon as you create the listing.'}
          </p>
        </div>
      </div>

      {tiles.length > 0 || uploading.length > 0 ? (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          {tiles.map((src, i) => (
            <div
              key={queueMode ? `${src}-${i}` : src}
              draggable
              onDragStart={e => { setDragIndex(i); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(i)) }}
              onDragOver={e => { if (dragIndex !== null) { e.preventDefault(); setOverIndex(i) } }}
              onDrop={e => { if (dragIndex !== null) { e.preventDefault(); e.stopPropagation(); move(dragIndex, i) } setDragIndex(null); setOverIndex(null) }}
              onDragEnd={() => { setDragIndex(null); setOverIndex(null) }}
              className={`group relative aspect-[4/3] cursor-grab overflow-hidden rounded-lg border bg-muted shadow-sm transition active:cursor-grabbing
                ${dragIndex === i ? 'opacity-40' : ''} ${overIndex === i && dragIndex !== i ? 'ring-2 ring-primary' : ''}`}
            >
              <img src={src} alt={`Listing photo ${i + 1}`} loading="lazy" draggable={false} className="h-full w-full object-cover" />
              <span className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white">
                <GripVertical className="h-3 w-3" />{i === 0 ? 'Cover' : i + 1}
              </span>
              <div className="absolute right-1.5 top-1.5 flex gap-1 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                {i > 0 && (
                  <button type="button" title="Make cover photo" aria-label={`Make photo ${i + 1} the cover`} onClick={() => move(i, 0)}
                    className="rounded bg-white/90 p-1 shadow hover:bg-white">
                    <Star className="h-3.5 w-3.5 text-amber-500" />
                  </button>
                )}
                <button type="button" title="Remove photo" aria-label={`Remove photo ${i + 1}`} disabled={busyUrl === src} onClick={() => remove(i)}
                  className="rounded bg-white/90 p-1 shadow hover:bg-white">
                  {busyUrl === src ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 text-red-600" />}
                </button>
              </div>
            </div>
          ))}
          {uploading.map(u => (
            <div key={u.id} className="relative aspect-[4/3] overflow-hidden rounded-lg border bg-muted">
              <img src={u.preview} alt="" className="h-full w-full object-cover opacity-50" />
              <div className="absolute inset-x-2 bottom-2 space-y-1">
                <p className="truncate text-[10px] font-medium text-foreground">{u.name}</p>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/70">
                  <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.max(u.progress, 4)}%` }} />
                </div>
              </div>
            </div>
          ))}
          {!full && (
            <button type="button" onClick={() => input.current?.click()}
              className="flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed text-xs text-muted-foreground transition hover:border-primary hover:text-primary">
              <ImagePlus className="h-5 w-5" />Add more
            </button>
          )}
        </div>
      ) : (
        <button type="button" onClick={() => input.current?.click()}
          className={`flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition
            ${fileHover ? 'border-primary text-primary' : 'text-muted-foreground hover:border-primary hover:text-primary'}`}>
          <UploadCloud className="h-9 w-9" />
          <span className="text-sm font-medium text-foreground">Drag & drop photos here, or <span className="text-primary underline">browse</span></span>
          <span className="text-xs">JPG, PNG or WebP · up to 10 MB each · {MAX_PHOTOS} photos max</span>
        </button>
      )}

      {fileHover && !full && (
        <p className="text-center text-sm font-medium text-primary">Drop to upload</p>
      )}
      <input ref={input} type="file" accept={ACCEPT.join(',')} multiple hidden
        onChange={e => { addFiles(Array.from(e.target.files ?? [])); e.target.value = '' }} />
    </div>
  )
}
