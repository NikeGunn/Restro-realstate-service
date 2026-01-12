import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { format, parseISO, isToday, isTomorrow, addDays } from 'date-fns'
import { Calendar, Clock, Users, Phone, Mail, Check, X, ChevronLeft, ChevronRight, Plus, ChevronDown } from 'lucide-react'
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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

const SOURCE_OPTIONS = [
  { value: 'phone', label: 'Phone Call', icon: '📞' },
  { value: 'walk_in', label: 'Walk-in', icon: '🚶' },
  { value: 'website', label: 'Website', icon: '🌐' },
  { value: 'whatsapp', label: 'WhatsApp', icon: '💬' },
  { value: 'other', label: 'Other', icon: '📝' },
]

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
  const [sourceDropdownOpen, setSourceDropdownOpen] = useState(false)

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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <Card className="border-l-4 border-l-slate-500 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-3xl font-bold tracking-tight">{stats.total}</div>
                  <div className="text-sm font-medium text-muted-foreground mt-1">Total Bookings</div>
                </div>
                <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center">
                  <Calendar className="h-6 w-6 text-slate-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-3xl font-bold text-amber-600 tracking-tight">{stats.by_status?.pending || 0}</div>
                  <div className="text-sm font-medium text-muted-foreground mt-1">Pending</div>
                </div>
                <div className="h-12 w-12 rounded-full bg-amber-100 flex items-center justify-center">
                  <Clock className="h-6 w-6 text-amber-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-emerald-500 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-3xl font-bold text-emerald-600 tracking-tight">{stats.by_status?.confirmed || 0}</div>
                  <div className="text-sm font-medium text-muted-foreground mt-1">Confirmed</div>
                </div>
                <div className="h-12 w-12 rounded-full bg-emerald-100 flex items-center justify-center">
                  <Check className="h-6 w-6 text-emerald-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-blue-500 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-3xl font-bold text-blue-600 tracking-tight">{stats.by_status?.completed || 0}</div>
                  <div className="text-sm font-medium text-muted-foreground mt-1">Completed</div>
                </div>
                <div className="h-12 w-12 rounded-full bg-blue-100 flex items-center justify-center">
                  <Check className="h-6 w-6 text-blue-600" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-purple-500 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-3xl font-bold text-purple-600 tracking-tight">{stats.total_guests || 0}</div>
                  <div className="text-sm font-medium text-muted-foreground mt-1">Total Guests</div>
                </div>
                <div className="h-12 w-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Users className="h-6 w-6 text-purple-600" />
                </div>
              </div>
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
        <Card className="p-8 text-center">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
        </Card>
      ) : bookings.length === 0 ? (
        <Card className="p-12 text-center border-dashed border-2">
          <div className="mx-auto w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
            <Calendar className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold mb-2">{t('restaurant.bookings.noBookingsFound')}</h3>
          <p className="text-muted-foreground mb-4">
            {activeTab === 'today' ? t('restaurant.bookings.noBookingsToday') : t('restaurant.bookings.noBookingsUpcoming')}
          </p>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create First Booking
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {bookings.map(booking => (
            <Card key={booking.id} className="overflow-hidden hover:shadow-lg transition-all duration-200 border-l-4" 
                  style={{ borderLeftColor: booking.status === 'confirmed' ? '#10b981' : booking.status === 'pending' ? '#f59e0b' : booking.status === 'completed' ? '#3b82f6' : '#6b7280' }}>
              <CardContent className="p-6">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* Main Info Section */}
                  <div className="flex-1 space-y-4">
                    {/* Header Row */}
                    <div className="flex items-center gap-3 flex-wrap">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold text-lg">
                          {booking.customer_name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <h3 className="font-semibold text-lg leading-tight">{booking.customer_name}</h3>
                          {booking.customer_email && (
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              <Mail className="h-3 w-3" />
                              {booking.customer_email}
                            </p>
                          )}
                        </div>
                      </div>
                      <Badge className={`${STATUS_COLORS[booking.status]} font-medium px-3 py-1`}>
                        {booking.status_display}
                      </Badge>
                      <span className="text-xl" title={booking.source_display}>
                        {SOURCE_ICONS[booking.source] || '📝'}
                      </span>
                    </div>
                    
                    {/* Info Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                      <div className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2">
                        <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                          <Calendar className="h-4 w-4 text-blue-600" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs text-muted-foreground font-medium">Date</div>
                          <div className="text-sm font-semibold truncate">{formatDate(booking.booking_date)}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2">
                        <div className="h-8 w-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                          <Clock className="h-4 w-4 text-amber-600" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs text-muted-foreground font-medium">Time</div>
                          <div className="text-sm font-semibold truncate">{booking.booking_time.slice(0, 5)}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2">
                        <div className="h-8 w-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                          <Users className="h-4 w-4 text-purple-600" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs text-muted-foreground font-medium">Party Size</div>
                          <div className="text-sm font-semibold truncate">{booking.party_size} {booking.party_size === 1 ? 'guest' : 'guests'}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2">
                        <div className="h-8 w-8 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
                          <Phone className="h-4 w-4 text-emerald-600" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs text-muted-foreground font-medium">Contact</div>
                          <div className="text-sm font-semibold truncate">{booking.customer_phone}</div>
                        </div>
                      </div>
                    </div>

                    {/* Special Requests */}
                    {booking.special_requests && (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <span className="text-lg">📝</span>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-semibold text-amber-900 mb-1">Special Requests</div>
                            <p className="text-sm text-amber-800 leading-relaxed">{booking.special_requests}</p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Confirmation Code */}
                    <div className="flex items-center gap-2 pt-2 border-t">
                      <span className="text-xs font-medium text-muted-foreground">Confirmation:</span>
                      <code className="px-2 py-1 bg-muted rounded text-xs font-mono font-semibold tracking-wider">
                        {booking.confirmation_code}
                      </code>
                    </div>
                  </div>

                  {/* Actions Section */}
                  <div className="flex lg:flex-col gap-2 flex-wrap lg:flex-nowrap">
                    {booking.status === 'pending' && (
                      <>
                        <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 flex-1 lg:flex-none lg:w-32" onClick={() => handleConfirm(booking.id)}>
                          <Check className="h-4 w-4 mr-1" />
                          Confirm
                        </Button>
                        <Button size="sm" variant="destructive" className="flex-1 lg:flex-none lg:w-32" onClick={() => handleCancel(booking.id)}>
                          <X className="h-4 w-4 mr-1" />
                          Cancel
                        </Button>
                      </>
                    )}
                    {booking.status === 'confirmed' && (
                      <>
                        <Button size="sm" className="bg-blue-600 hover:bg-blue-700 flex-1 lg:flex-none lg:w-32" onClick={() => handleComplete(booking.id)}>
                          <Check className="h-4 w-4 mr-1" />
                          Complete
                        </Button>
                        <Button size="sm" variant="outline" className="flex-1 lg:flex-none lg:w-32" onClick={() => handleNoShow(booking.id)}>
                          No Show
                        </Button>
                        <Button size="sm" variant="destructive" className="flex-1 lg:flex-none lg:w-32" onClick={() => handleCancel(booking.id)}>
                          Cancel
                        </Button>
                      </>
                    )}
                    {(booking.status === 'completed' || booking.status === 'cancelled' || booking.status === 'no_show') && (
                      <div className="flex-1 lg:flex-none lg:w-32 text-center lg:text-left">
                        <Badge variant="outline" className="w-full justify-center">
                          {booking.status === 'completed' && '✓ Completed'}
                          {booking.status === 'cancelled' && '✕ Cancelled'}
                          {booking.status === 'no_show' && '⊘ No Show'}
                        </Badge>
                      </div>
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
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader className="pb-4 border-b flex-shrink-0">
            <DialogTitle className="text-2xl font-bold flex items-center gap-2">
              <div className="h-10 w-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                <Plus className="h-5 w-5 text-white" />
              </div>
              Create New Booking
            </DialogTitle>
            <p className="text-sm text-muted-foreground mt-2">Fill in the details to create a new table reservation</p>
          </DialogHeader>
          
          <div className="space-y-6 py-6 overflow-y-auto flex-1">
            {/* Booking Date & Time Section */}
            <div className="space-y-4 px-1">
              <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                <Calendar className="h-4 w-4" />
                Reservation Details
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-2 sm:col-span-2">
                  <Label className="text-sm font-medium">Booking Date *</Label>
                  <Input
                    type="date"
                    className="h-11"
                    value={bookingForm.booking_date}
                    onChange={e => setBookingForm(prev => ({ ...prev, booking_date: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Time *</Label>
                  <Input
                    type="time"
                    className="h-11"
                    value={bookingForm.booking_time}
                    onChange={e => setBookingForm(prev => ({ ...prev, booking_time: e.target.value }))}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium">Party Size *</Label>
                <Input
                  type="number"
                  className="h-11"
                  min={1}
                  max={50}
                  value={bookingForm.party_size}
                  onChange={e => setBookingForm(prev => ({ ...prev, party_size: parseInt(e.target.value) || 1 }))}
                />
                <p className="text-xs text-muted-foreground">Number of guests (1-50)</p>
              </div>
            </div>

            {/* Customer Information Section */}
            <div className="space-y-4 pt-4 border-t px-1">
              <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                <Users className="h-4 w-4" />
                Customer Information
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium">Full Name *</Label>
                <Input
                  className="h-11"
                  value={bookingForm.customer_name}
                  onChange={e => setBookingForm(prev => ({ ...prev, customer_name: e.target.value }))}
                  placeholder="e.g., John Doe"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Phone Number *</Label>
                  <div className="relative">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-11 pl-10"
                      value={bookingForm.customer_phone}
                      onChange={e => setBookingForm(prev => ({ ...prev, customer_phone: e.target.value }))}
                      placeholder="(555) 123-4567"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Email Address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      type="email"
                      className="h-11 pl-10"
                      value={bookingForm.customer_email}
                      onChange={e => setBookingForm(prev => ({ ...prev, customer_email: e.target.value }))}
                      placeholder="john@example.com"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">Optional</p>
                </div>
              </div>
            </div>

            {/* Additional Details Section */}
            <div className="space-y-4 pt-4 border-t px-1">
              <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                <Clock className="h-4 w-4" />
                Additional Details
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium">Booking Source</Label>
                <DropdownMenu open={sourceDropdownOpen} onOpenChange={setSourceDropdownOpen}>
                  <DropdownMenuTrigger asChild>
                    <button
                      className="w-full h-11 flex items-center gap-2 px-3 rounded-md border border-input bg-background text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    >
                      <span className="text-lg">{SOURCE_OPTIONS.find(s => s.value === bookingForm.source)?.icon}</span>
                      <span className="flex-1 text-left">{SOURCE_OPTIONS.find(s => s.value === bookingForm.source)?.label}</span>
                      <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="start"
                    className="w-[var(--radix-dropdown-menu-trigger-width)] bg-background shadow-xl border-2"
                  >
                    {SOURCE_OPTIONS.map((option) => (
                      <DropdownMenuItem
                        key={option.value}
                        onClick={() => {
                          setBookingForm(prev => ({ ...prev, source: option.value }))
                          setSourceDropdownOpen(false)
                        }}
                        className="cursor-pointer flex items-center gap-3 py-2.5 px-3"
                      >
                        <span className="text-lg">{option.icon}</span>
                        <span className="flex-1 font-medium">{option.label}</span>
                        {bookingForm.source === option.value && (
                          <Check className="h-4 w-4 text-primary flex-shrink-0" />
                        )}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium">Special Requests</Label>
                <Textarea
                  className="min-h-[100px] resize-none"
                  value={bookingForm.special_requests}
                  onChange={e => setBookingForm(prev => ({ ...prev, special_requests: e.target.value }))}
                  placeholder="e.g., Window seat, high chair needed, birthday celebration..."
                />
                <p className="text-xs text-muted-foreground">Optional - Any dietary restrictions or special requirements</p>
              </div>
            </div>
          </div>

          <DialogFooter className="pt-4 border-t flex-shrink-0 flex flex-col sm:flex-row gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)} className="w-full sm:w-auto h-11">
              Cancel
            </Button>
            <Button onClick={handleCreateBooking} className="w-full sm:w-auto h-11 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700">
              <Check className="h-4 w-4 mr-2" />
              Create Booking
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
