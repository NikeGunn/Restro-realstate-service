import { Lock } from 'lucide-react'

export interface LockedFieldProps {
  label: string
  value: React.ReactNode
  reason?: string
  className?: string
}

/**
 * Read-only display for fields that are immutable after creation
 * (sku, unit, supplier.tax_id once PO exists, etc.).
 */
export function LockedField({ label, value, reason, className = '' }: LockedFieldProps) {
  return (
    <div className={`space-y-1 ${className}`}>
      <div className="flex items-center gap-1 text-sm font-medium text-slate-700">
        <Lock className="h-3 w-3" />
        {label}
      </div>
      <div
        className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700"
        title={reason || 'This field is locked.'}
      >
        {value || <span className="text-slate-400">—</span>}
      </div>
      {reason && (
        <p className="text-xs text-slate-500">{reason}</p>
      )}
    </div>
  )
}
