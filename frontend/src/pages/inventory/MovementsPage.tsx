import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowLeftRight, ArrowDown, ArrowUp } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

import { useAuthStore } from '@/store/auth'
import {
  inventoryApi, type StockMovement, type MovementType,
} from '@/services/inventory'

const TYPES: ('all' | MovementType)[] = [
  'all', 'purchase', 'sale', 'waste', 'adjustment',
  'recipe_consumption', 'supplier_return', 'opening_stock',
  'import_sale', 'import_purchase',
]

export function MovementsPage() {
  const { t } = useTranslation()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [movements, setMovements] = useState<StockMovement[]>([])
  const [filter, setFilter] = useState<'all' | MovementType>('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    inventoryApi
      .listMovements({
        organization: orgId,
        movement_type: filter === 'all' ? undefined : filter,
      })
      .then(setMovements)
      .finally(() => setLoading(false))
  }, [orgId, filter])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('inventory.movements')}</h1>
        <p className="text-muted-foreground">
          Append-only ledger. Every change to stock is recorded here.
        </p>
      </div>

      <Select value={filter} onValueChange={(v) => setFilter(v as 'all' | MovementType)}>
        <SelectTrigger className="w-[260px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {TYPES.map((tp) => (
            <SelectItem key={tp} value={tp}>
              {tp === 'all' ? t('common.all') : t(`inventory.movementTypes.${tp}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {loading ? (
        <p className="text-muted-foreground">{t('common.loading')}</p>
      ) : movements.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <ArrowLeftRight className="mx-auto h-8 w-8 mb-2" />
            {t('common.noData')}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/30 border-b">
                  <tr className="text-left">
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Item</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3 text-right">Quantity</th>
                    <th className="px-4 py-3">Notes</th>
                    <th className="px-4 py-3">By</th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map((m) => {
                    const qty = Number(m.quantity)
                    const negative = qty < 0
                    return (
                      <tr
                        key={m.id}
                        className={`border-b last:border-0 ${m.is_reversed ? 'opacity-50 line-through' : ''}`}
                      >
                        <td className="px-4 py-3 font-mono text-xs">{m.movement_date}</td>
                        <td className="px-4 py-3">
                          <div>{m.item_name}</div>
                          <div className="text-xs text-muted-foreground font-mono">{m.item_sku}</div>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline">
                            {t(`inventory.movementTypes.${m.movement_type}`)}
                          </Badge>
                        </td>
                        <td className={`px-4 py-3 text-right font-mono ${negative ? 'text-rose-600' : 'text-emerald-700'}`}>
                          <span className="inline-flex items-center gap-1">
                            {negative ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />}
                            {m.quantity} {m.item_unit}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground max-w-[280px] truncate" title={m.notes}>
                          {m.notes || '—'}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {m.created_by_email || '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
