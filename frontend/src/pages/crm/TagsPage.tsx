import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Tag as TagIcon, Lock } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import { crmApi, type CRMTag } from '@/services/crm'
import {
  InventoryEmpty as Empty,
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

export function TagsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [tags, setTags] = useState<CRMTag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', color: '#6366F1' })

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      setTags(await crmApi.listTags({ organization: orgId }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { refresh() }, [refresh])

  const save = async () => {
    if (!orgId || !form.name.trim()) return
    try {
      await crmApi.createTag({ organization: orgId, name: form.name.trim(), color: form.color })
      toast({ title: t('common.success') })
      setOpen(false)
      setForm({ name: '', color: '#6366F1' })
      refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  const remove = async (tag: CRMTag) => {
    try {
      await crmApi.deleteTag(tag.id)
      refresh()
    } catch {
      toast({ title: t('common.error'), description: t('crm.tags.systemLocked'), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('crm.tags.title')}</h1>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />{t('crm.tags.add')}
        </Button>
      </div>

      {loading ? (
        <Loading variant="rows" />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : tags.length === 0 ? (
        <Empty icon={TagIcon} message={t('common.noData')} />
      ) : (
        <Card>
          <CardContent className="py-4 flex flex-wrap gap-3">
            {tags.map((tag) => (
              <div key={tag.id} className="flex items-center gap-2 border rounded-full pl-3 pr-1.5 py-1">
                <Badge style={{ backgroundColor: tag.color }}>{tag.name}</Badge>
                {tag.is_system ? (
                  <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <button onClick={() => remove(tag)} type="button" aria-label="delete">
                    <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                  </button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t('crm.tags.add')}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t('common.name')}</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>{t('crm.tags.color')}</Label>
              <Input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} className="h-10 w-20 p-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={save} disabled={!form.name.trim()}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
