import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, isToday, isTomorrow, parseISO } from 'date-fns'
import {
  CalendarCheck, CalendarClock, CalendarX, CheckCircle2, Clock, Copy, Home, MapPin, Phone, Plus,
  RefreshCw, Search, UserX, Video, XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { InventoryEmpty, InventoryError, InventoryLoading } from '@/components/inventory/InventoryStates'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/auth'
import { realEstateApi } from '@/services/api'
import type { Appointment, AppointmentStatus, AppointmentType, Lead, PropertyListing } from '@/types'

type View = 'upcoming' | 'today' | 'past' | 'all'
type PendingAction = { kind: 'cancel' | 'complete' | 'no_show'; appt: Appointment } | null

const ACTIVE: AppointmentStatus[] = ['scheduled', 'confirmed']
const TYPES: AppointmentType[] = ['viewing', 'virtual_tour', 'consultation', 'meeting', 'follow_up']

const STATUS_STYLE: Record<string, string> = {
  scheduled: 'bg-amber-100 text-amber-800 border-amber-200',
  confirmed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  completed: 'bg-sky-100 text-sky-800 border-sky-200',
  cancelled: 'bg-gray-100 text-gray-600 border-gray-200',
  no_show: 'bg-rose-100 text-rose-800 border-rose-200',
  rescheduled: 'bg-violet-100 text-violet-800 border-violet-200',
}

const todayIso = () => format(new Date(), 'yyyy-MM-dd')

/** Flatten a DRF error payload ({field: [msg]} | {error} | {detail}) into one readable line. */
function apiErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data.slice(0, 200)
  const obj = data as Record<string, unknown>
  if (typeof obj.error === 'string') return obj.error
  if (typeof obj.detail === 'string') return obj.detail
  const parts = Object.entries(obj).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : String(v)}`)
  return parts.join(' · ') || fallback
}

const EMPTY_FORM = {
  lead: '', property_listing: '', appointment_type: 'viewing' as AppointmentType,
  appointment_date: '', appointment_time: '11:00', duration_minutes: '60', meeting_location: '', notes: '',
}

export function AppointmentsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const qc = useQueryClient()
  const orgId = useAuthStore((s) => s.currentOrganization?.id) ?? ''

  const [view, setView] = useState<View>('upcoming')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [pending, setPending] = useState<PendingAction>(null)
  const [actionNote, setActionNote] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState('')

  const listParams = useMemo(() => {
    const p: Record<string, string> = { organization: orgId }
    if (view === 'today') p.date = todayIso()
    if (view === 'upcoming') p.start_date = todayIso()
    if (view === 'past') p.end_date = todayIso()
    if (statusFilter !== 'all') p.status = statusFilter
    return p
  }, [orgId, view, statusFilter])

  const apptsQuery = useQuery({
    queryKey: ['appointments', listParams],
    queryFn: () => realEstateApi.appointments.list(listParams) as Promise<Appointment[]>,
    enabled: !!orgId,
  })
  const statsQuery = useQuery({
    queryKey: ['appointments-stats', orgId],
    queryFn: () => realEstateApi.appointments.stats({ organization: orgId, days: 30 }),
    enabled: !!orgId,
  })
  const upcomingQuery = useQuery({
    queryKey: ['appointments-upcoming', orgId],
    queryFn: () => realEstateApi.appointments.upcoming({ organization: orgId }) as Promise<Appointment[]>,
    enabled: !!orgId,
  })
  const leadsQuery = useQuery({
    queryKey: ['leads-for-appointments', orgId],
    queryFn: () => realEstateApi.leads.list({ organization: orgId }) as Promise<Lead[]>,
    enabled: !!orgId && createOpen,
  })
  const propsQuery = useQuery({
    queryKey: ['properties-for-appointments', orgId],
    queryFn: () => realEstateApi.properties.list({ organization: orgId }) as Promise<PropertyListing[]>,
    enabled: !!orgId && createOpen,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['appointments'] })
    qc.invalidateQueries({ queryKey: ['appointments-stats'] })
    qc.invalidateQueries({ queryKey: ['appointments-upcoming'] })
  }

  const transition = useMutation({
    mutationFn: async ({ kind, appt, note }: { kind: 'confirm' | 'cancel' | 'complete' | 'no_show'; appt: Appointment; note?: string }) => {
      const api = realEstateApi.appointments
      if (kind === 'confirm') return api.confirm(appt.id)
      if (kind === 'cancel') return api.cancel(appt.id, note)
      if (kind === 'complete') return api.complete(appt.id, note)
      return api.noShow(appt.id)
    },
    onSuccess: (data: Appointment, vars) => {
      // Every staff action is also told to the customer in their chat (and so to the AI agent).
      const via = data?.customer_notified_via
      toast({
        title: t(`realEstate.appointments.toast.${vars.kind}`, { code: vars.appt.confirmation_code }),
        description: via
          ? t('realEstate.appointments.toast.notified', { channel: via })
          : vars.appt.conversation ? t('realEstate.appointments.toast.notNotified') : undefined,
      })
      setPending(null)
      setActionNote('')
      invalidate()
    },
    onError: (err) => {
      toast({ variant: 'destructive', title: t('realEstate.appointments.toast.failed'), description: apiErrorMessage(err, t('common.error')) })
      setPending(null)
      invalidate() // the row may have changed under us (e.g. cancelled by the AI) — refresh it
    },
  })

  const create = useMutation({
    mutationFn: () => realEstateApi.appointments.create({
      organization: orgId,
      lead: form.lead,
      property_listing: form.property_listing || null,
      appointment_type: form.appointment_type,
      appointment_date: form.appointment_date,
      appointment_time: form.appointment_time,
      duration_minutes: Number(form.duration_minutes),
      meeting_location: form.meeting_location.trim(),
      notes: form.notes.trim(),
    }),
    onSuccess: (appt: Appointment) => {
      toast({ title: t('realEstate.appointments.toast.created', { code: appt.confirmation_code }) })
      setCreateOpen(false)
      setForm(EMPTY_FORM)
      invalidate()
    },
    onError: (err) => setFormError(apiErrorMessage(err, t('common.error'))),
  })

  const submitCreate = () => {
    setFormError('')
    if (!form.lead) return setFormError(t('realEstate.appointments.form.errLead'))
    if (!form.appointment_date || !form.appointment_time) return setFormError(t('realEstate.appointments.form.errWhen'))
    const when = new Date(`${form.appointment_date}T${form.appointment_time}`)
    if (Number.isNaN(when.getTime()) || when < new Date()) return setFormError(t('realEstate.appointments.form.errPast'))
    const mins = Number(form.duration_minutes)
    if (!Number.isInteger(mins) || mins < 15 || mins > 480) return setFormError(t('realEstate.appointments.form.errDuration'))
    create.mutate()
  }

  const rows = useMemo(() => {
    const list = apptsQuery.data ?? []
    const q = search.trim().toLowerCase()
    // "Upcoming" means still happening — cancelled/no-show rows live under Past/All or a status filter.
    const scoped = view === 'upcoming' && statusFilter === 'all' ? list.filter((a) => ACTIVE.includes(a.status)) : list
    const filtered = q
      ? scoped.filter((a) => [a.lead_name, a.attendee_name, a.lead_phone, a.confirmation_code, a.property_title]
          .some((v) => (v ?? '').toLowerCase().includes(q)))
      : scoped
    const sorted = [...filtered].sort((a, b) => {
      const ka = `${a.appointment_date} ${a.appointment_time}`
      const kb = `${b.appointment_date} ${b.appointment_time}`
      return view === 'past' ? kb.localeCompare(ka) : ka.localeCompare(kb)
    })
    const groups: { date: string; items: Appointment[] }[] = []
    for (const a of sorted) {
      const last = groups[groups.length - 1]
      if (last && last.date === a.appointment_date) last.items.push(a)
      else groups.push({ date: a.appointment_date, items: [a] })
    }
    return groups
  }, [apptsQuery.data, search, view, statusFilter])

  const stats = statsQuery.data
  const upcomingCount = upcomingQuery.data?.length ?? 0
  const todayCount = (upcomingQuery.data ?? []).filter((a) => a.appointment_date === todayIso()).length

  const dateLabel = (iso: string) => {
    const d = parseISO(iso)
    if (isToday(d)) return `${t('realEstate.appointments.today')} · ${format(d, 'EEE d MMM')}`
    if (isTomorrow(d)) return `${t('realEstate.appointments.tomorrow')} · ${format(d, 'EEE d MMM')}`
    return format(d, 'EEEE, d MMM yyyy')
  }

  const copyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code)
      toast({ title: t('realEstate.appointments.toast.copied', { code }) })
    } catch {
      toast({ variant: 'destructive', title: t('common.error') })
    }
  }

  if (!orgId) {
    return <InventoryEmpty icon={CalendarClock} message={t('realEstate.appointments.noOrg')} />
  }

  const statCards = [
    { icon: CalendarCheck, label: t('realEstate.appointments.stats.today'), value: todayCount, tone: 'text-emerald-600 bg-emerald-50' },
    { icon: CalendarClock, label: t('realEstate.appointments.stats.next7'), value: upcomingCount, tone: 'text-sky-600 bg-sky-50' },
    { icon: CheckCircle2, label: t('realEstate.appointments.stats.completion'), value: stats ? `${stats.completion_rate}%` : '—', tone: 'text-violet-600 bg-violet-50' },
    { icon: UserX, label: t('realEstate.appointments.stats.noShow'), value: stats ? `${stats.no_show_rate}%` : '—', tone: 'text-rose-600 bg-rose-50' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('realEstate.appointments.title')}</h1>
          <p className="text-muted-foreground">{t('realEstate.appointments.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={invalidate} aria-label={t('common.refresh')}
                  disabled={apptsQuery.isFetching}>
            <RefreshCw className={`h-4 w-4 ${apptsQuery.isFetching ? 'animate-spin' : ''}`} />
          </Button>
          <Button onClick={() => { setForm({ ...EMPTY_FORM, appointment_date: todayIso() }); setFormError(''); setCreateOpen(true) }}>
            <Plus className="mr-2 h-4 w-4" />{t('realEstate.appointments.new')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {statCards.map(({ icon: Icon, label, value, tone }) => (
          <Card key={label}>
            <CardContent className="flex items-center gap-3 p-4">
              <div className={`rounded-lg p-2 ${tone}`}><Icon className="h-5 w-5" /></div>
              <div className="min-w-0">
                <p className="truncate text-xs text-muted-foreground">{label}</p>
                <p className="text-xl font-semibold tabular-nums">{value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList>
            {(['upcoming', 'today', 'past', 'all'] as View[]).map((v) => (
              <TabsTrigger key={v} value={v}>{t(`realEstate.appointments.view.${v}`)}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input className="pl-8 sm:w-64" value={search} maxLength={100}
                   placeholder={t('realEstate.appointments.searchPlaceholder')}
                   onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="sm:w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('realEstate.appointments.allStatuses')}</SelectItem>
              {(['scheduled', 'confirmed', 'completed', 'cancelled', 'no_show'] as AppointmentStatus[]).map((s) => (
                <SelectItem key={s} value={s}>{t(`realEstate.appointments.status.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {apptsQuery.isLoading ? (
        <InventoryLoading variant="rows" />
      ) : apptsQuery.isError ? (
        <InventoryError message={apiErrorMessage(apptsQuery.error, t('common.error'))} onRetry={() => apptsQuery.refetch()} />
      ) : rows.length === 0 ? (
        <InventoryEmpty icon={CalendarX} message={search ? t('realEstate.appointments.noMatch') : t(`realEstate.appointments.empty.${view}`)} />
      ) : (
        <div className="space-y-6">
          {rows.map((group) => (
            <section key={group.date} className="space-y-2">
              <h2 className="text-sm font-semibold text-muted-foreground">{dateLabel(group.date)}</h2>
              <div className="space-y-2">
                {group.items.map((a) => {
                  const active = ACTIVE.includes(a.status)
                  const busy = transition.isPending && transition.variables?.appt.id === a.id
                  return (
                    <Card key={a.id} className={active ? '' : 'opacity-80'}>
                      <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center">
                        <div className="flex w-24 shrink-0 items-center gap-2 md:flex-col md:items-start md:gap-0">
                          <span className="text-lg font-semibold tabular-nums">{a.appointment_time.slice(0, 5)}</span>
                          <span className="text-xs text-muted-foreground">
                            <Clock className="mr-1 inline h-3 w-3" />{a.duration_minutes} {t('realEstate.appointments.min')}
                          </span>
                        </div>

                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">
                              {a.attendee_name || a.lead_name || t('realEstate.appointments.unknownLead')}
                            </span>
                            {a.attendee_name && a.lead_name && a.attendee_name.toLowerCase() !== a.lead_name.toLowerCase() && (
                              <span className="text-xs text-muted-foreground">
                                {t('realEstate.appointments.bookedBy', { name: a.lead_name })}
                              </span>
                            )}
                            <Badge variant="outline" className={STATUS_STYLE[a.status] ?? ''}>
                              {t(`realEstate.appointments.status.${a.status}`, { defaultValue: a.status_display })}
                            </Badge>
                            <Badge variant="secondary" className="gap-1">
                              {a.appointment_type === 'virtual_tour' ? <Video className="h-3 w-3" /> : <Home className="h-3 w-3" />}
                              {t(`realEstate.appointments.type.${a.appointment_type}`, { defaultValue: a.appointment_type_display })}
                            </Badge>
                            {a.conversation && (
                              <Badge variant="outline" className="border-violet-200 text-violet-700">{t('realEstate.appointments.bookedByAi')}</Badge>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                            {a.lead_phone && (
                              <a href={`tel:${a.lead_phone}`} className="inline-flex items-center gap-1 hover:text-foreground">
                                <Phone className="h-3.5 w-3.5" />{a.lead_phone}
                              </a>
                            )}
                            <span className="inline-flex min-w-0 items-center gap-1">
                              <MapPin className="h-3.5 w-3.5 shrink-0" />
                              <span className="truncate">{a.property_title || a.meeting_location || t('realEstate.appointments.noProperty')}</span>
                            </span>
                            <button type="button" onClick={() => copyCode(a.confirmation_code)}
                                    className="inline-flex items-center gap-1 font-mono text-xs hover:text-foreground">
                              <Copy className="h-3 w-3" />{a.confirmation_code}
                            </button>
                          </div>
                          {(a.notes || a.outcome || a.cancellation_reason) && (
                            <p className="line-clamp-2 text-xs text-muted-foreground">
                              {a.outcome || a.cancellation_reason || a.notes}
                            </p>
                          )}
                        </div>

                        {active && (
                          <div className="flex flex-wrap gap-2 md:justify-end">
                            {a.status === 'scheduled' && (
                              <Button size="sm" variant="outline" disabled={busy}
                                      onClick={() => transition.mutate({ kind: 'confirm', appt: a })}>
                                <CalendarCheck className="mr-1 h-4 w-4" />{t('realEstate.appointments.action.confirm')}
                              </Button>
                            )}
                            <Button size="sm" disabled={busy} onClick={() => { setActionNote(''); setPending({ kind: 'complete', appt: a }) }}>
                              <CheckCircle2 className="mr-1 h-4 w-4" />{t('realEstate.appointments.action.complete')}
                            </Button>
                            <Button size="sm" variant="outline" disabled={busy} onClick={() => setPending({ kind: 'no_show', appt: a })}>
                              <UserX className="mr-1 h-4 w-4" />{t('realEstate.appointments.action.noShow')}
                            </Button>
                            <Button size="sm" variant="ghost" className="text-destructive" disabled={busy}
                                    onClick={() => { setActionNote(''); setPending({ kind: 'cancel', appt: a }) }}>
                              <XCircle className="mr-1 h-4 w-4" />{t('realEstate.appointments.action.cancel')}
                            </Button>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* Transition confirmation (cancel / complete / no-show) */}
      <Dialog open={!!pending} onOpenChange={(o) => { if (!o && !transition.isPending) setPending(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{pending && t(`realEstate.appointments.dialog.${pending.kind}.title`)}</DialogTitle>
            <DialogDescription>
              {pending && t(`realEstate.appointments.dialog.${pending.kind}.body`, {
                name: pending.appt.lead_name, code: pending.appt.confirmation_code,
                when: `${pending.appt.appointment_date} ${pending.appt.appointment_time.slice(0, 5)}`,
              })}
            </DialogDescription>
          </DialogHeader>
          {pending && pending.kind !== 'no_show' && (
            <div className="space-y-2">
              <Label htmlFor="appt-note">{t(`realEstate.appointments.dialog.${pending.kind}.noteLabel`)}</Label>
              <Textarea id="appt-note" value={actionNote} maxLength={pending.kind === 'cancel' ? 1000 : 2000}
                        onChange={(e) => setActionNote(e.target.value)}
                        placeholder={t(`realEstate.appointments.dialog.${pending.kind}.notePlaceholder`)} />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPending(null)} disabled={transition.isPending}>{t('common.cancel')}</Button>
            <Button variant={pending?.kind === 'cancel' ? 'destructive' : 'default'} disabled={transition.isPending}
                    onClick={() => pending && transition.mutate({ kind: pending.kind, appt: pending.appt, note: actionNote.trim() })}>
              {transition.isPending ? t('common.saving') : t('common.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create appointment */}
      <Dialog open={createOpen} onOpenChange={(o) => { if (!create.isPending) setCreateOpen(o) }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('realEstate.appointments.new')}</DialogTitle>
            <DialogDescription>{t('realEstate.appointments.form.subtitle')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="space-y-2">
              <Label>{t('realEstate.appointments.form.lead')} *</Label>
              <Select value={form.lead} onValueChange={(v) => setForm({ ...form, lead: v })}>
                <SelectTrigger><SelectValue placeholder={leadsQuery.isLoading ? t('common.loading') : t('realEstate.appointments.form.leadPlaceholder')} /></SelectTrigger>
                <SelectContent>
                  {(leadsQuery.data ?? []).length === 0 && !leadsQuery.isLoading && (
                    <div className="px-2 py-1.5 text-sm text-muted-foreground">{t('realEstate.appointments.form.noLeads')}</div>
                  )}
                  {(leadsQuery.data ?? []).map((l) => (
                    <SelectItem key={l.id} value={l.id}>{l.name}{l.phone ? ` · ${l.phone}` : ''}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t('realEstate.appointments.form.property')}</Label>
              <Select value={form.property_listing || 'none'} onValueChange={(v) => setForm({ ...form, property_listing: v === 'none' ? '' : v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t('realEstate.appointments.form.noProperty')}</SelectItem>
                  {(propsQuery.data ?? []).map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.title} · {p.reference_number}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>{t('realEstate.appointments.form.type')}</Label>
                <Select value={form.appointment_type} onValueChange={(v) => setForm({ ...form, appointment_type: v as AppointmentType })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TYPES.map((ty) => <SelectItem key={ty} value={ty}>{t(`realEstate.appointments.type.${ty}`)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="appt-dur">{t('realEstate.appointments.form.duration')}</Label>
                <Input id="appt-dur" type="number" min={15} max={480} step={15} value={form.duration_minutes}
                       onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="appt-date">{t('realEstate.appointments.form.date')} *</Label>
                <Input id="appt-date" type="date" min={todayIso()} value={form.appointment_date}
                       onChange={(e) => setForm({ ...form, appointment_date: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="appt-time">{t('realEstate.appointments.form.time')} *</Label>
                <Input id="appt-time" type="time" step={900} value={form.appointment_time}
                       onChange={(e) => setForm({ ...form, appointment_time: e.target.value })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="appt-loc">{t('realEstate.appointments.form.meetingLocation')}</Label>
              <Input id="appt-loc" maxLength={500} value={form.meeting_location}
                     onChange={(e) => setForm({ ...form, meeting_location: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="appt-notes">{t('realEstate.appointments.form.notes')}</Label>
              <Textarea id="appt-notes" maxLength={2000} value={form.notes}
                        onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            {formError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{formError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={create.isPending}>{t('common.cancel')}</Button>
            <Button onClick={submitCreate} disabled={create.isPending}>
              {create.isPending ? t('common.saving') : t('realEstate.appointments.form.submit')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
