import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Plus, Gift, QrCode, Users, Send, Share2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

import { useAuthStore } from '@/store/auth'
import {
  luckyDrawApi, type LuckyDrawCampaign, type CampaignStatus,
} from '@/services/lucky_draw'
import {
  InventoryEmpty as Empty,
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

const STATUS_VARIANT: Record<CampaignStatus, string> = {
  draft: 'bg-slate-200 text-slate-700',
  active: 'bg-emerald-100 text-emerald-700',
  paused: 'bg-amber-100 text-amber-700',
  ended: 'bg-rose-100 text-rose-700',
}

export function CampaignListPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [campaigns, setCampaigns] = useState<LuckyDrawCampaign[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    try {
      setCampaigns(await luckyDrawApi.listCampaigns({ organization: orgId }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [orgId])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('luckyDraw.title')}</h1>
        <Button onClick={() => navigate('/lucky-draw/new')}>
          <Plus className="h-4 w-4 mr-2" />{t('luckyDraw.create')}
        </Button>
      </div>

      {loading ? (
        <Loading variant="cards" count={3} />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : campaigns.length === 0 ? (
        <Empty icon={Gift} message={t('luckyDraw.empty')} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {campaigns.map((c) => (
            <button key={c.id} type="button" className="text-left"
              onClick={() => navigate(`/lucky-draw/${c.id}`)}>
              <Card className="hover:border-primary transition-colors h-full">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base truncate">{c.name}</CardTitle>
                    <Badge className={STATUS_VARIANT[c.status]}>
                      {t(`luckyDraw.status.${c.status}`)}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="text-sm text-muted-foreground">
                    {t('luckyDraw.upTo', { pct: c.max_discount })}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm pt-1">
                    <Stat icon={Users} label={t('luckyDraw.entries')} value={c.entry_count} />
                    <Stat icon={QrCode} label={t('luckyDraw.qrCodes')} value={c.prizes.length} hidden />
                    {c.deliver_coupon_via_whatsapp && (
                      <Stat icon={Send} label="WhatsApp" value="✓" />
                    )}
                    {c.referral_enabled && (
                      <Stat icon={Share2} label={t('luckyDraw.referral')} value="✓" />
                    )}
                  </div>
                </CardContent>
              </Card>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Stat({ icon: Icon, label, value, hidden }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
  hidden?: boolean
}) {
  if (hidden) return null
  return (
    <div className="flex items-center gap-1.5 text-muted-foreground">
      <Icon className="h-4 w-4" />
      <span>{label}: <span className="text-foreground font-medium">{value}</span></span>
    </div>
  )
}
