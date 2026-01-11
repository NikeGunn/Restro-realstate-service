import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/auth'
import { organizationsApi, locationsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { WidgetPreview } from '@/components/WidgetPreview'
import {
  Building2,
  MapPin,
  Plus,
  Save,
  Trash2,
  Palette,
  Copy,
  Eye,
} from 'lucide-react'
import type { Location } from '@/types'

export function SettingsPage() {
  const { t } = useTranslation()
  const { currentOrganization, setCurrentOrganization } = useAuthStore()
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const [orgForm, setOrgForm] = useState({
    name: '',
    widget_position: 'bottom-right',
    widget_color: '#3B82F6',
    greeting_message: '',
  })

  const [newLocation, setNewLocation] = useState({
    name: '',
    address: '',
    phone: '',
    email: '',
  })

  useEffect(() => {
    if (currentOrganization) {
      setOrgForm({
        name: currentOrganization.name || '',
        widget_position: currentOrganization.widget_position || 'bottom-right',
        widget_color: currentOrganization.widget_color || '#3B82F6',
        greeting_message: currentOrganization.greeting_message || '',
      })
      fetchLocations()
    }
    setLoading(false)
  }, [currentOrganization])

  const fetchLocations = async () => {
    if (!currentOrganization) return

    try {
      const response = await locationsApi.list(currentOrganization.id)
      setLocations(Array.isArray(response) ? response : (response.results || []))
    } catch (error) {
      console.error('Error fetching locations:', error)
    }
  }

  const handleSaveOrganization = async () => {
    if (!currentOrganization) return

    setSaving(true)
    try {
      const updated = await organizationsApi.update(currentOrganization.id, orgForm)
      setCurrentOrganization({ ...currentOrganization, ...updated })
      toast({
        title: 'Saved!',
        description: 'Organization settings updated.',
      })
    } catch (error) {
      console.error('Error saving organization:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to save settings.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleAddLocation = async () => {
    if (!currentOrganization || !newLocation.name.trim()) return

    try {
      await locationsApi.create(currentOrganization.id, newLocation)
      setNewLocation({ name: '', address: '', phone: '', email: '' })
      await fetchLocations()
      toast({
        title: 'Location added',
        description: 'New location has been created.',
      })
    } catch (error) {
      console.error('Error adding location:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to add location.',
      })
    }
  }

  const handleDeleteLocation = async (locationId: string) => {
    if (!currentOrganization) return

    try {
      await locationsApi.delete(currentOrganization.id, locationId)
      await fetchLocations()
      toast({
        title: 'Location deleted',
        description: 'Location has been removed.',
      })
    } catch (error) {
      console.error('Error deleting location:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to delete location.',
      })
    }
  }

  const [showPreview, setShowPreview] = useState(false)

  // Generate widget embed code based on environment
  const getWidgetBaseUrl = () => {
    // In production, use the API URL or default to kribaat.com
    const apiUrl = import.meta.env.VITE_API_URL || '';
    if (apiUrl && !apiUrl.includes('localhost')) {
      // Extract base URL from API URL (e.g., https://kribaat.com/api -> https://kribaat.com)
      return apiUrl.replace(/\/api$/, '');
    }
    // Fallback for development
    return 'http://localhost:8000';
  }

  const getWidgetCode = () => {
    if (!currentOrganization) return ''
    const baseUrl = getWidgetBaseUrl();
    return `<script src="${baseUrl}/api/v1/widget/widget.js" data-widget-key="${currentOrganization.widget_key}"></script>`
  }

  const copyWidgetCode = () => {
    if (!currentOrganization) return

    const code = getWidgetCode()
    navigator.clipboard.writeText(code)
    toast({
      title: 'Copied!',
      description: 'Widget code copied to clipboard.',
    })
  }

  if (!currentOrganization) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Please select an organization first.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <>
      {/* Widget Preview Modal */}
      {showPreview && (
        <WidgetPreview
          widgetKey={currentOrganization.widget_key}
          onClose={() => setShowPreview(false)}
        />
      )}

      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">{t('settings.title')}</h1>
          <p className="text-muted-foreground">
            {t('settings.subtitle')}
          </p>
        </div>

      <Tabs defaultValue="organization">
        <TabsList>
          <TabsTrigger value="organization">{t('settings.organization')}</TabsTrigger>
          <TabsTrigger value="widget">{t('settings.widget')}</TabsTrigger>
          <TabsTrigger value="locations">{t('settings.locations')}</TabsTrigger>
        </TabsList>

        <TabsContent value="organization" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5" />
                {t('settings.organizationSettings')}
              </CardTitle>
              <CardDescription>
                {t('settings.organizationDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="org_name">{t('organization.name')}</Label>
                <Input
                  id="org_name"
                  value={orgForm.name}
                  onChange={(e) =>
                    setOrgForm((prev) => ({ ...prev, name: e.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>{t('organization.businessType')}</Label>
                <Badge variant="outline" className="text-sm">
                  {currentOrganization.business_type === 'restaurant'
                    ? '🍽️ Restaurant'
                    : '🏠 Real Estate'}
                </Badge>
              </div>

              <div className="space-y-2">
                <Label>{t('organization.plan')}</Label>
                <Badge variant="secondary" className="text-sm capitalize">
                  {currentOrganization.plan}
                </Badge>
              </div>

              <Button onClick={handleSaveOrganization} disabled={saving}>
                <Save className="h-4 w-4 mr-2" />
                {saving ? t('settings.saving') : t('settings.saveChanges')}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="widget" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Palette className="h-5 w-5" />
                {t('settings.widgetCustomization')}
              </CardTitle>
              <CardDescription>
                {t('settings.widgetCustomizationDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="widget_color">{t('settings.widgetColor')}</Label>
                  <div className="flex gap-2">
                    <Input
                      id="widget_color"
                      type="color"
                      className="w-16 h-10 p-1"
                      value={orgForm.widget_color}
                      onChange={(e) =>
                        setOrgForm((prev) => ({ ...prev, widget_color: e.target.value }))
                      }
                    />
                    <Input
                      value={orgForm.widget_color}
                      onChange={(e) =>
                        setOrgForm((prev) => ({ ...prev, widget_color: e.target.value }))
                      }
                      className="flex-1"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="widget_position">{t('settings.widgetPosition')}</Label>
                  <select
                    id="widget_position"
                    className="w-full p-2 rounded-md border bg-background"
                    value={orgForm.widget_position}
                    onChange={(e) =>
                      setOrgForm((prev) => ({ ...prev, widget_position: e.target.value }))
                    }
                  >
                    <option value="bottom-right">{t('settings.bottomRight')}</option>
                    <option value="bottom-left">{t('settings.bottomLeft')}</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="greeting">{t('settings.greetingMessage')}</Label>
                  <textarea
                    id="greeting"
                    className="w-full min-h-[80px] p-3 rounded-md border bg-background"
                    placeholder={t('settings.greetingPlaceholder')}
                    value={orgForm.greeting_message}
                    onChange={(e) =>
                      setOrgForm((prev) => ({ ...prev, greeting_message: e.target.value }))
                    }
                  />
                </div>

                <Button onClick={handleSaveOrganization} disabled={saving}>
                  <Save className="h-4 w-4 mr-2" />
                  {saving ? 'Saving...' : 'Save Changes'}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t('settings.widgetInstallation')}</CardTitle>
                <CardDescription>
                  {t('settings.widgetInstallationDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('settings.widgetKey')}</Label>
                  <div className="flex gap-2">
                    <Input value={currentOrganization.widget_key} readOnly className="flex-1" />
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        navigator.clipboard.writeText(currentOrganization.widget_key)
                        toast({
                          title: 'Copied!',
                          description: 'Widget key copied.',
                        })
                      }}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>{t('settings.embedCode')}</Label>
                    <div className="flex gap-2">
                      <Button onClick={copyWidgetCode} variant="outline" size="sm">
                        <Copy className="h-4 w-4 mr-2" />
                        {t('dashboard.copyCode')}
                      </Button>
                      <Button onClick={() => setShowPreview(true)} variant="default" size="sm">
                        <Eye className="h-4 w-4 mr-2" />
                        {t('settings.testWidget')}
                      </Button>
                    </div>
                  </div>
                  <div 
                    className="bg-muted p-4 rounded-lg font-mono text-xs overflow-x-auto cursor-pointer hover:bg-muted/80 transition-colors"
                    onClick={copyWidgetCode}
                    title="Click to copy"
                  >
                    {getWidgetCode()}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('settings.clickToCopy')}
                  </p>
                </div>

                {/* Static Preview */}
                <div className="border rounded-lg p-4 bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-2">{t('settings.widgetButtonPreview')}</p>
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center shadow-lg cursor-pointer hover:scale-110 transition-transform"
                    style={{ backgroundColor: orgForm.widget_color }}
                    onClick={() => setShowPreview(true)}
                    title="Click to test widget"
                  >
                    <svg
                      className="w-6 h-6 text-white"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                      />
                    </svg>
                  </div>
                </div>

                {/* Instructions */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-blue-900 mb-2">{t('settings.quickSetupGuide')}</h4>
                  <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
                    <li>{t('settings.setupStep1')}</li>
                    <li>{t('settings.setupStep2')}</li>
                    <li>{t('settings.setupStep3')}</li>
                    <li>{t('settings.setupStep4')}</li>
                  </ol>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="locations" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Plus className="h-5 w-5" />
                  {t('settings.addLocation')}
                </CardTitle>
                <CardDescription>
                  {t('settings.addLocationDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="loc_name">{t('settings.locationName')} *</Label>
                  <Input
                    id="loc_name"
                    placeholder={t('settings.locationNamePlaceholder')}
                    value={newLocation.name}
                    onChange={(e) =>
                      setNewLocation((prev) => ({ ...prev, name: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="loc_address">{t('common.address')}</Label>
                  <Input
                    id="loc_address"
                    placeholder={t('settings.locationAddressPlaceholder')}
                    value={newLocation.address}
                    onChange={(e) =>
                      setNewLocation((prev) => ({ ...prev, address: e.target.value }))
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="loc_phone">{t('common.phone')}</Label>
                    <Input
                      id="loc_phone"
                      placeholder="+1 234 567 8900"
                      value={newLocation.phone}
                      onChange={(e) =>
                        setNewLocation((prev) => ({ ...prev, phone: e.target.value }))
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="loc_email">{t('common.email')}</Label>
                    <Input
                      id="loc_email"
                      type="email"
                      placeholder="branch@example.com"
                      value={newLocation.email}
                      onChange={(e) =>
                        setNewLocation((prev) => ({ ...prev, email: e.target.value }))
                      }
                    />
                  </div>
                </div>
                <Button onClick={handleAddLocation}>
                  <Plus className="h-4 w-4 mr-2" />
                  {t('settings.addLocation')}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MapPin className="h-5 w-5" />
                  {t('settings.yourLocations')}
                </CardTitle>
                <CardDescription>
                  {t('settings.locationsConfigured', { count: locations.length })}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {locations.length === 0 ? (
                  <div className="text-center py-8">
                    <MapPin className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">{t('settings.noLocationsYet')}</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {locations.map((loc) => (
                      <div
                        key={loc.id}
                        className="flex items-start justify-between p-3 bg-muted rounded-lg group"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="font-medium">{loc.name}</p>
                            {!loc.is_active && (
                              <Badge variant="secondary">Inactive</Badge>
                            )}
                          </div>
                          {loc.address && (
                            <p className="text-sm text-muted-foreground">{loc.address}</p>
                          )}
                          <div className="flex gap-4 text-xs text-muted-foreground mt-1">
                            {loc.phone && <span>{loc.phone}</span>}
                            {loc.email && <span>{loc.email}</span>}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="opacity-0 group-hover:opacity-100"
                          onClick={() => handleDeleteLocation(loc.id)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
      </div>
    </>
  )
}
