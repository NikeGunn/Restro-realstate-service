import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { format, parseISO, isToday, isTomorrow, addDays } from 'date-fns'
import { Calendar, Clock, Users, Phone, Mail, Check, X, ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { restaurantApi, organizationsApi, locationsApi } from '@/services/api'
import type { Booking, Organization, Location, BookingStats } from '@/types'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  confirmed: 'bg-green-100 text-green-800 border-green-300',
  cancelled: 'bg-red-100 text-red-800 border-red-300',
  completed: 'bg-blue-100 text-blue-800 border-blue-300',
  no_show: 'bg-gray-100 text-gray-800 border-gray-300',
}

const SOURCE_ICONS: Record<string, string> = {
  website: '🌐',
  whatsapp: '💬',
  phone: '📞',
  walk_in: '🚶',
  other: '📝',
}

export function BookingsPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [selectedOrgId, setSelectedOrgId] = useState<string>('')
  const [selectedLocationId, setSelectedLocationId] = useState<string>('')
  const [bookings, setBookings] = useState<Booking[]>([])
  const [stats, setStats] = useState<BookingStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const [activeTab, setActiveTab] = useState('today')

  // Create booking dialog
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [bookingForm, setBookingForm] = useState({
    booking_date: format(new Date(), 'yyyy-MM-dd'),
    booking_time: '19:00',
    party_size: 2,
    customer_name: '',
    customer_email: '',
    customer_phone: '',
    special_requests: '',
    source: 'phone',
  })

  // Load organizations
  useEffect(() => {
    const loadOrgs = async () => {
      try {
        const data = await organizationsApi.list()
        const restaurantOrgs = data.filter((org: Organization) => org.business_type === 'restaurant')
        setOrganizations(restaurantOrgs)
        if (restaurantOrgs.length > 0) {
          setSelectedOrgId(restaurantOrgs[0].id)
        }
      } catch (error) {
        console.error('Failed to load organizations:', error)
      }
    }
    loadOrgs()
  }, [])

  // Load locations when org changes
  useEffect(() => {
    if (!selectedOrgId) return
    const loadLocations = async () => {
      try {
        const data = await locationsApi.list(selectedOrgId)
        const locationList = Array.isArray(data) ? data : data.results || []
        setLocations(locationList)
        if (locationList.length > 0) {
          setSelectedLocationId(locationList[0].id)
        }
      } catch (error) {
        console.error('Failed to load locations:', error)
      }
    }
    loadLocations()
  }, [selectedOrgId])

  // Load bookings
  const loadBookings = useCallback(async () => {
    if (!selectedOrgId) return
    setLoading(true)
    try {
      let data
      if (activeTab === 'today') {
        data = await restaurantApi.bookings.today({ location: selectedLocationId || undefined })
      } else if (activeTab === 'upcoming') {
        data = await restaurantApi.bookings.upcoming({ location: selectedLocationId || undefined })
      } else {
        data = await restaurantApi.bookings.list({
          organization: selectedOrgId,
          location: selectedLocationId || undefined,
          date: format(selectedDate, 'yyyy-MM-dd'),
        })
      }
      setBookings(Array.isArray(data) ? data : data.results || [])
    } catch (error) {
      console.error('Failed to load bookings:', error)
      toast({ title: 'Error', description: 'Failed to load bookings', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [selectedOrgId, selectedLocationId, activeTab, selectedDate, toast])

  // Load stats
  const loadStats = useCallback(async () => {
    if (!selectedOrgId) return
    try {
      const data = await restaurantApi.bookings.stats({ organization: selectedOrgId })
      setStats(data)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }, [selectedOrgId])

  useEffect(() => {
    loadBookings()
    loadStats()
  }, [loadBookings, loadStats])

  // Booking actions
  const handleConfirm = async (id: string) => {
    try {
      await restaurantApi.bookings.confirm(id)
      toast({ title: 'Success', description: 'Booking confirmed' })
      loadBookings()
      loadStats()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to confirm booking', variant: 'destructive' })
    }
  }

  const handleCancel = async (id: string) => {
    const reason = prompt('Cancellation reason (optional):')
    if (reason === null) return // User clicked cancel
    try {
      await restaurantApi.bookings.cancel(id, reason)
      toast({ title: 'Success', description: 'Booking cancelled' })
      loadBookings()
      loadStats()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to cancel booking', variant: 'destructive' })
    }
  }

  const handleComplete = async (id: string) => {
    try {
      await restaurantApi.bookings.complete(id)
      toast({ title: 'Success', description: 'Booking marked as completed' })
      loadBookings()
      loadStats()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to complete booking', variant: 'destructive' })
    }
  }

  const handleNoShow = async (id: string) => {
    if (!confirm('Mark this booking as no-show?')) return
    try {
      await restaurantApi.bookings.noShow(id)
      toast({ title: 'Success', description: 'Booking marked as no-show' })
      loadBookings()
      loadStats()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update booking', variant: 'destructive' })
    }
  }

  const handleCreateBooking = async () => {
    if (!selectedLocationId) {
      toast({ title: 'Error', description: 'Please select a location', variant: 'destructive' })
      return
    }
    try {
      await restaurantApi.bookings.create({
        organization: selectedOrgId,
        location: selectedLocationId,
        ...bookingForm,
      })
      toast({ title: 'Success', description: 'Booking created successfully' })
      setCreateDialogOpen(false)
      setBookingForm({
        booking_date: format(new Date(), 'yyyy-MM-dd'),
        booking_time: '19:00',
        party_size: 2,
        customer_name: '',
        customer_email: '',
        customer_phone: '',
        special_requests: '',
        source: 'phone',
      })
      loadBookings()
      loadStats()
    } catch (error: any) {
      const message = error.response?.data?.detail || error.response?.data?.booking_time?.[0] || 'Failed to create booking'
      toast({ title: 'Error', description: message, variant: 'destructive' })
    }
  }

  const formatDate = (dateStr: string) => {
    const date = parseISO(dateStr)
    if (isToday(date)) return 'Today'
    if (isTomorrow(date)) return 'Tomorrow'
    return format(date, 'EEE, MMM d')
  }

  if (organizations.length === 0 && !loading) {
    return (
      <div className="p-6">
        <Card className="p-8 text-center">
          <h2 className="text-xl font-semibold mb-2">No Restaurant Organization</h2>
          <p className="text-muted-foreground">Create a restaurant organization first to manage bookings.</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('restaurant.bookings.title')}</h1>
          <p className="text-muted-foreground">{t('restaurant.bookings.subtitle')}</p>
        </div>
        <div className="flex gap-4">
          {locations.length > 1 && (
            <Select value={selectedLocationId} onValueChange={setSelectedLocationId}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="All locations" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All Locations</SelectItem>
                {locations.map(loc => (
                  <SelectItem key={loc.id} value={loc.id}>{loc.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            {t('restaurant.bookings.newBooking')}
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{stats.total}</div>
              <div className="text-sm text-muted-foreground">{t('restaurant.bookings.totalBookings')}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-yellow-600">{stats.by_status?.pending || 0}</div>
              <div className="text-sm text-muted-foreground">{t('restaurant.bookings.pending')}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-600">{stats.by_status?.confirmed || 0}</div>
              <div className="text-sm text-muted-foreground">{t('restaurant.bookings.confirmed')}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-blue-600">{stats.by_status?.completed || 0}</div>
              <div className="text-sm text-muted-foreground">{t('restaurant.bookings.completed')}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{stats.total_guests || 0}</div>
              <div className="text-sm text-muted-foreground">{t('restaurant.bookings.totalGuests')}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="today">{t('restaurant.bookings.today')}</TabsTrigger>
          <TabsTrigger value="upcoming">{t('restaurant.bookings.upcoming')}</TabsTrigger>
          <TabsTrigger value="calendar">{t('restaurant.bookings.calendar')}</TabsTrigger>
        </TabsList>

        <TabsContent value="calendar" className="mt-4">
          <div className="flex items-center gap-4 mb-4">
            <Button variant="outline" size="icon" onClick={() => setSelectedDate(d => addDays(d, -1))}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="font-medium">{format(selectedDate, 'EEEE, MMMM d, yyyy')}</div>
            <Button variant="outline" size="icon" onClick={() => setSelectedDate(d => addDays(d, 1))}>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button variant="outline" onClick={() => setSelectedDate(new Date())}>{t('restaurant.bookings.today')}</Button>
          </div>
        </TabsContent>
      </Tabs>

      {/* Bookings List */}
      {loading ? (
        <Card className="p-8 text-center">Loading bookings...</Card>
      ) : bookings.length === 0 ? (
        <Card className="p-8 text-center">
          <h3 className="text-lg font-semibold mb-2">{t('restaurant.bookings.noBookingsFound')}</h3>
          <p className="text-muted-foreground">
            {activeTab === 'today' ? t('restaurant.bookings.noBookingsToday') : t('restaurant.bookings.noBookingsUpcoming')}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {bookings.map(booking => (
            <Card key={booking.id} className="overflow-hidden">
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold text-lg">{booking.customer_name}</h3>
                      <Badge className={STATUS_COLORS[booking.status]}>{booking.status_display}</Badge>
                      <span title={booking.source_display}>{SOURCE_ICONS[booking.source] || '📝'}</span>
                    </div>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div className="flex items-center gap-2">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <span>{formatDate(booking.booking_date)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <span>{booking.booking_time.slice(0, 5)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-muted-foreground" />
                        <span>{booking.party_size} {t('restaurant.bookings.guests')}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Phone className="h-4 w-4 text-muted-foreground" />
                        <span>{booking.customer_phone}</span>
                      </div>
                    </div>

                    {booking.special_requests && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        📝 {booking.special_requests}
                      </p>
                    )}

                    <div className="mt-2 text-xs text-muted-foreground">
                      Confirmation: <span className="font-mono">{booking.confirmation_code}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 ml-4">
                    {booking.status === 'pending' && (
                      <>
                        <Button size="sm" onClick={() => handleConfirm(booking.id)}>
                          <Check className="h-4 w-4 mr-1" />
                          Confirm
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => handleCancel(booking.id)}>
                          <X className="h-4 w-4 mr-1" />
                          Cancel
                        </Button>
                      </>
                    )}
                    {booking.status === 'confirmed' && (
                      <>
                        <Button size="sm" onClick={() => handleComplete(booking.id)}>
                          <Check className="h-4 w-4 mr-1" />
                          Complete
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleNoShow(booking.id)}>
                          No Show
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => handleCancel(booking.id)}>
                          Cancel
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Booking Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create New Booking</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Date</Label>
                <Input
                  type="date"
                  value={bookingForm.booking_date}
                  onChange={e => setBookingForm(prev => ({ ...prev, booking_date: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Time</Label>
                <Input
                  type="time"
                  value={bookingForm.booking_time}
                  onChange={e => setBookingForm(prev => ({ ...prev, booking_time: e.target.value }))}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Party Size</Label>
              <Input
                type="number"
                min={1}
                max={50}
                value={bookingForm.party_size}
                onChange={e => setBookingForm(prev => ({ ...prev, party_size: parseInt(e.target.value) || 1 }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Customer Name</Label>
              <Input
                value={bookingForm.customer_name}
                onChange={e => setBookingForm(prev => ({ ...prev, customer_name: e.target.value }))}
                placeholder="John Doe"
              />
            </div>
            <div className="space-y-2">
              <Label>Phone</Label>
              <Input
                value={bookingForm.customer_phone}
                onChange={e => setBookingForm(prev => ({ ...prev, customer_phone: e.target.value }))}
                placeholder="(555) 123-4567"
              />
            </div>
            <div className="space-y-2">
              <Label>Email (optional)</Label>
              <Input
                type="email"
                value={bookingForm.customer_email}
                onChange={e => setBookingForm(prev => ({ ...prev, customer_email: e.target.value }))}
                placeholder="john@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label>Source</Label>
              <Select
                value={bookingForm.source}
                onValueChange={value => setBookingForm(prev => ({ ...prev, source: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="phone">📞 Phone</SelectItem>
                  <SelectItem value="walk_in">🚶 Walk-in</SelectItem>
                  <SelectItem value="website">🌐 Website</SelectItem>
                  <SelectItem value="other">📝 Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Special Requests (optional)</Label>
              <Textarea
                value={bookingForm.special_requests}
                onChange={e => setBookingForm(prev => ({ ...prev, special_requests: e.target.value }))}
                placeholder="Any special requests or notes..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateBooking}>Create Booking</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
