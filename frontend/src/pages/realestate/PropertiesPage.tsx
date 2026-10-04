import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { Building2, MapPin, Bed, Bath, Maximize, Plus, Edit, Trash2, Star, Eye, Check, Globe } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
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
import { MARKET_OPTIONS, currencySymbol, formatMoney } from '@/lib/money'
import { useToast } from '@/hooks/use-toast'
import { PropertyPhotos } from '@/components/realestate/PropertyPhotos'
import { realEstateApi, organizationsApi } from '@/services/api'
import type { PropertyListing, Organization } from '@/types'

// Must match PropertyListing.Status on the backend (an unknown value is a 400 on save).
const STATUSES = [
  { value: 'active', label: 'Active', color: 'bg-green-100 text-green-800' },
  { value: 'coming_soon', label: 'Coming soon', color: 'bg-sky-100 text-sky-800' },
  { value: 'pending', label: 'Pending', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'rented', label: 'Rented', color: 'bg-purple-100 text-purple-800' },
  { value: 'sold', label: 'Sold', color: 'bg-blue-100 text-blue-800' },
  { value: 'off_market', label: 'Off market', color: 'bg-gray-100 text-gray-800' },
]
const STATUS_COLORS: Record<string, string> = Object.fromEntries(STATUSES.map(s => [s.value, s.color]))

/** DRF field errors -> one readable line ("price: A valid number is required."). */
function saveErrorMessage(error: any): string {
  const data = error?.response?.data
  if (!data) return error?.message ? `Network error: ${error.message}` : 'Failed to save property'
  if (typeof data === 'string') return data.slice(0, 200)
  if (data.detail) return data.detail
  const parts = Object.entries(data).map(([field, msgs]) => {
    const label = field === 'non_field_errors' ? '' : `${field.replace(/_/g, ' ')}: `
    return label + (Array.isArray(msgs) ? msgs.join(' ') : String(msgs))
  })
  return parts.join(' · ') || 'Failed to save property'
}

const PROPERTY_TYPES = [
  { value: 'house', label: 'House' },
  { value: 'apartment', label: 'Apartment / Flat' },
  { value: 'room', label: 'Room' },
  { value: 'condo', label: 'Condo' },
  { value: 'townhouse', label: 'Townhouse' },
  { value: 'land', label: 'Land' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'office', label: 'Office' },
  { value: 'retail', label: 'Shop / Shutter' },
  { value: 'industrial', label: 'Industrial' },
  { value: 'other', label: 'Other' },
]

const LISTING_TYPES = [
  { value: 'sale', label: 'For Sale' },
  { value: 'rent', label: 'For Rent' },
  { value: 'lease', label: 'For Lease' },
]

const INITIAL_FORM = {
  title: '',
  description: '',
  property_type: 'house',
  listing_type: 'sale',
  status: 'active',
  price: '',
  address_line1: '',
  address_line2: '',
  city: '',
  state: '',
  postal_code: '',
  country: '',
  bedrooms: '',
  bathrooms: '',
  square_feet: '',
  lot_size: '',
  year_built: '',
  is_featured: false,
}

export function PropertiesPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrgId, setSelectedOrgId] = useState<string>('')
  const [properties, setProperties] = useState<PropertyListing[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  // Dialog states
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingProperty, setEditingProperty] = useState<PropertyListing | null>(null)
  const [form, setForm] = useState(INITIAL_FORM)
  const [queuedPhotos, setQueuedPhotos] = useState<File[]>([])
  const [saving, setSaving] = useState(false)
  // The agency's market (primary location country) — a listing without its own country uses it.
  const orgCountry = organizations.find((o) => o.id === selectedOrgId)?.locations?.find((l) => l.is_primary)?.country

  // Load organizations
  useEffect(() => {
    const loadOrgs = async () => {
      try {
        const data = await organizationsApi.list()
        const realEstateOrgs = data.filter((org: Organization) => org.business_type === 'real_estate')
        setOrganizations(realEstateOrgs)
        if (realEstateOrgs.length > 0) {
          setSelectedOrgId(realEstateOrgs[0].id)
        }
      } catch (error) {
        console.error('Failed to load organizations:', error)
      }
    }
    loadOrgs()
  }, [])

  // Load properties
  const loadProperties = useCallback(async () => {
    if (!selectedOrgId) return
    setLoading(true)
    try {
      const params: Record<string, any> = { organization: selectedOrgId }
      if (statusFilter !== 'all') params.status = statusFilter
      
      const data = await realEstateApi.properties.list(params)
      setProperties(data)
    } catch (error) {
      console.error('Failed to load properties:', error)
      toast({ title: 'Error', description: 'Failed to load properties', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [selectedOrgId, statusFilter, toast])

  useEffect(() => {
    loadProperties()
  }, [loadProperties])

  const openCreateDialog = () => {
    setEditingProperty(null)
    setForm(INITIAL_FORM)
    setQueuedPhotos([])
    setDialogOpen(true)
  }

  const openEditDialog = async (summary: PropertyListing) => {
    // List rows are a lightweight projection (no description/address) — editing from them
    // would save blanks over real data, so always load the full listing first.
    let property: PropertyListing
    try {
      property = await realEstateApi.properties.get(summary.id)
    } catch (error) {
      toast({ title: 'Error', description: 'Could not load this property for editing', variant: 'destructive' })
      return
    }
    setEditingProperty(property)
    setForm({
      title: property.title,
      description: property.description || '',
      property_type: property.property_type,
      listing_type: property.listing_type,
      status: property.status,
      price: property.price?.toString() || '',
      address_line1: property.address_line1 || '',
      address_line2: property.address_line2 || '',
      city: property.city || '',
      state: property.state || '',
      postal_code: property.postal_code || '',
      country: property.country || orgCountry || '',
      bedrooms: property.bedrooms?.toString() || '',
      bathrooms: property.bathrooms?.toString() || '',
      square_feet: property.square_feet?.toString() || '',
      lot_size: property.lot_size?.toString() || '',
      year_built: property.year_built?.toString() || '',
      is_featured: property.is_featured,
    })
    setDialogOpen(true)
  }

  const handleSubmit = async () => {
    if (!form.title.trim()) {
      toast({ title: 'Error', description: 'Title is required', variant: 'destructive' })
      return
    }
    if (!form.price || parseFloat(form.price) < 0) {
      toast({ title: 'Error', description: 'Enter a price (0 or more)', variant: 'destructive' })
      return
    }
    if (!form.address_line1.trim() || !form.city.trim()) {
      toast({ title: 'Error', description: 'Address and city are required', variant: 'destructive' })
      return
    }

    const payload = {
      organization: selectedOrgId,
      title: form.title,
      description: form.description,
      property_type: form.property_type,
      listing_type: form.listing_type,
      status: form.status,
      price: form.price ? parseFloat(form.price) : null,
      address_line1: form.address_line1,
      address_line2: form.address_line2,
      city: form.city,
      state: form.state,
      postal_code: form.postal_code,
      country: form.country || orgCountry || 'USA',
      bedrooms: form.bedrooms ? parseInt(form.bedrooms) : null,
      bathrooms: form.bathrooms ? parseFloat(form.bathrooms) : null,
      square_feet: form.square_feet ? parseInt(form.square_feet) : null,
      lot_size: form.lot_size ? Math.round(parseFloat(form.lot_size)) : null,
      year_built: form.year_built ? parseInt(form.year_built) : null,
      is_featured: form.is_featured,
    }

    setSaving(true)
    try {
      if (editingProperty) {
        await realEstateApi.properties.update(editingProperty.id, payload)
        toast({ title: 'Success', description: 'Property updated' })
      } else {
        const created = await realEstateApi.properties.create(payload)
        toast({ title: 'Success', description: 'Property created' })
        if (queuedPhotos.length) {
          // The listing exists now; a photo failure must not lose it, so report it separately.
          try {
            const res = await realEstateApi.properties.uploadPhotos(created.id, queuedPhotos)
            if (res.errors.length) toast({ variant: 'destructive', title: 'Some photos were rejected', description: res.errors.join(' · ') })
          } catch {
            toast({ variant: 'destructive', title: 'Listing saved, photos failed', description: 'Open the listing again to add photos.' })
          }
          setQueuedPhotos([])
        }
      }
      setDialogOpen(false)
      loadProperties()
    } catch (error: any) {
      toast({ title: 'Could not save property', description: saveErrorMessage(error), variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this property?')) return
    try {
      await realEstateApi.properties.delete(id)
      toast({ title: 'Success', description: 'Property deleted' })
      loadProperties()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to delete property', variant: 'destructive' })
    }
  }

  const handleMarkSold = async (id: string) => {
    try {
      await realEstateApi.properties.markSold(id, format(new Date(), 'yyyy-MM-dd'))
      toast({ title: 'Success', description: 'Property marked as sold' })
      loadProperties()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update property', variant: 'destructive' })
    }
  }

  const handleToggleFeatured = async (id: string) => {
    try {
      await realEstateApi.properties.toggleFeatured(id)
      loadProperties()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update property', variant: 'destructive' })
    }
  }

  const typeCounts = properties.reduce<Record<string, number>>((acc, p) => {
    acc[p.property_type] = (acc[p.property_type] ?? 0) + 1
    return acc
  }, {})
  const visibleProperties = typeFilter === 'all' ? properties : properties.filter(p => p.property_type === typeFilter)

  const formatPrice = (price: number | string | null, listingType: string, country?: string) => {
    if (!price) return 'Price TBD'
    const formatted = formatMoney(price, country)
    return listingType === 'rent' || listingType === 'lease' ? `${formatted}/mo` : formatted
  }

  if (organizations.length === 0 && !loading) {
    return (
      <div className="p-6">
        <Card className="p-8 text-center">
          <h2 className="text-xl font-semibold mb-2">No Real Estate Organization</h2>
          <p className="text-muted-foreground">Create a real estate organization first to manage properties.</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('realEstate.properties.title')}</h1>
          <p className="text-muted-foreground">{t('realEstate.properties.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <a href="/realestate/properties" target="_blank" rel="noopener">
              <Globe className="h-4 w-4 mr-2" />
              Public page
            </a>
          </Button>
          <Button onClick={openCreateDialog}>
            <Plus className="h-4 w-4 mr-2" />
            Add Property
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-3">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
          </SelectContent>
        </Select>

      </div>

      {/* Type chips with live counts — only types the agency actually has */}
      <div className="flex flex-wrap gap-2 mb-6">
        {[{ value: 'all', label: 'All', count: properties.length },
          ...PROPERTY_TYPES.map(t => ({ ...t, count: typeCounts[t.value] ?? 0 })).filter(t => t.count > 0)]
          .map(t => (
            <Button
              key={t.value}
              size="sm"
              variant={typeFilter === t.value ? 'default' : 'outline'}
              onClick={() => setTypeFilter(t.value)}
            >
              {t.label} <span className="ml-1.5 opacity-70">{t.count}</span>
            </Button>
          ))}
      </div>

      {/* Properties Grid */}
      {loading ? (
        <Card className="p-8 text-center">Loading properties...</Card>
      ) : visibleProperties.length === 0 ? (
        <Card className="p-8 text-center">
          <Building2 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No properties found</h3>
          <p className="text-muted-foreground mb-4">Start by adding your first property listing.</p>
          <Button onClick={openCreateDialog}>
            <Plus className="h-4 w-4 mr-2" />
            Add Property
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {visibleProperties.map(property => (
            <Card key={property.id} className="overflow-hidden hover:shadow-lg transition-shadow">
              {/* Image placeholder */}
              <div className="h-48 bg-gradient-to-br from-gray-100 to-gray-200 relative">
                {property.primary_image ? (
                  <img src={property.primary_image} alt={property.title} loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Building2 className="h-16 w-16 text-gray-400" />
                  </div>
                )}
                {property.is_featured && (
                  <Badge className="absolute top-2 left-2 bg-yellow-500">
                    <Star className="h-3 w-3 mr-1" />
                    Featured
                  </Badge>
                )}
                <Badge className={`absolute top-2 right-2 ${STATUS_COLORS[property.status]}`}>
                  {property.status_display}
                </Badge>
              </div>

              <CardContent className="p-4">
                <div className="mb-2">
                  <h3 className="font-semibold text-lg line-clamp-1">{property.title}</h3>
                  <p className="text-2xl font-bold text-primary">
                    {formatPrice(property.price, property.listing_type, property.country || orgCountry)}
                  </p>
                </div>

                <div className="flex items-center text-sm text-muted-foreground mb-3">
                  <MapPin className="h-4 w-4 mr-1" />
                  <span className="line-clamp-1">
                    {[property.city, property.state].filter(Boolean).join(', ') || 'Address TBD'}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
                  {property.bedrooms && (
                    <span className="flex items-center gap-1">
                      <Bed className="h-4 w-4" />
                      {property.bedrooms} bd
                    </span>
                  )}
                  {property.bathrooms && (
                    <span className="flex items-center gap-1">
                      <Bath className="h-4 w-4" />
                      {property.bathrooms} ba
                    </span>
                  )}
                  {property.square_feet && (
                    <span className="flex items-center gap-1">
                      <Maximize className="h-4 w-4" />
                      {property.square_feet.toLocaleString()} sqft
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
                  <Eye className="h-3 w-3" />
                  <span>{property.view_count || 0} web views</span>
                  <span>•</span>
                  <span>{property.whatsapp_clicks || 0} WhatsApp chats</span>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => openEditDialog(property)}>
                      <Edit className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleToggleFeatured(property.id)}>
                      <Star className={`h-3 w-3 ${property.is_featured ? 'fill-yellow-500 text-yellow-500' : ''}`} />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleDelete(property.id)}>
                      <Trash2 className="h-3 w-3 text-red-500" />
                    </Button>
                  </div>
                  {property.status === 'active' && (
                    <Button size="sm" onClick={() => handleMarkSold(property.id)}>
                      <Check className="h-3 w-3 mr-1" />
                      Mark Sold
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingProperty ? 'Edit Property' : 'Add New Property'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Title */}
            <div className="space-y-2">
              <Label>Title *</Label>
              <Input
                value={form.title}
                onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
                placeholder="Room with balcony near Chabahil Chowk"
              />
            </div>

            {/* Type & Status */}
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Property Type</Label>
                <Select value={form.property_type} onValueChange={v => setForm(prev => ({ ...prev, property_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PROPERTY_TYPES.map(t => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Listing Type</Label>
                <Select value={form.listing_type} onValueChange={v => setForm(prev => ({ ...prev, listing_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {LISTING_TYPES.map(t => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={form.status} onValueChange={v => setForm(prev => ({ ...prev, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Market — defaults to the agency's market (Settings → Market & currency) */}
            <div className="space-y-2">
              <Label>Market / currency</Label>
              <Select
                value={form.country || orgCountry || ''}
                onValueChange={v => setForm(prev => ({ ...prev, country: v }))}
              >
                <SelectTrigger><SelectValue placeholder="Agency default" /></SelectTrigger>
                <SelectContent>
                  {MARKET_OPTIONS.map(m => (
                    <SelectItem key={m.country} value={m.country}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Price */}
            <div className="space-y-2">
              <Label>{form.listing_type === 'rent' || form.listing_type === 'lease' ? 'Monthly rent' : 'Price'}</Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                  {currencySymbol(form.country || orgCountry)}
                </span>
                <Input
                  type="number"
                  className="pl-12"
                  value={form.price}
                  onChange={e => setForm(prev => ({ ...prev, price: e.target.value }))}
                  placeholder="500000"
                />
              </div>
              {form.price && (
                <p className="text-xs text-muted-foreground">
                  {formatMoney(form.price, form.country || orgCountry)}
                  {form.listing_type === 'rent' || form.listing_type === 'lease' ? ' / month' : ''}
                </p>
              )}
            </div>

            {/* Address */}
            <div className="space-y-2">
              <Label>Address</Label>
              <Input
                value={form.address_line1}
                onChange={e => setForm(prev => ({ ...prev, address_line1: e.target.value }))}
                placeholder="Chabahil-7, near the Chowk"
                className="mb-2"
              />
              <Input
                value={form.address_line2}
                onChange={e => setForm(prev => ({ ...prev, address_line2: e.target.value }))}
                placeholder="Floor / landmark (optional)"
              />
            </div>

            <div className="grid grid-cols-4 gap-4">
              <div className="space-y-2 col-span-2">
                <Label>City *</Label>
                <Input
                  value={form.city}
                  onChange={e => setForm(prev => ({ ...prev, city: e.target.value }))}
                  placeholder="Kathmandu"
                />
              </div>
              <div className="space-y-2">
                <Label>Province</Label>
                <Input
                  value={form.state}
                  onChange={e => setForm(prev => ({ ...prev, state: e.target.value }))}
                  placeholder="Bagmati (optional)"
                />
              </div>
              <div className="space-y-2">
                <Label>Postal Code</Label>
                <Input
                  value={form.postal_code}
                  onChange={e => setForm(prev => ({ ...prev, postal_code: e.target.value }))}
                  placeholder="Optional"
                />
              </div>
            </div>

            {/* Property Details */}
            <div className="grid grid-cols-5 gap-4">
              <div className="space-y-2">
                <Label>Bedrooms</Label>
                <Input
                  type="number"
                  value={form.bedrooms}
                  onChange={e => setForm(prev => ({ ...prev, bedrooms: e.target.value }))}
                  placeholder="3"
                />
              </div>
              <div className="space-y-2">
                <Label>Bathrooms</Label>
                <Input
                  type="number"
                  step="0.5"
                  value={form.bathrooms}
                  onChange={e => setForm(prev => ({ ...prev, bathrooms: e.target.value }))}
                  placeholder="2"
                />
              </div>
              <div className="space-y-2">
                <Label>Sq Ft</Label>
                <Input
                  type="number"
                  value={form.square_feet}
                  onChange={e => setForm(prev => ({ ...prev, square_feet: e.target.value }))}
                  placeholder="1500"
                />
              </div>
              <div className="space-y-2">
                <Label>Lot (sq ft)</Label>
                <Input
                  type="number"
                  step="1"
                  value={form.lot_size}
                  onChange={e => setForm(prev => ({ ...prev, lot_size: e.target.value }))}
                  placeholder="1711"
                />
              </div>
              <div className="space-y-2">
                <Label>Year Built</Label>
                <Input
                  type="number"
                  value={form.year_built}
                  onChange={e => setForm(prev => ({ ...prev, year_built: e.target.value }))}
                  placeholder="2010"
                />
              </div>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={form.description}
                onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Describe the property features, neighborhood, etc."
                rows={4}
              />
            </div>

            {/* Featured */}
            <div className="flex items-center space-x-2">
              <Switch
                checked={form.is_featured}
                onCheckedChange={checked => setForm(prev => ({ ...prev, is_featured: checked }))}
              />
              <Label>Featured Property</Label>
            </div>
          </div>
          <PropertyPhotos
            propertyId={editingProperty?.id}
            images={editingProperty?.images || []}
            onChange={images => {
              if (!editingProperty) return
              setEditingProperty(prev => (prev ? { ...prev, images } : prev))
              setProperties(prev => prev.map(p => (p.id === editingProperty.id ? { ...p, primary_image: images[0] ?? null } : p)))
            }}
            queued={queuedPhotos}
            onQueueChange={setQueuedPhotos}
          />

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={saving}>
              {saving ? 'Saving…' : editingProperty ? 'Update' : queuedPhotos.length ? `Create + upload ${queuedPhotos.length} photo${queuedPhotos.length > 1 ? 's' : ''}` : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
