import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Users, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  crmApi, type CRMCustomer, type CustomerSource, type ConsentStatus,
} from '@/services/crm'
import {
  InventoryEmpty as Empty,
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'
import { CustomerDetailDrawer } from './CustomerDetailDrawer'

const SOURCES: CustomerSource[] = [
  'manual', 'booking', 'chatbot', 'whatsapp', 'instagram',
  'lucky_draw', 'wifi', 'walk_in', 'import',
]
const CONSENT_STATUSES: ConsentStatus[] = ['not_asked', 'given', 'refused', 'withdrawn']

const consentColor: Record<ConsentStatus, string> = {
  given: 'bg-emerald-100 text-emerald-700',
  refused: 'bg-rose-100 text-rose-700',
  withdrawn: 'bg-amber-100 text-amber-700',
  not_asked: 'bg-slate-100 text-slate-600',
}

const emptyForm = {
  name: '', phone: '', email: '', source: 'manual' as CustomerSource,
  preferred_language: '' as CRMCustomer['preferred_language'],
  birthday: '', notes: '',
}

export function CustomersPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [customers, setCustomers] = useState<CRMCustomer[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [sourceFilter, setSourceFilter] = useState<string>('')
  const [consentFilter, setConsentFilter] = useState<string>('')

  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)

  const [selectedId, setSelectedId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      const data = await crmApi.listCustomers({
        organization: orgId,
        search: search || undefined,
        source: (sourceFilter || undefined) as CustomerSource | undefined,
        marketing_consent_status: (consentFilter || undefined) as ConsentStatus | undefined,
      })
      setCustomers(data.results)
      setCount(data.count)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId, search, sourceFilter, consentFilter])

  useEffect(() => {
    const tmo = setTimeout(refresh, 300)
    return () => clearTimeout(tmo)
  }, [refresh])

  const save = async () => {
    if (!orgId || !form.name.trim()) return
    setSaving(true)
    try {
      await crmApi.createCustomer({
        organization: orgId,
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        source: form.source,
        preferred_language: form.preferred_language,
        birthday: form.birthday || null,
        notes: form.notes,
      })
      toast({ title: t('common.success') })
      setDialogOpen(false)
      setForm(emptyForm)
      refresh()
    } catch (e) {
      toast({
        title: t('common.error'),
        description: e instanceof Error ? e.message : String(e),
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('crm.customers.title')}</h1>
          <p className="text-sm text-muted-foreground">
            {t('crm.customers.count', { count })}
          </p>
        </div>
        <Button onClick={() => { setForm(emptyForm); setDialogOpen(true) }}>
          <Plus className="h-4 w-4 mr-2" />
          {t('crm.customers.add')}
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="py-3 flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder={t('crm.customers.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select value={sourceFilter || 'all'} onValueChange={(v) => setSourceFilter(v === 'all' ? '' : v)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder={t('crm.customers.source')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('common.all')}</SelectItem>
              {SOURCES.map((s) => (
                <SelectItem key={s} value={s}>{t(`crm.source.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={consentFilter || 'all'} onValueChange={(v) => setConsentFilter(v === 'all' ? '' : v)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder={t('crm.customers.consent')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('common.all')}</SelectItem>
              {CONSENT_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>{t(`crm.consent.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {loading ? (
        <Loading variant="rows" />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : customers.length === 0 ? (
        <Empty icon={Users} message={t('crm.customers.empty')} />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th className="px-4 py-2 font-medium">{t('common.name')}</th>
                    <th className="px-4 py-2 font-medium">{t('common.phone')}</th>
                    <th className="px-4 py-2 font-medium">{t('common.email')}</th>
                    <th className="px-4 py-2 font-medium">{t('crm.customers.source')}</th>
                    <th className="px-4 py-2 font-medium">{t('crm.customers.consent')}</th>
                    <th className="px-4 py-2 font-medium text-right">{t('crm.customers.visits')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {customers.map((c) => (
                    <tr
                      key={c.id}
                      className="hover:bg-muted/40 cursor-pointer"
                      onClick={() => setSelectedId(c.id)}
                    >
                      <td className="px-4 py-2.5">
                        <div className="font-medium">{c.name}</div>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {c.tags.map((tag) => (
                            <Badge
                              key={tag.id}
                              variant="secondary"
                              style={{ backgroundColor: `${tag.color}22`, color: tag.color }}
                            >
                              {tag.name}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2.5">{c.phone || '—'}</td>
                      <td className="px-4 py-2.5">{c.email || '—'}</td>
                      <td className="px-4 py-2.5">{t(`crm.source.${c.source}`)}</td>
                      <td className="px-4 py-2.5">
                        <span className={`px-2 py-0.5 rounded text-xs ${consentColor[c.marketing_consent_status]}`}>
                          {t(`crm.consent.${c.marketing_consent_status}`)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{c.visit_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('crm.customers.add')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t('common.name')}</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('common.phone')}</Label>
                <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div>
                <Label>{t('common.email')}</Label>
                <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('crm.customers.source')}</Label>
                <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v as CustomerSource })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SOURCES.map((s) => (
                      <SelectItem key={s} value={s}>{t(`crm.source.${s}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{t('crm.customers.birthday')}</Label>
                <Input type="date" value={form.birthday} onChange={(e) => setForm({ ...form, birthday: e.target.value })} />
              </div>
            </div>
            <div>
              <Label>{t('common.notes')}</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={save} disabled={saving || !form.name.trim()}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {selectedId && (
        <CustomerDetailDrawer
          customerId={selectedId}
          orgId={orgId}
          onClose={() => setSelectedId(null)}
          onChanged={refresh}
        />
      )}
    </div>
  )
}
