import { useTranslation } from 'react-i18next'
import { AlertCircle, RotateCw, type LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

/**
 * Shared empty/loading/error state primitives for inventory pages.
 *
 * Three states a list view can be in (besides showing data):
 *   - Loading → render a Skeleton block (looks like the eventual content).
 *   - Empty   → "no data yet" with an icon + message.
 *   - Error   → user-visible, with a Retry button (never a silent failure).
 *
 * Pages should keep their own data fetching and pass the state in. The
 * Skeleton matches "card grid" or "table row" shapes — pick the variant
 * that fits the page.
 */

type Variant = 'cards' | 'rows'

export function InventoryLoading({ variant = 'rows', count = 5 }: { variant?: Variant; count?: number }) {
  if (variant === 'cards') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: count }).map((_, i) => (
          <Card key={i}>
            <CardContent className="py-5">
              <div className="h-5 w-2/3 bg-muted animate-pulse rounded mb-3" />
              <div className="h-3 w-1/2 bg-muted animate-pulse rounded mb-2" />
              <div className="h-3 w-1/3 bg-muted animate-pulse rounded" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }
  return (
    <Card>
      <CardContent className="p-0">
        <div className="divide-y">
          {Array.from({ length: count }).map((_, i) => (
            <div key={i} className="px-4 py-3 flex items-center gap-3">
              <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              <div className="h-4 flex-1 bg-muted animate-pulse rounded" />
              <div className="h-4 w-20 bg-muted animate-pulse rounded" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function InventoryEmpty({
  icon: Icon,
  message,
}: {
  icon?: LucideIcon
  message?: string
}) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardContent className="py-12 text-center text-muted-foreground">
        {Icon && <Icon className="mx-auto h-8 w-8 mb-2" />}
        {message ?? t('common.noData')}
      </CardContent>
    </Card>
  )
}

export function InventoryError({
  message,
  onRetry,
}: {
  message?: string
  onRetry?: () => void
}) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardContent className="py-10 text-center">
        <AlertCircle className="mx-auto h-8 w-8 mb-2 text-rose-600" />
        <div className="text-sm text-muted-foreground mb-4">
          {message ?? t('common.error')}
        </div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCw className="h-3 w-3 mr-2" />
            {t('common.retry')}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
