import { AlertTriangle } from 'lucide-react'

export interface StockDisplayProps {
  reported: string
  raw: string
  lowerBound: string
  upperBound: string
  tolerancePercent: string
  unit: string
  isCritical?: boolean
  isNegative?: boolean
}

/**
 * Renders a stock quantity with tolerance metadata.
 * Always use this — never render raw numbers directly.
 */
export function StockDisplay({
  reported, raw, lowerBound, upperBound, tolerancePercent, unit,
  isCritical, isNegative,
}: StockDisplayProps) {
  const tone = isNegative
    ? 'text-rose-700'
    : isCritical
      ? 'text-orange-700'
      : 'text-slate-900'

  const title = (
    `Ledger: ${raw} ${unit}\n` +
    `Tolerance: ±${tolerancePercent}%\n` +
    `Range: ${lowerBound} – ${upperBound} ${unit}`
  )

  return (
    <span
      className={`inline-flex items-center gap-1 font-medium ${tone}`}
      title={title}
    >
      {isNegative && <AlertTriangle className="h-4 w-4" />}
      <span>{reported}</span>
      <span className="text-slate-500">{unit}</span>
    </span>
  )
}
