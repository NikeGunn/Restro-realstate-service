import { useEffect, useState } from 'react'
import { Globe2, Save } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { locationsApi, organizationsApi } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { MARKET_OPTIONS, formatMoney, marketFor } from '@/lib/money'
import type { Location } from '@/types'

/**
 * Market & currency — the ONE switch for an organization's money and time.
 * It writes the primary location's country + timezone. Everything reads from there:
 * dashboard prices (lib/money.ts) and the WhatsApp/website agent (ai_engine/agent/tools.py
 * market_for), so what the admin sets here is exactly what customers are quoted.
 */
export function MarketSettingsCard({ locations, onSaved }: { locations: Location[]; onSaved: () => Promise<void> | void }) {
  const { toast } = useToast()
  const { currentOrganization, setCurrentOrganization } = useAuthStore()
  const primary = locations.find((l) => l.is_primary && l.is_active !== false) ?? locations[0]
  const [country, setCountry] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setCountry(primary ? marketFor(primary.country).country : '')
  }, [primary?.id, primary?.country])

  const current = MARKET_OPTIONS.find((m) => m.country === country)
  const unchanged = !!primary && (primary.country ?? '') === country

  const save = async () => {
    if (!primary || !current || !currentOrganization) return
    setSaving(true)
    try {
      await locationsApi.update(currentOrganization.id, primary.id, { country: current.country, timezone: current.timezone })
      setCurrentOrganization(await organizationsApi.get(currentOrganization.id))
      await onSaved()
      toast({ title: 'Market updated', description: `Prices now show in ${current.symbol}; the AI agent quotes the same.` })
    } catch (error) {
      toast({ variant: 'destructive', title: 'Could not update market', description: 'Only the owner can change this.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Globe2 className="h-5 w-5" />
          Market &amp; currency
        </CardTitle>
        <CardDescription>
          Sets the currency, number format and time zone for the dashboard and for what the AI agent tells customers.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!primary ? (
          <p className="text-sm text-muted-foreground">Add a location first — the market is stored on your primary location.</p>
        ) : (
          <>
            <div className="space-y-2">
              <Label>Country / market</Label>
              <Select value={country} onValueChange={setCountry}>
                <SelectTrigger className="max-w-sm"><SelectValue placeholder="Choose a market" /></SelectTrigger>
                <SelectContent>
                  {MARKET_OPTIONS.map((m) => (
                    <SelectItem key={m.country} value={m.country}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {current && (
              <p className="text-sm text-muted-foreground">
                Example: {formatMoney(18500000, current.country)} · rent {formatMoney(12000, current.country)}/month ·
                time zone {current.timezone}
              </p>
            )}
            <Button onClick={save} disabled={saving || unchanged || !current}>
              <Save className="h-4 w-4 mr-2" />
              {saving ? 'Saving…' : 'Save market'}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}
