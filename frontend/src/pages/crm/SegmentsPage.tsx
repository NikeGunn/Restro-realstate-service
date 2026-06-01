import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Filter, Users } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  crmApi, SEGMENT_FIELDS, SEGMENT_OPS,
  type CRMSegment, type SegmentRule, type SegmentFilterRules,
} from '@/services/crm'
import {
  InventoryEmpty as Empty,
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

const blankRule: SegmentRule = { field: 'source', op: 'eq', value: '' }

export function SegmentsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [segments, setSegments] = useState<CRMSegment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [logic, setLogic] = useState<'AND' | 'OR'>('AND')
  const [rules, setRules] = useState<SegmentRule[]>([{ ...blankRule }])
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      setSegments(await crmApi.listSegments({ organization: orgId }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { refresh() }, [refresh])

  const buildRules = (): SegmentFilterRules => ({
    logic,
    rules: rules.map((r) => ({
      ...r,
      // 'in'/'not_in' take a comma list; others take a scalar.
      value: (r.op === 'in' || r.op === 'not_in') && typeof r.value === 'string'
        ? r.value.split(',').map((v) => v.trim()).filter(Boolean)
        : r.value,
    })),
  })

  // Live preview (debounced) whenever rules change.
  useEffect(() => {
    if (!open || !orgId) return
    const tmo = setTimeout(async () => {
      try {
        setPreviewError(null)
        setPreviewCount(await crmApi.previewSegment(orgId, buildRules()))
      } catch (e) {
        setPreviewCount(null)
        setPreviewError(e instanceof Error ? e.message : String(e))
      }
    }, 400)
    return () => clearTimeout(tmo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rules, logic, open, orgId])

  const save = async () => {
    if (!orgId || !name.trim()) return
    try {
      await crmApi.createSegment({
        organization: orgId, name: name.trim(), filter_rules: buildRules(),
      })
      toast({ title: t('common.success') })
      setOpen(false)
      setName(''); setRules([{ ...blankRule }]); setLogic('AND'); setPreviewCount(null)
      refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  const remove = async (seg: CRMSegment) => {
    try {
      await crmApi.deleteSegment(seg.id)
      refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  const updateRule = (i: number, patch: Partial<SegmentRule>) => {
    setRules(rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('crm.segments.title')}</h1>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />{t('crm.segments.add')}
        </Button>
      </div>

      {loading ? (
        <Loading variant="cards" />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : segments.length === 0 ? (
        <Empty icon={Filter} message={t('crm.segments.empty')} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {segments.map((seg) => (
            <Card key={seg.id}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-base">{seg.name}</CardTitle>
                <button onClick={() => remove(seg)} type="button" aria-label="delete">
                  <Trash2 className="h-4 w-4 text-rose-500" />
                </button>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Users className="h-4 w-4" />
                  {t('crm.segments.memberCount', { count: seg.customer_count })}
                </div>
                {seg.description && <p className="text-xs text-muted-foreground mt-2">{seg.description}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create dialog with rule builder */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{t('crm.segments.add')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('common.name')}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>

            <div className="flex items-center gap-2">
              <Label>{t('crm.segments.matchLogic')}</Label>
              <Select value={logic} onValueChange={(v) => setLogic(v as 'AND' | 'OR')}>
                <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="AND">{t('crm.segments.all')}</SelectItem>
                  <SelectItem value="OR">{t('crm.segments.any')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              {rules.map((rule, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <Select value={rule.field} onValueChange={(v) => updateRule(i, { field: v })}>
                    <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SEGMENT_FIELDS.map((f) => (
                        <SelectItem key={f} value={f}>{t(`crm.segmentField.${f}`, f)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={rule.op} onValueChange={(v) => updateRule(i, { op: v })}>
                    <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SEGMENT_OPS.map((o) => (
                        <SelectItem key={o} value={o}>{t(`crm.segmentOp.${o}`, o)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {rule.op !== 'exists' && rule.op !== 'not_exists' && (
                    <Input
                      className="flex-1"
                      placeholder={rule.op === 'in' || rule.op === 'not_in'
                        ? t('crm.segments.commaSeparated') : ''}
                      value={String(rule.value ?? '')}
                      onChange={(e) => updateRule(i, { value: e.target.value })}
                    />
                  )}
                  {rules.length > 1 && (
                    <button onClick={() => setRules(rules.filter((_, idx) => idx !== i))} type="button">
                      <Trash2 className="h-4 w-4 text-rose-500" />
                    </button>
                  )}
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => setRules([...rules, { ...blankRule }])}>
                <Plus className="h-3 w-3 mr-1" />{t('crm.segments.addRule')}
              </Button>
            </div>

            <div className="text-sm rounded bg-muted px-3 py-2">
              {previewError
                ? <span className="text-rose-600">{previewError}</span>
                : t('crm.segments.previewCount', { count: previewCount ?? 0 })}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={save} disabled={!name.trim()}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
