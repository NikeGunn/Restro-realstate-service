import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/hooks/use-toast'

import {
  crmApi, type CRMCustomer, type CRMInteraction, type CRMConsent, type CRMTag,
} from '@/services/crm'

export function CustomerDetailDrawer({
  customerId, orgId, onClose, onChanged,
}: {
  customerId: string
  orgId?: string
  onClose: () => void
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const { toast } = useToast()

  const [customer, setCustomer] = useState<CRMCustomer | null>(null)
  const [interactions, setInteractions] = useState<CRMInteraction[]>([])
  const [consents, setConsents] = useState<CRMConsent[]>([])
  const [allTags, setAllTags] = useState<CRMTag[]>([])
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    const [c, ix, cs] = await Promise.all([
      crmApi.getCustomer(customerId),
      crmApi.customerInteractions(customerId),
      crmApi.customerConsents(customerId),
    ])
    setCustomer(c)
    setNotes(c.notes)
    setInteractions(ix)
    setConsents(cs)
    if (orgId) setAllTags(await crmApi.listTags({ organization: orgId }))
  }, [customerId, orgId])

  useEffect(() => { load() }, [load])

  const saveNotes = async () => {
    setSaving(true)
    try {
      await crmApi.updateCustomer(customerId, { notes })
      toast({ title: t('common.success') })
      onChanged()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  const toggleTag = async (tag: CRMTag, has: boolean) => {
    try {
      await crmApi.setCustomerTag(customerId, tag.id, has ? 'remove' : 'add')
      await load()
      onChanged()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  const hasTag = (tagId: string) => customer?.tags.some((tg) => tg.id === tagId) ?? false

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{customer?.name ?? t('common.loading')}</DialogTitle>
        </DialogHeader>

        {customer && (
          <Tabs defaultValue="info">
            <TabsList className="grid grid-cols-4 w-full">
              <TabsTrigger value="info">{t('crm.detail.info')}</TabsTrigger>
              <TabsTrigger value="timeline">{t('crm.detail.timeline')}</TabsTrigger>
              <TabsTrigger value="consent">{t('crm.detail.consent')}</TabsTrigger>
              <TabsTrigger value="tags">{t('crm.detail.tags')}</TabsTrigger>
            </TabsList>

            {/* Info */}
            <TabsContent value="info" className="space-y-3 pt-2">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Field label={t('common.phone')} value={customer.phone || '—'} />
                <Field label={t('common.email')} value={customer.email || '—'} />
                <Field label={t('crm.customers.source')} value={t(`crm.source.${customer.source}`)} />
                <Field label={t('crm.customers.consent')} value={t(`crm.consent.${customer.marketing_consent_status}`)} />
                <Field label={t('crm.customers.visits')} value={String(customer.visit_count)} />
                <Field label={t('crm.customers.lastVisit')} value={customer.last_visit_date || '—'} />
                <Field label={t('crm.customers.birthday')} value={customer.birthday || '—'} />
                <Field label={t('crm.customers.whatsapp')} value={customer.whatsapp_number || '—'} />
              </div>
              <div>
                <Label>{t('common.notes')}</Label>
                <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
                <Button className="mt-2" size="sm" onClick={saveNotes} disabled={saving}>
                  {t('common.save')}
                </Button>
              </div>
            </TabsContent>

            {/* Timeline */}
            <TabsContent value="timeline" className="pt-2">
              <ScrollArea className="h-72 pr-3">
                {interactions.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-6 text-center">{t('common.noData')}</p>
                ) : (
                  <ol className="relative border-l pl-4 space-y-3">
                    {interactions.map((ix) => (
                      <li key={ix.id} className="text-sm">
                        <div className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full bg-primary" />
                        <div className="font-medium">{t(`crm.interactionType.${ix.interaction_type}`, ix.interaction_type)}</div>
                        {ix.summary && <div className="text-muted-foreground">{ix.summary}</div>}
                        <div className="text-xs text-muted-foreground">
                          {new Date(ix.created_at).toLocaleString()}
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </ScrollArea>
            </TabsContent>

            {/* Consent */}
            <TabsContent value="consent" className="pt-2">
              <ScrollArea className="h-72 pr-3">
                {consents.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-6 text-center">{t('common.noData')}</p>
                ) : (
                  <div className="space-y-2">
                    {consents.map((cs) => (
                      <div key={cs.id} className="flex items-center justify-between text-sm border rounded px-3 py-2">
                        <div className="flex items-center gap-2">
                          {cs.consent_given
                            ? <Check className="h-4 w-4 text-emerald-600" />
                            : <X className="h-4 w-4 text-rose-600" />}
                          <span>{t(`crm.consentSource.${cs.consent_source}`, cs.consent_source)}</span>
                          {cs.marketing_channels_allowed.length > 0 && (
                            <span className="text-muted-foreground">
                              ({cs.marketing_channels_allowed.join(', ')})
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {new Date(cs.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </TabsContent>

            {/* Tags */}
            <TabsContent value="tags" className="pt-2">
              <div className="flex flex-wrap gap-2">
                {allTags.map((tag) => {
                  const has = hasTag(tag.id)
                  return (
                    <button key={tag.id} onClick={() => toggleTag(tag, has)} type="button">
                      <Badge
                        variant={has ? 'default' : 'outline'}
                        style={has ? { backgroundColor: tag.color } : { color: tag.color, borderColor: tag.color }}
                      >
                        {has && <Check className="h-3 w-3 mr-1" />}
                        {tag.name}
                      </Badge>
                    </button>
                  )
                })}
              </div>
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div>{value}</div>
    </div>
  )
}
