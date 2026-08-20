import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Ban, RotateCcw, Search, Ticket } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import {
  InventoryEmpty as Empty,
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

import { useAuthStore } from '@/store/auth'
import { coffeePassApi, type CoffeePass, type PassStatus } from '@/services/coffeePass'

import { PassStatusBadge } from './components/PassStatusBadge'

const FILTERS: (PassStatus | 'all')[] = [
  'all', 'active', 'expired', 'suspended', 'cancelled',
]

export function CoffeePassPassesPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [passes, setPasses] = useState<CoffeePass[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<PassStatus | 'all'>('all')
  const [search, setSearch] = useState('')
  const [suspending, setSuspending] = useState<CoffeePass | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      setPasses(await coffeePassApi.listPasses({
        organization: orgId,
        ...(filter !== 'all' ? { status: filter } : {}),
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId, filter])

  useEffect(() => { refresh() }, [refresh])

  // Client-side name/phone filter: staff scan this list visually while a
  // customer waits, so instant feedback beats a round trip.
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return passes
    return passes.filter((p) => p.customer_name.toLowerCase().includes(needle))
  }, [passes, search])

  const handleSuspend = async () => {
    if (!suspending || reason.trim().length < 5) {
      toast({ title: t('coffeePass.passes.reasonRequired'), variant: 'destructive' })
      return
    }
    setBusy(true)
    try {
      await coffeePassApi.suspendPass(suspending.id, reason.trim())
      toast({ title: t('coffeePass.passes.suspended') })
      setSuspending(null)
      setReason('')
      await refresh()
    } catch {
      toast({ title: t('coffeePass.passes.suspendFailed'), variant: 'destructive' })
    } finally {
      setBusy(false)
    }
  }

  const handleRestore = async (pass: CoffeePass) => {
    setBusy(true)
    try {
      await coffeePassApi.restorePass(pass.id)
      toast({ title: t('coffeePass.passes.restored') })
      await refresh()
    } catch {
      toast({ title: t('coffeePass.passes.restoreFailed'), variant: 'destructive' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('coffeePass.passes.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('coffeePass.passes.subtitle')}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('coffeePass.passes.searchPlaceholder')}
            className="pl-8"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((value) => (
            <Button
              key={value}
              size="sm"
              variant={filter === value ? 'default' : 'outline'}
              onClick={() => setFilter(value)}
            >
              {t(`coffeePass.passes.filter.${value}`)}
            </Button>
          ))}
        </div>
      </div>

      {loading ? (
        <Loading variant="rows" count={5} />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : visible.length === 0 ? (
        <Empty icon={Ticket} message={t('coffeePass.passes.empty')} />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40">
                  <tr className="text-left">
                    <th className="p-3 font-medium">{t('coffeePass.passes.customer')}</th>
                    <th className="p-3 font-medium">{t('coffeePass.passes.status')}</th>
                    <th className="p-3 font-medium">{t('coffeePass.passes.expires')}</th>
                    <th className="p-3 font-medium text-right">
                      {t('coffeePass.passes.redemptions')}
                    </th>
                    <th className="p-3 font-medium text-right">
                      {t('coffeePass.passes.saved')}
                    </th>
                    <th className="p-3" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {visible.map((pass) => (
                    <tr key={pass.id} className="hover:bg-muted/30">
                      <td className="p-3">
                        <div className="font-medium">{pass.customer_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {pass.location_name}
                        </div>
                      </td>
                      <td className="p-3"><PassStatusBadge status={pass.status} /></td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(pass.expires_at).toLocaleDateString()}
                      </td>
                      <td className="p-3 text-right tabular-nums">
                        {pass.redemption_count}
                      </td>
                      <td className="p-3 text-right tabular-nums font-medium">
                        HK${pass.total_saved_hkd}
                      </td>
                      <td className="p-3 text-right">
                        {pass.status === 'active' ? (
                          <Button
                            size="sm" variant="ghost" disabled={busy}
                            onClick={() => setSuspending(pass)}
                          >
                            <Ban className="h-3.5 w-3.5 mr-1" />
                            {t('coffeePass.passes.suspend')}
                          </Button>
                        ) : pass.status === 'suspended' ? (
                          <Button
                            size="sm" variant="ghost" disabled={busy}
                            onClick={() => handleRestore(pass)}
                          >
                            <RotateCcw className="h-3.5 w-3.5 mr-1" />
                            {t('coffeePass.passes.restore')}
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <Dialog
        open={suspending !== null}
        onOpenChange={(open) => { if (!open) { setSuspending(null); setReason('') } }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('coffeePass.passes.suspendTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {t('coffeePass.passes.suspendHint', { name: suspending?.customer_name })}
            </p>
            <div>
              <Label htmlFor="cp-suspend-reason">
                {t('coffeePass.passes.reason')}
              </Label>
              <Textarea
                id="cp-suspend-reason" rows={3} value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t('coffeePass.passes.reasonPlaceholder')}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline" disabled={busy}
              onClick={() => { setSuspending(null); setReason('') }}
            >
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleSuspend} disabled={busy}>
              {t('coffeePass.passes.suspend')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
