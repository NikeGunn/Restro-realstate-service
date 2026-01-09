import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { Building2, MapPin, Bed, Bath, Maximize, DollarSign, Plus, Edit, Trash2, Star, Eye, Check } from 'lucide-react'
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
import { useToast } from '@/hooks/use-toast'
import { realEstateApi, organizationsApi } from '@/services/api'
import type { PropertyListing, Organization } from '@/types'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800',
  active: 'bg-green-100 text-green-800',
  under_contract: 'bg-yellow-100 text-yellow-800',
  sold: 'bg-blue-100 text-blue-800',
  rented: 'bg-purple-100 text-purple-800',
  inactive: 'bg-red-100 text-red-800',
}

const PROPERTY_TYPES = [
  { value: 'house', label: 'House' },
  { value: 'apartment', label: 'Apartment' },
  { value: 'condo', label: 'Condo' },
  { value: 'townhouse', label: 'Townhouse' },
  { value: 'land', label: 'Land' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'industrial', label: 'Industrial' },
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
  status: 'draft',
  price: '',
  address_line1: '',
  address_line2: '',
  city: '',
  state: '',
  postal_code: '',
  country: 'USA',
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
      if (typeFilter !== 'all') params.property_type = typeFilter
      
      const data = await realEstateApi.properties.list(params)
      setProperties(Array.isArray(data) ? data : data.results || [])
    } catch (error) {
      console.error('Failed to load properties:', error)
      toast({ title: 'Error', description: 'Failed to load properties', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [selectedOrgId, statusFilter, typeFilter, toast])

  useEffect(() => {
    loadProperties()
  }, [loadProperties])

  const openCreateDialog = () => {
    setEditingProperty(null)
    setForm(INITIAL_FORM)
    setDialogOpen(true)
  }

  const openEditDialog = (property: PropertyListing) => {
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
      country: property.country || 'USA',
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
      country: form.country,
      bedrooms: form.bedrooms ? parseInt(form.bedrooms) : null,
      bathrooms: form.bathrooms ? parseFloat(form.bathrooms) : null,
      square_feet: form.square_feet ? parseInt(form.square_feet) : null,
      lot_size: form.lot_size ? parseFloat(form.lot_size) : null,
      year_built: form.year_built ? parseInt(form.year_built) : null,
      is_featured: form.is_featured,
    }

    try {
      if (editingProperty) {
        await realEstateApi.properties.update(editingProperty.id, payload)
        toast({ title: 'Success', description: 'Property updated' })
      } else {
        await realEstateApi.properties.create(payload)
        toast({ title: 'Success', description: 'Property created' })
      }
      setDialogOpen(false)
      loadProperties()
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to save property'
      toast({ title: 'Error', description: message, variant: 'destructive' })
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

  const formatPrice = (price: number | null, listingType: string) => {
    if (!price) return 'Price TBD'
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(price)
    return listingType === 'rent' ? `${formatted}/mo` : formatted
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
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4 mr-2" />
          Add Property
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="under_contract">Under Contract</SelectItem>
            <SelectItem value="sold">Sold</SelectItem>
            <SelectItem value="rented">Rented</SelectItem>
          </SelectContent>
        </Select>

        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            {PROPERTY_TYPES.map(t => (
              <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Properties Grid */}
      {loading ? (
        <Card className="p-8 text-center">Loading properties...</Card>
      ) : properties.length === 0 ? (
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
          {properties.map(property => (
            <Card key={property.id} className="overflow-hidden hover:shadow-lg transition-shadow">
              {/* Image placeholder */}
              <div className="h-48 bg-gradient-to-br from-gray-100 to-gray-200 relative">
                <div className="absolute inset-0 flex items-center justify-center">
                  <Building2 className="h-16 w-16 text-gray-400" />
                </div>
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
                    {formatPrice(property.price, property.listing_type)}
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
                  <span>{property.view_count || 0} views</span>
                  <span>•</span>
                  <span>{property.inquiry_count || 0} inquiries</span>
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
                placeholder="Beautiful 3BR Home in Sunset District"
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
                    <SelectItem value="draft">Draft</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="under_contract">Under Contract</SelectItem>
                    <SelectItem value="sold">Sold</SelectItem>
                    <SelectItem value="rented">Rented</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Price */}
            <div className="space-y-2">
              <Label>Price</Label>
              <div className="relative">
                <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="number"
                  className="pl-8"
                  value={form.price}
                  onChange={e => setForm(prev => ({ ...prev, price: e.target.value }))}
                  placeholder="500000"
                />
              </div>
            </div>

            {/* Address */}
            <div className="space-y-2">
              <Label>Address</Label>
              <Input
                value={form.address_line1}
                onChange={e => setForm(prev => ({ ...prev, address_line1: e.target.value }))}
                placeholder="123 Main Street"
                className="mb-2"
              />
              <Input
                value={form.address_line2}
                onChange={e => setForm(prev => ({ ...prev, address_line2: e.target.value }))}
                placeholder="Apt 4B (optional)"
              />
            </div>

            <div className="grid grid-cols-4 gap-4">
              <div className="space-y-2 col-span-2">
                <Label>City</Label>
                <Input
                  value={form.city}
                  onChange={e => setForm(prev => ({ ...prev, city: e.target.value }))}
                  placeholder="San Francisco"
                />
              </div>
              <div className="space-y-2">
                <Label>State</Label>
                <Input
                  value={form.state}
                  onChange={e => setForm(prev => ({ ...prev, state: e.target.value }))}
                  placeholder="CA"
                />
              </div>
              <div className="space-y-2">
                <Label>Postal Code</Label>
                <Input
                  value={form.postal_code}
                  onChange={e => setForm(prev => ({ ...prev, postal_code: e.target.value }))}
                  placeholder="94102"
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
                <Label>Lot Size</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={form.lot_size}
                  onChange={e => setForm(prev => ({ ...prev, lot_size: e.target.value }))}
                  placeholder="0.25"
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
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit}>{editingProperty ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
