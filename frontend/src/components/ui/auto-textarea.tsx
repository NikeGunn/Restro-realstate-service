import * as React from 'react'
import { Maximize2, Minimize2 } from 'lucide-react'

import { cn } from '@/lib/utils'

export interface AutoTextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** Minimum visible rows before the field starts to grow. Default 2. */
  minRows?: number
  /** Cap auto-grow at this many rows; beyond it the field scrolls. Default 16. */
  maxRows?: number
  /** Show the live character counter (needs `maxLength`). Default true. */
  showCount?: boolean
  /** Show the expand-to-fullscreen control. Default true. */
  expandable?: boolean
}

const LINE_HEIGHT = 22 // px, matches text-sm leading
const V_PADDING = 16 // py-2 top+bottom

/**
 * A textarea that grows to fit its content (no endless scrolling), keeps a
 * manual resize grip, and can pop into a focused full-screen editor so users
 * can read long prompts end-to-end. Drop-in replacement for the base Textarea.
 */
const AutoTextarea = React.forwardRef<HTMLTextAreaElement, AutoTextareaProps>(
  (
    {
      className,
      minRows = 2,
      maxRows = 16,
      showCount = true,
      expandable = true,
      value,
      maxLength,
      onChange,
      ...props
    },
    forwardedRef,
  ) => {
    const innerRef = React.useRef<HTMLTextAreaElement>(null)
    const modalRef = React.useRef<HTMLTextAreaElement>(null)
    const [expanded, setExpanded] = React.useState(false)

    // Merge the forwarded ref with our internal one.
    React.useImperativeHandle(forwardedRef, () => innerRef.current as HTMLTextAreaElement)

    const resize = React.useCallback((el: HTMLTextAreaElement | null) => {
      if (!el) return
      el.style.height = 'auto'
      const min = minRows * LINE_HEIGHT + V_PADDING
      const max = maxRows * LINE_HEIGHT + V_PADDING
      el.style.height = `${Math.min(max, Math.max(min, el.scrollHeight))}px`
      el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
    }, [minRows, maxRows])

    React.useLayoutEffect(() => { resize(innerRef.current) }, [value, resize])
    React.useLayoutEffect(() => {
      if (expanded) {
        // Focus the modal editor and move cursor to the end.
        const el = modalRef.current
        if (el) {
          el.focus()
          const len = el.value.length
          el.setSelectionRange(len, len)
        }
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpanded(false) }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
      }
    }, [expanded])

    const charCount = typeof value === 'string' ? value.length : 0
    const showCounter = showCount && !!maxLength

    const counter = showCounter && (
      <span
        className={cn(
          'pointer-events-none select-none text-[11px] tabular-nums',
          charCount >= (maxLength as number) ? 'text-destructive' : 'text-muted-foreground',
        )}
      >
        {charCount}/{maxLength}
      </span>
    )

    return (
      <>
        <div className="relative">
          <textarea
            ref={innerRef}
            value={value}
            maxLength={maxLength}
            onChange={(e) => { resize(e.target); onChange?.(e) }}
            className={cn(
              'flex w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
              (expandable || showCounter) && 'pb-7',
              className,
            )}
            {...props}
          />

          {(expandable || showCounter) && (
            <div className="pointer-events-none absolute inset-x-2 bottom-1.5 flex items-center justify-between">
              {counter || <span />}
              {expandable && (
                <button
                  type="button"
                  onClick={() => setExpanded(true)}
                  className="pointer-events-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  title="Expand to full screen"
                >
                  <Maximize2 className="h-3 w-3" /> Expand
                </button>
              )}
            </div>
          )}
        </div>

        {expanded && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm"
            onMouseDown={(e) => { if (e.target === e.currentTarget) setExpanded(false) }}
          >
            <div className="flex h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border bg-card shadow-2xl">
              <div className="flex items-center justify-between border-b px-4 py-2.5">
                <span className="text-sm font-medium text-muted-foreground">
                  {props['aria-label'] || 'Editing'}
                </span>
                <div className="flex items-center gap-3">
                  {counter}
                  <button
                    type="button"
                    onClick={() => setExpanded(false)}
                    className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Minimize2 className="h-3.5 w-3.5" /> Collapse
                  </button>
                </div>
              </div>
              <textarea
                ref={modalRef}
                value={value}
                maxLength={maxLength}
                placeholder={props.placeholder}
                onChange={(e) => onChange?.(e)}
                className="flex-1 resize-none bg-transparent px-5 py-4 text-base leading-relaxed outline-none placeholder:text-muted-foreground"
              />
            </div>
          </div>
        )}
      </>
    )
  },
)
AutoTextarea.displayName = 'AutoTextarea'

export { AutoTextarea }
