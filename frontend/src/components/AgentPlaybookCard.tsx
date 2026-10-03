import { useEffect, useState } from 'react'
import { Bot, Plus, Save, Trash2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/hooks/use-toast'
import { api } from '@/services/api'

const MAX_CHARS = 240
const MAX_ITEMS = 30

type Playbook = { instructions: string[]; can_edit: boolean }

/**
 * AI agent playbook — the owner's standing instructions the WhatsApp/website agent follows
 * on every message (tone, policies, what to offer). Saved to /api/v1/ai/playbook/; takes
 * effect on the next customer message, no deploy needed. Listings, prices and the market
 * come from Properties and Settings → Market, so nothing here should restate them.
 */
export function AgentPlaybookCard({ organizationId }: { organizationId: string }) {
  const { toast } = useToast()
  const [items, setItems] = useState<string[]>([])
  const [canEdit, setCanEdit] = useState(false)
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api.get<Playbook>('/v1/ai/playbook/', { params: { organization: organizationId } })
      .then(({ data }) => { if (alive) { setItems(data.instructions); setCanEdit(data.can_edit); setError('') } })
      .catch(() => { if (alive) setError('Could not load the AI playbook.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [organizationId])

  const save = async (next: string[]) => {
    setSaving(true)
    try {
      const { data } = await api.put<Playbook>('/v1/ai/playbook/', { organization: organizationId, instructions: next })
      setItems(data.instructions)
      toast({ title: 'AI playbook saved', description: 'The agent follows it from the next message.' })
    } catch (e: any) {
      const msg = e?.response?.data?.instructions?.[0] || e?.response?.data?.detail || 'Save failed.'
      toast({ variant: 'destructive', title: 'Could not save', description: String(msg) })
    } finally {
      setSaving(false)
    }
  }

  const add = () => {
    const text = draft.trim()
    if (!text || items.length >= MAX_ITEMS) return
    setItems((prev) => [...prev, text])
    setDraft('')
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="h-5 w-5" />
          AI agent playbook
        </CardTitle>
        <CardDescription>
          Rules your AI assistant follows with every customer (tone, policies, what to offer). Listings and
          prices come from your Properties page — keep those out of here.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : (
          <>
            {items.length === 0 && <p className="text-sm text-muted-foreground">No rules yet.</p>}
            <ol className="space-y-2">
              {items.map((text, i) => (
                <li key={`${i}-${text}`} className="flex items-start gap-2">
                  <span className="mt-2 w-5 shrink-0 text-xs text-muted-foreground">{i + 1}.</span>
                  {canEdit ? (
                    <Input
                      value={text}
                      maxLength={MAX_CHARS}
                      onChange={(e) => setItems((prev) => prev.map((t, j) => (j === i ? e.target.value : t)))}
                    />
                  ) : (
                    <p className="py-2 text-sm">{text}</p>
                  )}
                  {canEdit && (
                    <Button variant="ghost" size="icon" aria-label="Remove rule"
                      onClick={() => setItems((prev) => prev.filter((_, j) => j !== i))}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </li>
              ))}
            </ol>
            {canEdit ? (
              <>
                <div className="flex gap-2">
                  <Input
                    value={draft}
                    maxLength={MAX_CHARS}
                    placeholder='e.g. "Always offer two viewing time slots"'
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
                  />
                  <Button variant="outline" onClick={add} disabled={!draft.trim() || items.length >= MAX_ITEMS}>
                    <Plus className="h-4 w-4 mr-1" /> Add
                  </Button>
                </div>
                <Button onClick={() => save(items.map((t) => t.trim()).filter(Boolean))} disabled={saving}>
                  <Save className="h-4 w-4 mr-2" />
                  {saving ? 'Saving…' : 'Save playbook'}
                </Button>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Only the owner can edit these rules.</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
