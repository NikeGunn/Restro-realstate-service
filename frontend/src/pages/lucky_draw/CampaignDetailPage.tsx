import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Play, Pause, Square, Pencil, Plus, Download, QrCode, Ticket,
} from 'lucide-react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'

import {
  luckyDrawApi, type LuckyDrawCampaign, type CampaignStats,
  type LuckyDrawQRCode, type LuckyDrawEntry, type CampaignStatus,
} from '@/services/lucky_draw'
import {
  InventoryError as ErrorState,
  InventoryLoading as Loading,
} from '@/components/inventory/InventoryStates'

const PIE_COLORS = ['#6366F1', '#22C55E', '#F59E0B', '#EF4444', '#06B6D4', '#A855F7']
const STATUS_VARIANT: Record<CampaignStatus, string> = {
  draft: 'bg-slate-200 text-slate-700',
  active: 'bg-emerald-100 text-emerald-700',
  paused: 'bg-amber-100 text-amber-700',
  ended: 'bg-rose-100 text-rose-700',
}

export function CampaignDetailPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { toast } = useToast()
  const { id } = useParams<{ id: string }>()

  const [campaign, setCampaign] = useState<LuckyDrawCampaign | null>(null)
  const [stats, setStats] = useState<CampaignStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [c, s] = await Promise.all([
        luckyDrawApi.getCampaign(id),
        luckyDrawApi.stats(id),
      ])
      setCampaign(c)
      setStats(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const transition = async (fn: (id: string) => Promise<LuckyDrawCampaign>) => {
    if (!id) return
    try {
      await fn(id)
      load()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  if (loading) return <Loading variant="cards" count={4} />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!campaign || !stats) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Button variant="ghost" size="icon" onClick={() => navigate('/lucky-draw')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-semibold">{campaign.name}</h1>
        <Badge className={STATUS_VARIANT[campaign.status]}>
          {t(`luckyDraw.status.${campaign.status}`)}
        </Badge>
        <div className="ml-auto flex gap-2">
          {campaign.status !== 'active' && (
            <Button size="sm" onClick={() => transition(luckyDrawApi.activate)}>
              <Play className="h-4 w-4 mr-1" />{t('luckyDraw.activate')}
            </Button>
          )}
          {campaign.status === 'active' && (
            <Button size="sm" variant="outline" onClick={() => transition(luckyDrawApi.pause)}>
              <Pause className="h-4 w-4 mr-1" />{t('luckyDraw.pause')}
            </Button>
          )}
          {campaign.status !== 'ended' && (
            <Button size="sm" variant="outline" onClick={() => transition(luckyDrawApi.end)}>
              <Square className="h-4 w-4 mr-1" />{t('luckyDraw.end')}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => navigate(`/lucky-draw/${campaign.id}/edit`)}>
            <Pencil className="h-4 w-4 mr-1" />{t('common.edit')}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t('luckyDraw.tabs.overview')}</TabsTrigger>
          <TabsTrigger value="prizes">{t('luckyDraw.tabs.prizes')}</TabsTrigger>
          <TabsTrigger value="qr">{t('luckyDraw.tabs.qr')}</TabsTrigger>
          <TabsTrigger value="entries">{t('luckyDraw.tabs.entries')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-3">
          <OverviewTab stats={stats} />
        </TabsContent>
        <TabsContent value="prizes" className="pt-3">
          <PrizesTab campaign={campaign} />
        </TabsContent>
        <TabsContent value="qr" className="pt-3">
          <QrTab campaignId={campaign.id} />
        </TabsContent>
        <TabsContent value="entries" className="pt-3">
          <EntriesTab campaignId={campaign.id} onChange={load} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ── Overview ──────────────────────────────────────────────────────────
function OverviewTab({ stats }: { stats: CampaignStats }) {
  const { t } = useTranslation()
  const f = stats.referral_funnel
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label={t('luckyDraw.stats.scans')} value={stats.total_scans} />
        <Kpi label={t('luckyDraw.stats.entries')} value={stats.total_entries} />
        <Kpi label={t('luckyDraw.stats.uniqueCustomers')} value={stats.unique_customers} />
        <Kpi label={t('luckyDraw.stats.redeemed')} value={stats.redeemed_count} />
        <Kpi label={t('luckyDraw.stats.deliveryRate')}
          value={`${Math.round(stats.whatsapp_delivery_rate * 100)}%`} />
        <Kpi label={t('luckyDraw.stats.shared')} value={f.shared} />
        <Kpi label={t('luckyDraw.stats.referred')} value={f.referred_entries} />
        <Kpi label={t('luckyDraw.stats.referralConversion')}
          value={`${Math.round(f.conversion_rate * 100)}%`} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">{t('luckyDraw.stats.prizeDistribution')}</CardTitle></CardHeader>
          <CardContent className="h-64">
            {stats.prize_distribution.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-12">{t('common.noData')}</p>
            ) : (
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={stats.prize_distribution} dataKey="count" nameKey="label"
                    cx="50%" cy="50%" outerRadius={80} label>
                    {stats.prize_distribution.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">{t('luckyDraw.stats.referralFunnel')}</CardTitle></CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer>
              <BarChart data={[
                { stage: t('luckyDraw.stats.entries'), v: f.entries },
                { stage: t('luckyDraw.stats.shared'), v: f.shared },
                { stage: t('luckyDraw.stats.referred'), v: f.referred_entries },
                { stage: t('luckyDraw.stats.redeemed'), v: f.referred_redeemed },
              ]}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="stage" /><YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="v" fill="#6366F1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  )
}

// ── Prizes ────────────────────────────────────────────────────────────
function PrizesTab({ campaign }: { campaign: LuckyDrawCampaign }) {
  const { t } = useTranslation()
  const total = campaign.prizes.reduce((s, p) => s + p.weight, 0)
  return (
    <Card>
      <CardContent className="py-4 space-y-2">
        {campaign.prizes.map((p) => {
          const pct = total ? Math.round((p.weight / total) * 100) : 0
          return (
            <div key={p.id} className="flex items-center gap-3">
              <div className="w-32 font-medium">{p.label || `${p.discount_percent}%`}</div>
              <div className="flex-1 bg-muted rounded-full h-3 overflow-hidden">
                <div className="bg-primary h-full" style={{ width: `${pct}%` }} />
              </div>
              <div className="w-16 text-right text-sm text-muted-foreground">{pct}%</div>
              <div className="w-28 text-right text-xs text-muted-foreground">
                {t('luckyDraw.stats.wins')}: {p.wins_total_count}
              </div>
            </div>
          )
        })}
        <p className="text-xs text-muted-foreground pt-2">{t('luckyDraw.form.editPrizesHint')}</p>
      </CardContent>
    </Card>
  )
}

// ── QR codes ──────────────────────────────────────────────────────────
function QrTab({ campaignId }: { campaignId: string }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [codes, setCodes] = useState<LuckyDrawQRCode[]>([])
  const [loading, setLoading] = useState(true)
  const [label, setLabel] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setCodes(await luckyDrawApi.listQrCodes(campaignId)) }
    finally { setLoading(false) }
  }, [campaignId])
  useEffect(() => { refresh() }, [refresh])

  const create = async () => {
    try {
      await luckyDrawApi.createQrCode(campaignId, label)
      setLabel('')
      refresh()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  if (loading) return <Loading variant="cards" count={2} />

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input placeholder={t('luckyDraw.qr.labelPlaceholder')} value={label}
          onChange={(e) => setLabel(e.target.value)} className="max-w-xs" />
        <Button onClick={create}><Plus className="h-4 w-4 mr-1" />{t('luckyDraw.qr.create')}</Button>
      </div>
      {codes.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">{t('common.noData')}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {codes.map((qr) => (
            <Card key={qr.id}>
              <CardContent className="py-4 space-y-3 text-center">
                <div className="font-medium flex items-center justify-center gap-1">
                  <QrCode className="h-4 w-4" />{qr.label || t('luckyDraw.qr.untitled')}
                </div>
                {qr.qr_image && (
                  <img src={qr.qr_image} alt="QR" className="mx-auto w-40 h-40" />
                )}
                <div className="text-xs text-muted-foreground break-all">{qr.entry_url}</div>
                <div className="text-sm">{t('luckyDraw.qr.scans')}: {qr.scan_count}</div>
                <div className="flex justify-center gap-2">
                  {qr.qr_image && (
                    <a href={qr.qr_image} download>
                      <Button variant="outline" size="sm">
                        <Download className="h-4 w-4 mr-1" />{t('luckyDraw.qr.downloadQr')}
                      </Button>
                    </a>
                  )}
                  <a href={luckyDrawApi.posterUrl(campaignId, qr.id)} target="_blank" rel="noreferrer">
                    <Button variant="outline" size="sm">
                      <Download className="h-4 w-4 mr-1" />{t('luckyDraw.qr.poster')}
                    </Button>
                  </a>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Entries + redeem ──────────────────────────────────────────────────
function EntriesTab({ campaignId, onChange }: { campaignId: string; onChange: () => void }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [entries, setEntries] = useState<LuckyDrawEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [code, setCode] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await luckyDrawApi.listEntries(campaignId)
      setEntries(res.results)
    } finally { setLoading(false) }
  }, [campaignId])
  useEffect(() => { refresh() }, [refresh])

  const redeem = async () => {
    if (!code.trim()) return
    try {
      await luckyDrawApi.redeem(code.trim())
      toast({ title: t('luckyDraw.entriesTab.redeemed') })
      setCode('')
      refresh()
      onChange()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input placeholder={t('luckyDraw.entriesTab.couponPlaceholder')} value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())} className="max-w-xs" />
        <Button onClick={redeem}><Ticket className="h-4 w-4 mr-1" />{t('luckyDraw.entriesTab.redeem')}</Button>
      </div>

      {loading ? (
        <Loading variant="rows" />
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">{t('common.noData')}</p>
      ) : (
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left">
              <tr>
                <th className="p-2">{t('luckyDraw.entriesTab.customer')}</th>
                <th className="p-2">{t('luckyDraw.entriesTab.phone')}</th>
                <th className="p-2">{t('luckyDraw.entriesTab.coupon')}</th>
                <th className="p-2">{t('luckyDraw.entriesTab.discount')}</th>
                <th className="p-2">{t('luckyDraw.entriesTab.status')}</th>
                <th className="p-2">WhatsApp</th>
                <th className="p-2">{t('luckyDraw.entriesTab.enteredAt')}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-t">
                  <td className="p-2">{e.customer_name}</td>
                  <td className="p-2">{e.phone || '—'}</td>
                  <td className="p-2 font-mono">{e.coupon_code || '—'}</td>
                  <td className="p-2">{e.prize_discount ? `${e.prize_discount}%` : '—'}</td>
                  <td className="p-2">
                    <Badge variant="outline">{t(`luckyDraw.entryStatus.${e.status}`)}</Badge>
                  </td>
                  <td className="p-2">{e.whatsapp_sent_at ? '✓' : '—'}</td>
                  <td className="p-2 text-muted-foreground">
                    {new Date(e.entered_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
