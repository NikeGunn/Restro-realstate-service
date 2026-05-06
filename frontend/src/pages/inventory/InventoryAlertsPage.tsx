import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, CheckCircle2 } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { inventoryApi, type StockAlert } from '@/services/inventory'

export function InventoryAlertsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [alerts, setAlerts] = useState<StockAlert[]>([])
  const [showResolved, setShowResolved] = useState(false)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    if (!orgId) return
    setLoading(true)
    try {
      setAlerts(await inventoryApi.listAlerts({
        organization: orgId,
        resolved: showResolved,
      }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() /* eslint-disable-line */ }, [orgId, showResolved])

  const resolve = async (a: StockAlert) => {
    try {
      await inventoryApi.resolveAlert(a.id)
      await refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('inventory.alerts')}</h1>
          <p className="text-muted-foreground">
            Auto-generated when items hit reorder level or go negative.
          </p>
        </div>
        <Button variant="outline" onClick={() => setShowResolved(!showResolved)}>
          {showResolved ? 'Show open' : 'Show resolved'}
        </Button>
      </div>

      {loading ? (
        <p className="text-muted-foreground">{t('common.loading')}</p>
      ) : alerts.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Bell className="mx-auto h-8 w-8 mb-2" />
            {showResolved ? 'No resolved alerts' : 'All clear — no open alerts.'}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => (
            <Card key={a.id} className={a.is_resolved ? 'opacity-60' : ''}>
              <CardContent className="py-4 flex items-center justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={
                        a.alert_type === 'negative_stock'
                          ? 'bg-rose-100 text-rose-800 border-rose-200'
                          : 'bg-orange-100 text-orange-800 border-orange-200'
                      }
                    >
                      {a.alert_type.replace('_', ' ')}
                    </Badge>
                    <span className="font-medium">{a.item_name}</span>
                    <span className="text-xs text-muted-foreground font-mono">
                      {a.item_sku}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">{a.message}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {new Date(a.triggered_at).toLocaleString()}
                  </p>
                </div>
                {!a.is_resolved && (
                  <Button size="sm" variant="outline" onClick={() => resolve(a)}>
                    <CheckCircle2 className="h-4 w-4 mr-1" />
                    Resolve
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
