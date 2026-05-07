import { useEffect, useRef, useState } from 'react'
import { Camera, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Lightweight barcode scanner.
 *
 * Uses the browser's native BarcodeDetector API where available
 * (Chromium / modern Edge / Android Chrome). Falls back to a manual
 * entry mode when the API is missing or camera permission is denied
 * — keeps the UI usable without a heavy 3rd-party dep.
 */
interface Props {
  onScan: (code: string) => void
  onClose: () => void
}

export function BarcodeScanner({ onScan, onClose }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [error, setError] = useState<string>('')
  const [manual, setManual] = useState('')
  const [supported, setSupported] = useState(true)

  useEffect(() => {
    const Detector = (window as any).BarcodeDetector
    if (!Detector) {
      setSupported(false)
      return
    }

    let cancelled = false
    let detector: any
    try {
      detector = new Detector({
        formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'qr_code'],
      })
    } catch {
      setSupported(false)
      return
    }

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
        })
        if (cancelled) {
          stream.getTracks().forEach(t => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
        const tick = async () => {
          if (cancelled || !videoRef.current) return
          try {
            const codes = await detector.detect(videoRef.current)
            if (codes && codes.length > 0) {
              onScan(codes[0].rawValue)
              return
            }
          } catch { /* keep polling */ }
          requestAnimationFrame(tick)
        }
        tick()
      } catch (e: any) {
        setError(e?.message || 'Camera error')
      }
    }
    void start()

    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach(t => t.stop())
    }
  }, [onScan])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Camera className="h-4 w-4" /> Barcode scanner
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      {supported ? (
        <div className="rounded border bg-black overflow-hidden">
          <video ref={videoRef} className="w-full max-h-64 object-cover" muted playsInline />
        </div>
      ) : (
        <div className="text-xs text-slate-500">
          Camera/BarcodeDetector unavailable. Enter code manually.
        </div>
      )}
      {error && <div className="text-sm text-rose-600">{error}</div>}
      <div className="flex gap-2">
        <input
          autoFocus
          className="flex-1 border rounded px-2 py-1 text-sm"
          placeholder="Or type/paste a barcode"
          value={manual}
          onChange={e => setManual(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && manual.trim()) onScan(manual.trim())
          }}
        />
        <Button size="sm" disabled={!manual.trim()} onClick={() => onScan(manual.trim())}>
          OK
        </Button>
      </div>
    </div>
  )
}
