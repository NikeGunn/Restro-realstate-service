import { useState, useEffect, useCallback } from 'react'
import { format, formatDistanceToNow } from 'date-fns'
import { User, Phone, Mail, Building2, Star, TrendingUp, Clock, Plus, Edit, MessageSquare, UserCheck, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import type { Lead, Organization, LeadStats } from '@/types'

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-800',
  contacted: 'bg-yellow-100 text-yellow-800',
  qualified: 'bg-green-100 text-green-800',
  unqualified: 'bg-gray-100 text-gray-800',
  converted: 'bg-purple-100 text-purple-800',
  lost: 'bg-red-100 text-red-800',
}

const SOURCE_LABELS: Record<string, string> = {
  website: '🌐 Website',
  referral: '👥 Referral',
  social: '📱 Social Media',
  advertisement: '📢 Advertisement',
  walk_in: '🚶 Walk-in',
  other: '📝 Other',
}

const BUDGET_RANGES = [
  { value: '0-250000', label: 'Under $250K' },
  { value: '250000-500000', label: '$250K - $500K' },
  { value: '500000-750000', label: '$500K - $750K' },
  { value: '750000-1000000', label: '$750K - $1M' },
  { value: '1000000+', label: '$1M+' },
]

const INITIAL_FORM = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  source: 'website',
  status: 'new',
  budget_min: '',
  budget_max: '',
  preferred_property_type: '',
  preferred_locations: '',
  notes: '',
}

export function LeadsPage() {
  const { toast } = useToast()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrgId, setSelectedOrgId] = useState<string>('')
  const [leads, setLeads] = useState<Lead[]>([])
  const [stats, setStats] = useState<LeadStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [sourceFilter, setSourceFilter] = useState<string>('all')

  // Dialog states
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingLead, setEditingLead] = useState<Lead | null>(null)
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

  // Load leads
  const loadLeads = useCallback(async () => {
    if (!selectedOrgId) return
    setLoading(true)
    try {
      const params: Record<string, any> = { organization: selectedOrgId }
      if (statusFilter !== 'all') params.status = statusFilter
      if (sourceFilter !== 'all') params.source = sourceFilter
      
      const data = await realEstateApi.leads.list(params)
      setLeads(Array.isArray(data) ? data : data.results || [])
    } catch (error) {
      console.error('Failed to load leads:', error)
      toast({ title: 'Error', description: 'Failed to load leads', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [selectedOrgId, statusFilter, sourceFilter, toast])

  // Load stats
  const loadStats = useCallback(async () => {
    if (!selectedOrgId) return
    try {
      const data = await realEstateApi.leads.stats({ organization: selectedOrgId })
      setStats(data)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }, [selectedOrgId])

  useEffect(() => {
    loadLeads()
    loadStats()
  }, [loadLeads, loadStats])

  const openCreateDialog = () => {
    setEditingLead(null)
    setForm(INITIAL_FORM)
    setDialogOpen(true)
  }

  const openEditDialog = (lead: Lead) => {
    setEditingLead(lead)
    setForm({
      first_name: lead.first_name,
      last_name: lead.last_name,
      email: lead.email || '',
      phone: lead.phone || '',
      source: lead.source,
      status: lead.status,
      budget_min: lead.budget_min?.toString() || '',
      budget_max: lead.budget_max?.toString() || '',
      preferred_property_type: lead.preferred_property_type || '',
      preferred_locations: lead.preferred_locations || '',
      notes: lead.notes || '',
    })
    setDialogOpen(true)
  }

  const handleSubmit = async () => {
    if (!form.first_name.trim() || !form.last_name.trim()) {
      toast({ title: 'Error', description: 'Name is required', variant: 'destructive' })
      return
    }

    const payload = {
      organization: selectedOrgId,
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email || null,
      phone: form.phone || null,
      source: form.source,
      status: form.status,
      budget_min: form.budget_min ? parseFloat(form.budget_min) : null,
      budget_max: form.budget_max ? parseFloat(form.budget_max) : null,
      preferred_property_type: form.preferred_property_type || null,
      preferred_locations: form.preferred_locations || null,
      notes: form.notes || null,
    }

    try {
      if (editingLead) {
        await realEstateApi.leads.update(editingLead.id, payload)
        toast({ title: 'Success', description: 'Lead updated' })
      } else {
        await realEstateApi.leads.create(payload)
        toast({ title: 'Success', description: 'Lead created' })
      }
      setDialogOpen(false)
      loadLeads()
      loadStats()
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to save lead'
      toast({ title: 'Error', description: message, variant: 'destructive' })
    }
  }

  const handleMarkContacted = async (id: string) => {
    try {
      await realEstateApi.leads.markContacted(id, 'Marked as contacted from dashboard')
      toast({ title: 'Success', description: 'Lead marked as contacted' })
      loadLeads()
      loadStats()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update lead', variant: 'destructive' })
    }
  }

  const handleQualify = async (id: string) => {
    try {
      await realEstateApi.leads.qualify(id)
      toast({ title: 'Success', description: 'Lead qualified' })
      loadLeads()
      loadStats()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to qualify lead', variant: 'destructive' })
    }
  }

  const handleRecalculateScore = async (id: string) => {
    try {
      await realEstateApi.leads.recalculateScore(id)
      toast({ title: 'Success', description: 'Lead score recalculated' })
      loadLeads()
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to recalculate score', variant: 'destructive' })
    }
  }

  const getScoreColor = (score: number | null) => {
    if (!score) return 'text-gray-400'
    if (score >= 80) return 'text-green-600'
    if (score >= 50) return 'text-yellow-600'
    return 'text-red-600'
  }

  if (organizations.length === 0 && !loading) {
    return (
      <div className="p-6">
        <Card className="p-8 text-center">
          <h2 className="text-xl font-semibold mb-2">No Real Estate Organization</h2>
          <p className="text-muted-foreground">Create a real estate organization first to manage leads.</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Leads</h1>
          <p className="text-muted-foreground">Manage potential buyers and renters</p>
        </div>
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4 mr-2" />
          Add Lead
        </Button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{stats.total}</div>
              <div className="text-sm text-muted-foreground">Total Leads</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-blue-600">{stats.by_status?.new || 0}</div>
              <div className="text-sm text-muted-foreground">New</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-yellow-600">{stats.by_status?.contacted || 0}</div>
              <div className="text-sm text-muted-foreground">Contacted</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-600">{stats.by_status?.qualified || 0}</div>
              <div className="text-sm text-muted-foreground">Qualified</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-purple-600">{stats.by_status?.converted || 0}</div>
              <div className="text-sm text-muted-foreground">Converted</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="contacted">Contacted</SelectItem>
            <SelectItem value="qualified">Qualified</SelectItem>
            <SelectItem value="unqualified">Unqualified</SelectItem>
            <SelectItem value="converted">Converted</SelectItem>
            <SelectItem value="lost">Lost</SelectItem>
          </SelectContent>
        </Select>

        <Select value={sourceFilter} onValueChange={setSourceFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            <SelectItem value="website">Website</SelectItem>
            <SelectItem value="referral">Referral</SelectItem>
            <SelectItem value="social">Social Media</SelectItem>
            <SelectItem value="advertisement">Advertisement</SelectItem>
            <SelectItem value="walk_in">Walk-in</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Leads List */}
      {loading ? (
        <Card className="p-8 text-center">Loading leads...</Card>
      ) : leads.length === 0 ? (
        <Card className="p-8 text-center">
          <User className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No leads found</h3>
          <p className="text-muted-foreground mb-4">Start by adding your first lead.</p>
          <Button onClick={openCreateDialog}>
            <Plus className="h-4 w-4 mr-2" />
            Add Lead
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {leads.map(lead => (
            <Card key={lead.id} className="overflow-hidden hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold text-lg">{lead.full_name}</h3>
                      <Badge className={STATUS_COLORS[lead.status]}>{lead.status_display}</Badge>
                      {lead.is_hot && (
                        <Badge className="bg-red-100 text-red-800">
                          🔥 Hot Lead
                        </Badge>
                      )}
                    </div>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-3">
                      {lead.email && (
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Mail className="h-4 w-4" />
                          <span>{lead.email}</span>
                        </div>
                      )}
                      {lead.phone && (
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Phone className="h-4 w-4" />
                          <span>{lead.phone}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <span>{SOURCE_LABELS[lead.source] || lead.source}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <TrendingUp className={`h-4 w-4 ${getScoreColor(lead.score)}`} />
                        <span className={`font-medium ${getScoreColor(lead.score)}`}>
                          Score: {lead.score || 0}
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                      {lead.budget_min && lead.budget_max && (
                        <span>💰 ${(lead.budget_min / 1000).toFixed(0)}K - ${(lead.budget_max / 1000).toFixed(0)}K</span>
                      )}
                      {lead.preferred_property_type && (
                        <span>🏠 {lead.preferred_property_type}</span>
                      )}
                      {lead.preferred_locations && (
                        <span>📍 {lead.preferred_locations}</span>
                      )}
                    </div>

                    {lead.last_contacted_at && (
                      <div className="mt-2 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3 inline mr-1" />
                        Last contacted {formatDistanceToNow(new Date(lead.last_contacted_at), { addSuffix: true })}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 ml-4">
                    <Button size="sm" variant="outline" onClick={() => openEditDialog(lead)}>
                      <Edit className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleRecalculateScore(lead.id)} title="Recalculate Score">
                      <RefreshCw className="h-3 w-3" />
                    </Button>
                    {lead.status === 'new' && (
                      <Button size="sm" onClick={() => handleMarkContacted(lead.id)}>
                        <MessageSquare className="h-3 w-3 mr-1" />
                        Contacted
                      </Button>
                    )}
                    {lead.status === 'contacted' && (
                      <Button size="sm" onClick={() => handleQualify(lead.id)}>
                        <UserCheck className="h-3 w-3 mr-1" />
                        Qualify
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingLead ? 'Edit Lead' : 'Add New Lead'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Name */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>First Name *</Label>
                <Input
                  value={form.first_name}
                  onChange={e => setForm(prev => ({ ...prev, first_name: e.target.value }))}
                  placeholder="John"
                />
              </div>
              <div className="space-y-2">
                <Label>Last Name *</Label>
                <Input
                  value={form.last_name}
                  onChange={e => setForm(prev => ({ ...prev, last_name: e.target.value }))}
                  placeholder="Doe"
                />
              </div>
            </div>

            {/* Contact */}
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                value={form.email}
                onChange={e => setForm(prev => ({ ...prev, email: e.target.value }))}
                placeholder="john@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label>Phone</Label>
              <Input
                value={form.phone}
                onChange={e => setForm(prev => ({ ...prev, phone: e.target.value }))}
                placeholder="(555) 123-4567"
              />
            </div>

            {/* Source & Status */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Source</Label>
                <Select value={form.source} onValueChange={v => setForm(prev => ({ ...prev, source: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="website">Website</SelectItem>
                    <SelectItem value="referral">Referral</SelectItem>
                    <SelectItem value="social">Social Media</SelectItem>
                    <SelectItem value="advertisement">Advertisement</SelectItem>
                    <SelectItem value="walk_in">Walk-in</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={form.status} onValueChange={v => setForm(prev => ({ ...prev, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="new">New</SelectItem>
                    <SelectItem value="contacted">Contacted</SelectItem>
                    <SelectItem value="qualified">Qualified</SelectItem>
                    <SelectItem value="unqualified">Unqualified</SelectItem>
                    <SelectItem value="converted">Converted</SelectItem>
                    <SelectItem value="lost">Lost</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Budget */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Budget Min</Label>
                <Input
                  type="number"
                  value={form.budget_min}
                  onChange={e => setForm(prev => ({ ...prev, budget_min: e.target.value }))}
                  placeholder="250000"
                />
              </div>
              <div className="space-y-2">
                <Label>Budget Max</Label>
                <Input
                  type="number"
                  value={form.budget_max}
                  onChange={e => setForm(prev => ({ ...prev, budget_max: e.target.value }))}
                  placeholder="500000"
                />
              </div>
            </div>

            {/* Preferences */}
            <div className="space-y-2">
              <Label>Preferred Property Type</Label>
              <Select value={form.preferred_property_type} onValueChange={v => setForm(prev => ({ ...prev, preferred_property_type: v }))}>
                <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="house">House</SelectItem>
                  <SelectItem value="apartment">Apartment</SelectItem>
                  <SelectItem value="condo">Condo</SelectItem>
                  <SelectItem value="townhouse">Townhouse</SelectItem>
                  <SelectItem value="land">Land</SelectItem>
                  <SelectItem value="commercial">Commercial</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Preferred Locations</Label>
              <Input
                value={form.preferred_locations}
                onChange={e => setForm(prev => ({ ...prev, preferred_locations: e.target.value }))}
                placeholder="Downtown, Sunset District, Marina"
              />
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label>Notes</Label>
              <Textarea
                value={form.notes}
                onChange={e => setForm(prev => ({ ...prev, notes: e.target.value }))}
                placeholder="Additional notes about the lead..."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit}>{editingLead ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
