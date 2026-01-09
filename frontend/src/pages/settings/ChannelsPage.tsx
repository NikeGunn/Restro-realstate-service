import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/auth'
import { channelsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import {
  Instagram,
  Phone,
  Save,
  Trash2,
  Plus,
  RefreshCw,
  Copy,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ExternalLink,
  Eye,
  EyeOff,
  Crown,
} from 'lucide-react'

interface WhatsAppConfig {
  id: string
  organization: string
  phone_number_id: string
  business_account_id: string
  access_token: string
  verify_token: string
  is_verified: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

interface InstagramConfig {
  id: string
  organization: string
  instagram_business_id: string
  page_id: string
  access_token: string
  verify_token: string
  is_verified: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export function ChannelsPage() {
  const { t } = useTranslation()
  const { currentOrganization, setCurrentOrganization } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const [whatsappConfigs, setWhatsappConfigs] = useState<WhatsAppConfig[]>([])
  const [instagramConfigs, setInstagramConfigs] = useState<InstagramConfig[]>([])

  const [showWhatsAppForm, setShowWhatsAppForm] = useState(false)
  const [showInstagramForm, setShowInstagramForm] = useState(false)
  const [showAccessTokens, setShowAccessTokens] = useState<Record<string, boolean>>({})
  const [showGuide, setShowGuide] = useState(false)

  const [whatsappForm, setWhatsappForm] = useState({
    phone_number_id: '',
    business_account_id: '',
    access_token: '',
    verify_token: '',
  })

  const [instagramForm, setInstagramForm] = useState({
    instagram_business_id: '',
    page_id: '',
    access_token: '',
    verify_token: '',
  })

  // Check if organization has Power plan
  const isPowerPlan = currentOrganization?.plan === 'power'

  // Refresh organization data on mount to get latest plan
  useEffect(() => {
    const refreshOrganization = async () => {
      if (currentOrganization) {
        try {
          const { organizationsApi } = await import('@/services/api')
          const updated = await organizationsApi.get(currentOrganization.id)
          setCurrentOrganization(updated)
        } catch (error) {
          console.error('Error refreshing organization:', error)
        }
      }
    }
    refreshOrganization()
  }, [])

  useEffect(() => {
    if (currentOrganization) {
      fetchChannels()
    }
  }, [currentOrganization])

  const fetchChannels = async () => {
    if (!currentOrganization) return

    setLoading(true)
    try {
      const [whatsapp, instagram] = await Promise.all([
        channelsApi.whatsapp.list({ organization: currentOrganization.id }),
        channelsApi.instagram.list({ organization: currentOrganization.id }),
      ])
      setWhatsappConfigs(whatsapp)
      setInstagramConfigs(instagram)
    } catch (error: any) {
      console.error('Error fetching channels:', error)
      // Don't show error for 403 - that's expected for non-power plans
      if (error.response?.status !== 403) {
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Failed to load channel configurations.',
        })
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSaveWhatsApp = async () => {
    if (!currentOrganization) return

    setSaving(true)
    try {
      const newConfig = await channelsApi.whatsapp.create({
        organization: currentOrganization.id,
        ...whatsappForm,
      })
      setWhatsappConfigs([...whatsappConfigs, newConfig])
      setWhatsappForm({ phone_number_id: '', business_account_id: '', access_token: '', verify_token: '' })
      setShowWhatsAppForm(false)
      toast({
        title: 'WhatsApp Connected',
        description: 'WhatsApp Business configuration saved. Configure your webhook to complete setup.',
      })
    } catch (error: any) {
      console.error('Error saving WhatsApp config:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save WhatsApp configuration.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleSaveInstagram = async () => {
    if (!currentOrganization) return

    setSaving(true)
    try {
      const newConfig = await channelsApi.instagram.create({
        organization: currentOrganization.id,
        ...instagramForm,
      })
      setInstagramConfigs([...instagramConfigs, newConfig])
      setInstagramForm({ instagram_business_id: '', page_id: '', access_token: '', verify_token: '' })
      setShowInstagramForm(false)
      toast({
        title: 'Instagram Connected',
        description: 'Instagram configuration saved. Configure your webhook to complete setup.',
      })
    } catch (error: any) {
      console.error('Error saving Instagram config:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save Instagram configuration.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteWhatsApp = async (id: string) => {
    if (!confirm('Are you sure you want to remove this WhatsApp connection?')) return

    try {
      await channelsApi.whatsapp.delete(id)
      setWhatsappConfigs(whatsappConfigs.filter((c) => c.id !== id))
      toast({
        title: 'Deleted',
        description: 'WhatsApp configuration removed.',
      })
    } catch (error) {
      console.error('Error deleting WhatsApp config:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to delete configuration.',
      })
    }
  }

  const handleDeleteInstagram = async (id: string) => {
    if (!confirm('Are you sure you want to remove this Instagram connection?')) return

    try {
      await channelsApi.instagram.delete(id)
      setInstagramConfigs(instagramConfigs.filter((c) => c.id !== id))
      toast({
        title: 'Deleted',
        description: 'Instagram configuration removed.',
      })
    } catch (error) {
      console.error('Error deleting Instagram config:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to delete configuration.',
      })
    }
  }

  const handleToggleActive = async (type: 'whatsapp' | 'instagram', id: string, isActive: boolean) => {
    try {
      if (type === 'whatsapp') {
        await channelsApi.whatsapp.update(id, { is_active: !isActive })
        setWhatsappConfigs(
          whatsappConfigs.map((c) => (c.id === id ? { ...c, is_active: !isActive } : c))
        )
      } else {
        await channelsApi.instagram.update(id, { is_active: !isActive })
        setInstagramConfigs(
          instagramConfigs.map((c) => (c.id === id ? { ...c, is_active: !isActive } : c))
        )
      }
      toast({
        title: isActive ? 'Channel Disabled' : 'Channel Enabled',
        description: `${type === 'whatsapp' ? 'WhatsApp' : 'Instagram'} integration is now ${isActive ? 'inactive' : 'active'}.`,
      })
    } catch (error) {
      console.error('Error toggling channel:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to update channel status.',
      })
    }
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast({
      title: 'Copied!',
      description: `${label} copied to clipboard.`,
    })
  }

  const getWebhookUrl = (type: 'whatsapp' | 'instagram') => {
    // For production/ngrok, use VITE_WEBHOOK_URL if set, otherwise fallback to API URL
    const webhookBase = import.meta.env.VITE_WEBHOOK_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
    return `${webhookBase.replace('/api', '')}/api/webhooks/${type}/`
  }

  const isLocalhost = getWebhookUrl('whatsapp').includes('localhost')

  if (!currentOrganization) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Please select an organization first.</p>
      </div>
    )
  }

  // Power Plan Gate
  if (!isPowerPlan) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">{t('channels.title')}</h1>
          <p className="text-muted-foreground">
            {t('channels.subtitle')}
          </p>
        </div>

        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-6">
            <div className="flex items-start gap-4">
              <div className="p-3 bg-amber-100 rounded-full">
                <Crown className="h-8 w-8 text-amber-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-amber-900">Power Plan Required</h3>
                <p className="text-amber-800 mt-1">
                  WhatsApp and Instagram integrations are available on the Power plan.
                  Contact your administrator to upgrade your organization.
                </p>
                <div className="mt-4 space-y-2">
                  <p className="text-sm font-medium text-amber-900">Power Plan includes:</p>
                  <ul className="text-sm text-amber-800 space-y-1">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4" /> WhatsApp Business API integration (FREE from Meta)
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4" /> Instagram DM automation (FREE from Meta)
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4" /> Multi-channel inbox
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4" /> Advanced analytics
                    </li>
                  </ul>
                </div>
                <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm text-blue-900">
                    <strong>💡 Good News:</strong> WhatsApp Business API and Instagram Graph API are <strong>FREE</strong> from Meta!
                    You only need to pay for our Power Plan to access these features in our platform.
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{t('channels.title')}</h1>
          <p className="text-muted-foreground">
            {t('channels.subtitle')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowGuide(!showGuide)}>
            {showGuide ? <EyeOff className="h-4 w-4 mr-2" /> : <Eye className="h-4 w-4 mr-2" />}
            {showGuide ? 'Hide Guide' : 'Beginner\'s Guide'}
          </Button>
          <Button variant="outline" onClick={fetchChannels}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Beginner's Setup Guide */}
      {showGuide && (
        <Card className="border-blue-200 bg-blue-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-blue-600" />
              Complete Setup Guide for Beginners
            </CardTitle>
            <CardDescription className="text-blue-800">
              Follow these steps to connect WhatsApp and Instagram to your chatbot (100% FREE from Meta!)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Overview */}
            <div className="bg-white p-4 rounded-lg border border-blue-200">
              <h3 className="font-semibold text-blue-900 mb-2">📋 What You Need (All FREE):</h3>
              <ul className="space-y-2 text-sm text-blue-900">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                  <span><strong>Facebook Developer Account</strong> (Free - sign up at developers.facebook.com)</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                  <span><strong>Facebook Business Page</strong> (Free - for Instagram integration)</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                  <span><strong>WhatsApp Business Account</strong> (Free - Meta provides 1000 free conversations/month)</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                  <span><strong>Instagram Business Account</strong> (Free - must be linked to Facebook Page)</span>
                </li>
              </ul>
            </div>

            {/* Step-by-Step Instructions */}
            <div className="space-y-4">
              <div className="bg-white p-4 rounded-lg border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-3">🚀 Step 1: Create Meta Developer App</h3>
                <ol className="space-y-2 text-sm text-blue-900 list-decimal list-inside">
                  <li>Go to <a href="https://developers.facebook.com/apps/" target="_blank" className="text-blue-600 underline">developers.facebook.com/apps</a></li>
                  <li>Click "Create App" → Select "Business" type</li>
                  <li>Enter app name (e.g., "My Chatbot") and contact email</li>
                  <li>Click "Create App" and complete security check</li>
                </ol>
              </div>

              <div className="bg-white p-4 rounded-lg border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-3">📱 Step 2: Setup WhatsApp (Optional)</h3>
                <ol className="space-y-2 text-sm text-blue-900 list-decimal list-inside">
                  <li>In your Meta app, add "WhatsApp" product</li>
                  <li>Go to WhatsApp → API Setup</li>
                  <li>Copy <strong>Phone Number ID</strong> and <strong>Business Account ID</strong></li>
                  <li>Click "Generate Token" → Copy the <strong>Access Token</strong> (starts with EAA...)</li>
                  <li>Create your own <strong>Verify Token</strong> (any random string like "my_secret_123")</li>
                  <li>Paste all values in the WhatsApp form below</li>
                  <li>After saving, copy the webhook URL and configure it in Meta's WhatsApp settings</li>
                </ol>
              </div>

              <div className="bg-white p-4 rounded-lg border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-3">📸 Step 3: Setup Instagram (Optional)</h3>
                <ol className="space-y-2 text-sm text-blue-900 list-decimal list-inside">
                  <li>Link your Instagram Business account to a Facebook Page</li>
                  <li>In your Meta app, add "Instagram" product</li>
                  <li>Go to Instagram → Basic Display</li>
                  <li>Copy <strong>Instagram Business ID</strong> and <strong>Page ID</strong></li>
                  <li>Generate an <strong>Access Token</strong> with instagram_basic and pages_messaging permissions</li>
                  <li>Create your own <strong>Verify Token</strong> (any random string)</li>
                  <li>Paste all values in the Instagram form below</li>
                  <li>After saving, copy the webhook URL and configure it in Meta's Instagram settings</li>
                </ol>
              </div>

              <div className="bg-white p-4 rounded-lg border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-3">⚙️ Step 4: Environment Variables (Backend Only)</h3>
                <p className="text-sm text-blue-900 mb-2">Your backend .env file should include:</p>
                <div className="bg-gray-900 text-gray-100 p-3 rounded font-mono text-xs overflow-x-auto">
                  <div># Meta Configuration (Optional - only needed for webhook verification)</div>
                  <div>META_APP_SECRET=your_app_secret_from_meta_app_settings</div>
                  <div>META_GRAPH_API_VERSION=v18.0</div>
                  <div className="mt-2"># Default Verify Tokens (you can use any random string)</div>
                  <div>WHATSAPP_DEFAULT_VERIFY_TOKEN=my_whatsapp_verify_token_123</div>
                  <div>INSTAGRAM_DEFAULT_VERIFY_TOKEN=my_instagram_verify_token_456</div>
                </div>
                <p className="text-xs text-blue-700 mt-2">💡 Note: The actual tokens you use are stored in the database per organization, not in .env</p>
              </div>

              <div className="bg-white p-4 rounded-lg border border-blue-200">
                <h3 className="font-semibold text-blue-900 mb-3">💰 Free Tier Information</h3>
                <ul className="space-y-2 text-sm text-blue-900">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                    <span><strong>WhatsApp Business API:</strong> 1000 free conversations per month, then $0.005-0.09 per conversation (varies by country)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                    <span><strong>Instagram API:</strong> Completely FREE - no limits on messages</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 mt-0.5 text-blue-600 flex-shrink-0" />
                    <span><strong>Development Mode:</strong> Test for free with up to 5 test numbers before going live</span>
                  </li>
                </ul>
              </div>

              <div className="bg-green-50 border border-green-200 p-4 rounded-lg">
                <h3 className="font-semibold text-green-900 mb-2">✅ Quick Checklist</h3>
                <ul className="space-y-1 text-sm text-green-900">
                  <li>☐ Created Meta Developer account</li>
                  <li>☐ Created a Meta app</li>
                  <li>☐ Got Phone Number ID and Access Token (WhatsApp)</li>
                  <li>☐ Got Instagram Business ID and Access Token (Instagram)</li>
                  <li>☐ Created verify tokens (any random string)</li>
                  <li>☐ Filled forms below and saved</li>
                  <li>☐ Configured webhooks in Meta Developer Console</li>
                  <li>☐ Tested with a message!</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="whatsapp">
        <TabsList>
          <TabsTrigger value="whatsapp" className="flex items-center gap-2">
            <Phone className="h-4 w-4" />
            WhatsApp
            {whatsappConfigs.length > 0 && (
              <Badge variant="secondary" className="ml-1">
                {whatsappConfigs.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="instagram" className="flex items-center gap-2">
            <Instagram className="h-4 w-4" />
            Instagram
            {instagramConfigs.length > 0 && (
              <Badge variant="secondary" className="ml-1">
                {instagramConfigs.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* WhatsApp Tab */}
        <TabsContent value="whatsapp" className="mt-4 space-y-4">
          {/* Webhook Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Webhook Configuration</CardTitle>
              <CardDescription>
                Configure this webhook URL in your Meta Developer Console
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {isLocalhost && (
                <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                  <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-600" />
                  <div className="text-amber-800">
                    <strong>Warning:</strong> localhost URLs won't work with Meta webhooks.
                    For testing, use <a href="https://ngrok.com" target="_blank" rel="noopener noreferrer" className="underline">ngrok</a> to create a public URL, then set <code className="bg-amber-100 px-1 rounded">VITE_WEBHOOK_URL</code> in your .env file.
                    <br />
                    <span className="text-xs mt-1 block">Example: VITE_WEBHOOK_URL=https://abc123.ngrok-free.app</span>
                  </div>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Input value={getWebhookUrl('whatsapp')} readOnly className="flex-1 font-mono text-sm" />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => copyToClipboard(getWebhookUrl('whatsapp'), 'Webhook URL')}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex items-start gap-2 text-sm text-muted-foreground">
                <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>
                  Add this URL to your WhatsApp Business webhook settings in the{' '}
                  <a
                    href="https://developers.facebook.com/apps/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline inline-flex items-center gap-1"
                  >
                    Meta Developer Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Existing Configs */}
          {whatsappConfigs.map((config) => (
            <Card key={config.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-green-100 rounded-lg">
                      <Phone className="h-5 w-5 text-green-600" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">WhatsApp Business</CardTitle>
                      <CardDescription>Phone Number ID: {config.phone_number_id}</CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {config.is_verified ? (
                      <Badge variant="default" className="bg-green-600">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Verified
                      </Badge>
                    ) : (
                      <Badge variant="secondary">
                        <XCircle className="h-3 w-3 mr-1" />
                        Pending
                      </Badge>
                    )}
                    <Switch
                      checked={config.is_active}
                      onCheckedChange={() => handleToggleActive('whatsapp', config.id, config.is_active)}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-muted-foreground text-xs">Business Account ID</Label>
                    <p className="font-mono text-sm">{config.business_account_id}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground text-xs">Verify Token</Label>
                    <div className="flex items-center gap-2">
                      <p className="font-mono text-sm">{config.verify_token}</p>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={() => copyToClipboard(config.verify_token, 'Verify token')}
                      >
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => handleDeleteWhatsApp(config.id)}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Add New WhatsApp */}
          {showWhatsAppForm ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Plus className="h-5 w-5" />
                  Connect WhatsApp Business
                </CardTitle>
                <CardDescription>
                  Enter your WhatsApp Business API credentials from Meta Developer Console
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="wa_phone_id">Phone Number ID *</Label>
                    <Input
                      id="wa_phone_id"
                      placeholder="123456789012345"
                      value={whatsappForm.phone_number_id}
                      onChange={(e) =>
                        setWhatsappForm({ ...whatsappForm, phone_number_id: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="wa_business_id">Business Account ID *</Label>
                    <Input
                      id="wa_business_id"
                      placeholder="123456789012345"
                      value={whatsappForm.business_account_id}
                      onChange={(e) =>
                        setWhatsappForm({ ...whatsappForm, business_account_id: e.target.value })
                      }
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wa_access_token">Access Token *</Label>
                  <div className="flex gap-2">
                    <Input
                      id="wa_access_token"
                      type={showAccessTokens['wa_new'] ? 'text' : 'password'}
                      placeholder="EAAxxxxxxx..."
                      value={whatsappForm.access_token}
                      onChange={(e) =>
                        setWhatsappForm({ ...whatsappForm, access_token: e.target.value })
                      }
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() =>
                        setShowAccessTokens({ ...showAccessTokens, wa_new: !showAccessTokens['wa_new'] })
                      }
                    >
                      {showAccessTokens['wa_new'] ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="wa_verify_token">Verify Token *</Label>
                  <Input
                    id="wa_verify_token"
                    placeholder="my_verify_token_123"
                    value={whatsappForm.verify_token}
                    onChange={(e) =>
                      setWhatsappForm({ ...whatsappForm, verify_token: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Create your own verify token. You'll need to use the same token in Meta's webhook configuration.
                  </p>
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setShowWhatsAppForm(false)}>
                    Cancel
                  </Button>
                  <Button onClick={handleSaveWhatsApp} disabled={saving}>
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? 'Saving...' : 'Save Configuration'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Button onClick={() => setShowWhatsAppForm(true)} className="w-full">
              <Plus className="h-4 w-4 mr-2" />
              Connect WhatsApp Business
            </Button>
          )}
        </TabsContent>

        {/* Instagram Tab */}
        <TabsContent value="instagram" className="mt-4 space-y-4">
          {/* Webhook Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Webhook Configuration</CardTitle>
              <CardDescription>
                Configure this webhook URL in your Meta Developer Console
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <Input value={getWebhookUrl('instagram')} readOnly className="flex-1 font-mono text-sm" />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => copyToClipboard(getWebhookUrl('instagram'), 'Webhook URL')}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex items-start gap-2 text-sm text-muted-foreground">
                <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>
                  Add this URL to your Instagram webhook settings in the{' '}
                  <a
                    href="https://developers.facebook.com/apps/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline inline-flex items-center gap-1"
                  >
                    Meta Developer Console
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Existing Configs */}
          {instagramConfigs.map((config) => (
            <Card key={config.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-pink-100 rounded-lg">
                      <Instagram className="h-5 w-5 text-pink-600" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">Instagram Business</CardTitle>
                      <CardDescription>Business ID: {config.instagram_business_id}</CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {config.is_verified ? (
                      <Badge variant="default" className="bg-green-600">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Verified
                      </Badge>
                    ) : (
                      <Badge variant="secondary">
                        <XCircle className="h-3 w-3 mr-1" />
                        Pending
                      </Badge>
                    )}
                    <Switch
                      checked={config.is_active}
                      onCheckedChange={() => handleToggleActive('instagram', config.id, config.is_active)}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-muted-foreground text-xs">Page ID</Label>
                    <p className="font-mono text-sm">{config.page_id}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground text-xs">Verify Token</Label>
                    <div className="flex items-center gap-2">
                      <p className="font-mono text-sm">{config.verify_token}</p>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={() => copyToClipboard(config.verify_token, 'Verify token')}
                      >
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => handleDeleteInstagram(config.id)}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Add New Instagram */}
          {showInstagramForm ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Plus className="h-5 w-5" />
                  Connect Instagram Business
                </CardTitle>
                <CardDescription>
                  Enter your Instagram Business credentials from Meta Developer Console
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="ig_business_id">Instagram Business ID *</Label>
                    <Input
                      id="ig_business_id"
                      placeholder="123456789012345"
                      value={instagramForm.instagram_business_id}
                      onChange={(e) =>
                        setInstagramForm({ ...instagramForm, instagram_business_id: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="ig_page_id">Facebook Page ID *</Label>
                    <Input
                      id="ig_page_id"
                      placeholder="123456789012345"
                      value={instagramForm.page_id}
                      onChange={(e) =>
                        setInstagramForm({ ...instagramForm, page_id: e.target.value })
                      }
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ig_access_token">Access Token *</Label>
                  <div className="flex gap-2">
                    <Input
                      id="ig_access_token"
                      type={showAccessTokens['ig_new'] ? 'text' : 'password'}
                      placeholder="EAAxxxxxxx..."
                      value={instagramForm.access_token}
                      onChange={(e) =>
                        setInstagramForm({ ...instagramForm, access_token: e.target.value })
                      }
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() =>
                        setShowAccessTokens({ ...showAccessTokens, ig_new: !showAccessTokens['ig_new'] })
                      }
                    >
                      {showAccessTokens['ig_new'] ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ig_verify_token">Verify Token *</Label>
                  <Input
                    id="ig_verify_token"
                    placeholder="my_verify_token_123"
                    value={instagramForm.verify_token}
                    onChange={(e) =>
                      setInstagramForm({ ...instagramForm, verify_token: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Create your own verify token. You'll need to use the same token in Meta's webhook configuration.
                  </p>
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setShowInstagramForm(false)}>
                    Cancel
                  </Button>
                  <Button onClick={handleSaveInstagram} disabled={saving}>
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? 'Saving...' : 'Save Configuration'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Button onClick={() => setShowInstagramForm(true)} className="w-full">
              <Plus className="h-4 w-4 mr-2" />
              Connect Instagram Business
            </Button>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
