import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Receipt, AlertTriangle, Filter } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useAuthStore } from '@/store/auth'
import { billingApi, type UsageEvent } from '@/services/billing'
import { MODULE_LABELS, hkd } from './format'

const STATUS_THEME: Record<string, string> = {
  success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  reserved: 'bg-sky-50 text-sky-700 border-sky-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  refunded: 'bg-muted text-muted-foreground',
}

const PAGE_SIZE = 20

export function UsageHistoryPage() {
  const { t } = useTranslation()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [events, setEvents] = useState<UsageEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [moduleFilter, setModuleFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)

  useEffect(() => {
    if (!orgId) return
    let active = true
    setLoading(true); setError(false)
    billingApi.listEvents({
      organization: orgId,
      module: moduleFilter !== 'all' ? moduleFilter : undefined,
      status: statusFilter !== 'all' ? statusFilter : undefined,
    })
      .then(rows => { if (active) { setEvents(rows); setPage(1) } })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [orgId, moduleFilter, statusFilter])

  const pageRows = useMemo(
    () => events.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [events, page],
  )
  const totalPages = Math.max(1, Math.ceil(events.length / PAGE_SIZE))

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Receipt className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-semibold">{t('billing.usageHistory')}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <Select value={moduleFilter} onValueChange={setModuleFilter}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('billing.allModules')}</SelectItem>
              {Object.entries(MODULE_LABELS).map(([k, v]) => (
                <SelectItem key={k} value={k}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('billing.allStatuses')}</SelectItem>
              {['success', 'reserved', 'failed', 'refunded'].map(s => (
                <SelectItem key={s} value={s}>{t(`billing.eventStatus.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <Card className="divide-y">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse bg-muted/40" />
          ))}
        </Card>
      ) : error ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <AlertTriangle className="h-8 w-8 text-rose-400" /> {t('billing.loadError')}
        </Card>
      ) : events.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <Receipt className="h-8 w-8 opacity-40" /> {t('billing.noEvents')}
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">{t('billing.col.date')}</th>
                  <th className="px-4 py-3">{t('billing.col.module')}</th>
                  <th className="px-4 py-3">{t('billing.col.type')}</th>
                  <th className="px-4 py-3 text-right">{t('billing.col.credits')}</th>
                  <th className="px-4 py-3 text-right">{t('billing.col.cost')}</th>
                  <th className="px-4 py-3">{t('billing.col.status')}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {pageRows.map(ev => (
                  <tr key={ev.id} className="transition-colors hover:bg-muted/30">
                    <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                      {new Date(ev.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">{MODULE_LABELS[ev.module] || ev.module}</td>
                    <td className="px-4 py-3 text-muted-foreground">{ev.event_type}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {ev.credits_used}
                      {ev.is_free_credit ? (
                        <Badge variant="outline" className="ml-2 border-emerald-200 bg-emerald-50 text-emerald-700">
                          {t('billing.free')}
                        </Badge>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{hkd(ev.billable_amount_hkd)}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={STATUS_THEME[ev.status] || ''}>
                        {t(`billing.eventStatus.${ev.status}`)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 ? (
            <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
              <span className="text-muted-foreground">
                {t('billing.pageOf', { page, total: totalPages })}
              </span>
              <div className="flex gap-2">
                <button
                  className="rounded-md border px-3 py-1 disabled:opacity-40"
                  disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                >{t('common.prev', 'Prev')}</button>
                <button
                  className="rounded-md border px-3 py-1 disabled:opacity-40"
                  disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                >{t('common.next', 'Next')}</button>
              </div>
            </div>
          ) : null}
        </Card>
      )}
    </div>
  )
}
