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
import { Checkbox } from '@/components/ui/checkbox'
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
  UserCog,
  MessageSquare,
  Clock,
  Send,
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

interface TwilioConfig {
  id: string
  organization: string
  account_sid: string
  auth_token?: string
  from_number: string
  is_sandbox: boolean
  sandbox_join_code: string
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

interface ManagerNumber {
  id: string
  organization: string
  phone_number: string
  name: string
  role: string
  can_update_hours: boolean
  can_respond_queries: boolean
  can_view_bookings: boolean
  is_active: boolean
  created_at: string
  user_email?: string
}

interface TemporaryOverride {
  id: string
  organization: string
  override_type: string
  original_message: string
  processed_content: string
  priority: string
  expires_at: string | null
  is_active: boolean
  is_expired: boolean
  created_at: string
  created_by_manager_name: string | null
}

interface ManagerQuery {
  id: string
  organization: string
  conversation: string
  customer_query: string
  query_summary: string
  manager_response: string | null
  status: string
  created_at: string
  response_received_at: string | null
  manager_name: string
  customer_name: string
}

export function ChannelsPage() {
  const { t } = useTranslation()
  const { currentOrganization, setCurrentOrganization } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const [whatsappConfigs, setWhatsappConfigs] = useState<WhatsAppConfig[]>([])
  const [twilioConfigs, setTwilioConfigs] = useState<TwilioConfig[]>([])
  const [instagramConfigs, setInstagramConfigs] = useState<InstagramConfig[]>([])
  const [managerNumbers, setManagerNumbers] = useState<ManagerNumber[]>([])
  const [temporaryOverrides, setTemporaryOverrides] = useState<TemporaryOverride[]>([])
  const [managerQueries, setManagerQueries] = useState<ManagerQuery[]>([])
  const [verifyingId, setVerifyingId] = useState<string | null>(null)
  const [whatsappReady, setWhatsappReady] = useState(false)
  const [healthData, setHealthData] = useState<Record<string, any>>({})
  const [loadingHealth, setLoadingHealth] = useState<string | null>(null)

  const [showWhatsAppForm, setShowWhatsAppForm] = useState(false)
  const [showTwilioForm, setShowTwilioForm] = useState(false)
  const [showInstagramForm, setShowInstagramForm] = useState(false)
  const [showManagerForm, setShowManagerForm] = useState(false)
  const [twilioTestTo, setTwilioTestTo] = useState('')
  const [twilioBusy, setTwilioBusy] = useState<string | null>(null)
  const [showAccessTokens, setShowAccessTokens] = useState<Record<string, boolean>>({})
  const [showGuide, setShowGuide] = useState(false)
  const [sendingTestMessage, setSendingTestMessage] = useState<string | null>(null)

  const [whatsappForm, setWhatsappForm] = useState({
    phone_number_id: '',
    business_account_id: '',
    access_token: '',
    verify_token: '',
  })

  const [twilioForm, setTwilioForm] = useState({
    account_sid: '',
    auth_token: '',
    from_number: '+14155238886',
    is_sandbox: true,
    sandbox_join_code: '',
  })

  const [instagramForm, setInstagramForm] = useState({
    instagram_business_id: '',
    page_id: '',
    access_token: '',
    verify_token: '',
  })

  const [managerForm, setManagerForm] = useState({
    phone_number: '',
    name: '',
    role: 'Manager',
    can_update_hours: true,
    can_respond_queries: true,
    can_view_bookings: true,
  })

  // Check if organization has Power plan (only needed for Instagram)
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
      const [whatsapp, twilio, instagram, managers, overrides, queries] = await Promise.all([
        channelsApi.whatsapp.list({ organization: currentOrganization.id }),
        channelsApi.twilio.list({ organization: currentOrganization.id }).catch(() => []),
        channelsApi.instagram.list({ organization: currentOrganization.id }),
        channelsApi.managerNumbers.list({ organization: currentOrganization.id }).catch(() => []),
        channelsApi.temporaryOverrides.list({ organization: currentOrganization.id, active: 'true' }).catch(() => []),
        channelsApi.managerQueries.list({ organization: currentOrganization.id }).catch(() => []),
      ])
      setWhatsappConfigs(whatsapp)
      setTwilioConfigs(twilio)
      setInstagramConfigs(instagram)
      setManagerNumbers(managers)
      setTemporaryOverrides(overrides)
      setManagerQueries(queries)
      
      // Check if WhatsApp is ready for manager numbers
      try {
        const readyCheck = await channelsApi.managerNumbers.checkWhatsAppReady(currentOrganization.id)
        setWhatsappReady(readyCheck.ready)
      } catch {
        setWhatsappReady(false)
      }
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
      
      // Show verifying state
      setVerifyingId(newConfig.id)
      setWhatsappConfigs([...whatsappConfigs, { ...newConfig, is_verified: false }])
      
      // Auto-verification happens on backend - wait a moment then fetch updated config
      setTimeout(async () => {
        try {
          const updatedConfig = await channelsApi.whatsapp.get(newConfig.id)
          setWhatsappConfigs(configs => 
            configs.map(c => c.id === newConfig.id ? updatedConfig : c)
          )
          setVerifyingId(null)
          
          if (updatedConfig.is_verified) {
            toast({
              title: 'WhatsApp Connected & Verified! ✅',
              description: 'Your credentials are valid and WhatsApp is ready to use.',
            })
          } else {
            toast({
              title: 'WhatsApp Connected',
              description: 'Configuration saved, but credentials verification failed. Please check your access token.',
              variant: 'destructive',
            })
          }
        } catch (e) {
          setVerifyingId(null)
          toast({
            title: 'WhatsApp Connected',
            description: 'Configuration saved. Please refresh to see verification status.',
          })
        }
      }, 1500) // Give backend time to verify
      
      setWhatsappForm({ phone_number_id: '', business_account_id: '', access_token: '', verify_token: '' })
      setShowWhatsAppForm(false)
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
      
      // Show verifying state
      setVerifyingId(newConfig.id)
      setInstagramConfigs([...instagramConfigs, { ...newConfig, is_verified: false }])
      
      // Auto-verification happens on backend - wait a moment then fetch updated config
      setTimeout(async () => {
        try {
          const updatedConfig = await channelsApi.instagram.get(newConfig.id)
          setInstagramConfigs(configs => 
            configs.map(c => c.id === newConfig.id ? updatedConfig : c)
          )
          setVerifyingId(null)
          
          if (updatedConfig.is_verified) {
            toast({
              title: 'Instagram Connected & Verified! ✅',
              description: 'Your credentials are valid and Instagram is ready to use.',
            })
          } else {
            toast({
              title: 'Instagram Connected',
              description: 'Configuration saved, but credentials verification failed. Please check your access token.',
              variant: 'destructive',
            })
          }
        } catch (e) {
          setVerifyingId(null)
          toast({
            title: 'Instagram Connected',
            description: 'Configuration saved. Please refresh to see verification status.',
          })
        }
      }, 1500) // Give backend time to verify
      
      setInstagramForm({ instagram_business_id: '', page_id: '', access_token: '', verify_token: '' })
      setShowInstagramForm(false)
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

  // Manager Number Handlers
  const handleSaveManager = async () => {
    if (!currentOrganization) return

    setSaving(true)
    try {
      const newManager = await channelsApi.managerNumbers.create({
        organization: currentOrganization.id,
        ...managerForm,
      })
      setManagerNumbers([...managerNumbers, newManager])
      setManagerForm({
        phone_number: '',
        name: '',
        role: 'Manager',
        can_update_hours: true,
        can_respond_queries: true,
        can_view_bookings: true,
      })
      setShowManagerForm(false)
      toast({
        title: 'Manager Added',
        description: `${newManager.name} can now send commands to the chatbot via WhatsApp.`,
      })
    } catch (error: any) {
      console.error('Error saving manager:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: error.response?.data?.detail || error.response?.data?.non_field_errors?.[0] || 'Failed to add manager.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteManager = async (id: string) => {
    if (!confirm('Are you sure you want to remove this manager?')) return

    try {
      await channelsApi.managerNumbers.delete(id)
      setManagerNumbers(managerNumbers.filter((m) => m.id !== id))
      toast({
        title: 'Manager Removed',
        description: 'Manager number has been removed.',
      })
    } catch (error) {
      console.error('Error deleting manager:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to remove manager.',
      })
    }
  }

  const handleToggleManagerActive = async (id: string, isActive: boolean) => {
    try {
      await channelsApi.managerNumbers.update(id, { is_active: !isActive })
      setManagerNumbers(
        managerNumbers.map((m) => (m.id === id ? { ...m, is_active: !isActive } : m))
      )
      toast({
        title: isActive ? 'Manager Disabled' : 'Manager Enabled',
        description: `Manager is now ${isActive ? 'inactive' : 'active'}.`,
      })
    } catch (error) {
      console.error('Error toggling manager:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to update manager status.',
      })
    }
  }

  const handleSendTestMessage = async (id: string) => {
    setSendingTestMessage(id)
    try {
      await channelsApi.managerNumbers.testMessage(id)
      toast({
        title: 'Test Message Sent',
        description: 'A test message has been sent to the manager\'s WhatsApp.',
      })
    } catch (error: any) {
      console.error('Error sending test message:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: error.response?.data?.error || 'Failed to send test message.',
      })
    } finally {
      setSendingTestMessage(null)
    }
  }

  const handleHealthCheck = async (type: 'whatsapp' | 'instagram', id: string) => {
    setLoadingHealth(id)
    try {
      const { api } = await import('@/services/api')
      const response = await api.get(`/channels/${type}-config/${id}/health/`)
      setHealthData(prev => ({ ...prev, [id]: response.data }))
    } catch (error: any) {
      toast({
        variant: 'destructive',
        title: 'Health check failed',
        description: error.response?.data?.detail || 'Could not reach health endpoint.',
      })
    } finally {
      setLoadingHealth(null)
    }
  }

  const handleDeactivateOverride = async (id: string) => {
    try {
      await channelsApi.temporaryOverrides.deactivate(id)
      setTemporaryOverrides(
        temporaryOverrides.map((o) => (o.id === id ? { ...o, is_active: false } : o))
      )
      toast({
        title: 'Override Deactivated',
        description: 'The temporary override has been deactivated.',
      })
    } catch (error) {
      console.error('Error deactivating override:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to deactivate override.',
      })
    }
  }

  const handleDeactivateAllOverrides = async () => {
    if (!currentOrganization) return
    if (!confirm('Are you sure you want to deactivate all temporary overrides?')) return

    try {
      await channelsApi.temporaryOverrides.deactivateAll(currentOrganization.id)
      setTemporaryOverrides(
        temporaryOverrides.map((o) => ({ ...o, is_active: false }))
      )
      toast({
        title: 'All Overrides Deactivated',
        description: 'All temporary overrides have been deactivated.',
      })
    } catch (error) {
      console.error('Error deactivating overrides:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to deactivate overrides.',
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

  const handleSaveTwilio = async () => {
    if (!currentOrganization) return
    if (!twilioForm.account_sid.trim() || !twilioForm.auth_token.trim() || !twilioForm.from_number.trim()) {
      toast({ variant: 'destructive', title: 'Missing fields', description: 'SID, Auth Token, and From Number are all required.' })
      return
    }
    setSaving(true)
    try {
      const created = await channelsApi.twilio.create({
        organization: currentOrganization.id,
        account_sid: twilioForm.account_sid.trim(),
        auth_token: twilioForm.auth_token.trim(),
        from_number: twilioForm.from_number.trim(),
        is_sandbox: twilioForm.is_sandbox,
        sandbox_join_code: twilioForm.sandbox_join_code.trim(),
      })
      // Activate by default — minimal manual setup
      const activated = await channelsApi.twilio.update(created.id, { is_active: true })
      setTwilioConfigs([...twilioConfigs, activated])
      setShowTwilioForm(false)
      setTwilioForm({ account_sid: '', auth_token: '', from_number: '+14155238886', is_sandbox: true, sandbox_join_code: '' })
      toast({ title: 'Twilio connected', description: 'WhatsApp via Twilio is configured and active.' })
    } catch (error: any) {
      toast({
        variant: 'destructive',
        title: 'Failed to save',
        description: error.response?.data?.detail || error.response?.data?.error || 'Could not connect Twilio.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteTwilio = async (id: string) => {
    if (!confirm('Remove this Twilio configuration?')) return
    try {
      await channelsApi.twilio.delete(id)
      setTwilioConfigs(twilioConfigs.filter((c) => c.id !== id))
      toast({ title: 'Removed', description: 'Twilio configuration deleted.' })
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Could not delete.' })
    }
  }

  const handleToggleTwilio = async (id: string, isActive: boolean) => {
    try {
      const updated = await channelsApi.twilio.update(id, { is_active: !isActive })
      setTwilioConfigs(twilioConfigs.map((c) => (c.id === id ? { ...c, is_active: updated.is_active } : c)))
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Could not toggle.' })
    }
  }

  const handleTwilioTest = async (id: string) => {
    if (!twilioTestTo.trim()) {
      toast({ variant: 'destructive', title: 'Phone required', description: 'Enter a phone number in E.164, e.g. +9779705651002.' })
      return
    }
    setTwilioBusy(id)
    try {
      const res = await channelsApi.twilio.testMessage(id, twilioTestTo.trim())
      if (res.success) {
        toast({ title: 'Test sent', description: `Message SID: ${res.message_sid}` })
      } else {
        toast({ variant: 'destructive', title: 'Send failed', description: res.error || 'Twilio rejected the request.' })
      }
    } catch (e: any) {
      toast({ variant: 'destructive', title: 'Send failed', description: e.response?.data?.error || 'Network error.' })
    } finally {
      setTwilioBusy(null)
    }
  }

  const getWebhookUrl = (type: 'whatsapp' | 'instagram' | 'twilio') => {
    // Use API URL from environment, fallback to kribaat.com for production
    const apiUrl = import.meta.env.VITE_API_URL || '';
    if (apiUrl && !apiUrl.includes('localhost')) {
      // Production: extract base URL and build webhook URL
      const baseUrl = apiUrl.replace(/\/api$/, '');
      return `${baseUrl}/api/webhooks/${type}/`;
    }
    // Development fallback
    return `http://localhost:8000/api/webhooks/${type}/`;
  }

  const isLocalhost = getWebhookUrl('whatsapp').includes('localhost')

  if (!currentOrganization) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Please select an organization first.</p>
      </div>
    )
  }

  // Remove Power Plan Gate - WhatsApp is now available on all plans
  // Instagram is still Power plan only (handled in the Instagram tab)

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

      <Tabs defaultValue="twilio">
        <TabsList>
          <TabsTrigger value="twilio" className="flex items-center gap-2">
            <Send className="h-4 w-4" />
            Twilio (Easy Setup)
            {twilioConfigs.length > 0 && (
              <Badge variant="secondary" className="ml-1">
                {twilioConfigs.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="whatsapp" className="flex items-center gap-2">
            <Phone className="h-4 w-4" />
            WhatsApp (Meta)
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
          <TabsTrigger value="managers" className="flex items-center gap-2">
            <UserCog className="h-4 w-4" />
            Manager Control
            {managerNumbers.length > 0 && (
              <Badge variant="secondary" className="ml-1">
                {managerNumbers.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Twilio Tab — easiest path: WhatsApp Sandbox */}
        <TabsContent value="twilio" className="mt-4 space-y-4">
          <Card className="border-emerald-200 bg-emerald-50">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Send className="h-5 w-5 text-emerald-700" />
                Twilio WhatsApp — Easy Setup
              </CardTitle>
              <CardDescription className="text-emerald-900">
                Skip the Meta Business approval. Use Twilio's WhatsApp Sandbox to start chatting in minutes.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-emerald-900">
              <ol className="list-decimal list-inside space-y-1">
                <li>Create a free Twilio account at <a className="underline" href="https://www.twilio.com/try-twilio" target="_blank" rel="noopener noreferrer">twilio.com/try-twilio</a>.</li>
                <li>Go to <strong>Messaging → Try it out → Send a WhatsApp message</strong>. Note your Sandbox number (usually <code>+1 415 523 8886</code>) and join code (e.g. <code>join using-pink</code>).</li>
                <li>Customers send <code>join &lt;your-code&gt;</code> from WhatsApp to opt in.</li>
                <li>In Sandbox settings, paste the webhook URL below into <strong>"When a message comes in"</strong>.</li>
                <li>Paste your SID, Auth Token, and Sandbox number below — that's it.</li>
              </ol>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Webhook URL</CardTitle>
              <CardDescription>Paste this into Twilio Sandbox → "When a message comes in" (POST).</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Input value={getWebhookUrl('twilio')} readOnly className="flex-1 font-mono text-sm" />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => copyToClipboard(getWebhookUrl('twilio'), 'Twilio webhook URL')}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Configure at <a className="underline" href="https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn" target="_blank" rel="noopener noreferrer">Twilio Console → WhatsApp Sandbox <ExternalLink className="inline h-3 w-3" /></a>
              </p>
            </CardContent>
          </Card>

          {/* Existing Twilio configs */}
          {twilioConfigs.map((config) => (
            <Card key={config.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-emerald-100 rounded-lg">
                      <Send className="h-5 w-5 text-emerald-700" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">Twilio WhatsApp{config.is_sandbox ? ' (Sandbox)' : ''}</CardTitle>
                      <CardDescription>From: {config.from_number}</CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {config.is_verified ? (
                      <Badge variant="default" className="bg-emerald-600">
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
                      onCheckedChange={() => handleToggleTwilio(config.id, config.is_active)}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <Label className="text-muted-foreground text-xs">Account SID</Label>
                    <p className="font-mono">{config.account_sid?.slice(0, 8)}…{config.account_sid?.slice(-4)}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground text-xs">Mode</Label>
                    <p>{config.is_sandbox ? `Sandbox${config.sandbox_join_code ? ` (join ${config.sandbox_join_code})` : ''}` : 'Production sender'}</p>
                  </div>
                </div>

                <div className="border-t pt-3 space-y-2">
                  <Label htmlFor={`twilio_test_${config.id}`}>Send test message</Label>
                  <div className="flex gap-2">
                    <Input
                      id={`twilio_test_${config.id}`}
                      placeholder="+9779705651002"
                      value={twilioTestTo}
                      onChange={(e) => setTwilioTestTo(e.target.value)}
                      className="font-mono text-sm"
                    />
                    <Button
                      variant="outline"
                      onClick={() => handleTwilioTest(config.id)}
                      disabled={twilioBusy === config.id}
                    >
                      {twilioBusy === config.id ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                      Send
                    </Button>
                  </div>
                  {config.is_sandbox && (
                    <p className="text-xs text-muted-foreground">
                      Recipient must have already sent <code>join {config.sandbox_join_code || '&lt;your-code&gt;'}</code> from their WhatsApp to <code>{config.from_number}</code>.
                    </p>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => handleDeleteTwilio(config.id)}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Add Twilio config */}
          {showTwilioForm ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Plus className="h-5 w-5" />
                  Connect Twilio WhatsApp
                </CardTitle>
                <CardDescription>
                  Find these in your Twilio Console → Account → API keys & tokens.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="tw_sid">Account SID *</Label>
                  <Input
                    id="tw_sid"
                    placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    value={twilioForm.account_sid}
                    onChange={(e) => setTwilioForm({ ...twilioForm, account_sid: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tw_token">Auth Token *</Label>
                  <div className="flex gap-2">
                    <Input
                      id="tw_token"
                      type={showAccessTokens['tw_new'] ? 'text' : 'password'}
                      placeholder="your-twilio-auth-token"
                      value={twilioForm.auth_token}
                      onChange={(e) => setTwilioForm({ ...twilioForm, auth_token: e.target.value })}
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => setShowAccessTokens({ ...showAccessTokens, tw_new: !showAccessTokens['tw_new'] })}
                    >
                      {showAccessTokens['tw_new'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="tw_from">From Number *</Label>
                    <Input
                      id="tw_from"
                      placeholder="+14155238886"
                      value={twilioForm.from_number}
                      onChange={(e) => setTwilioForm({ ...twilioForm, from_number: e.target.value })}
                    />
                    <p className="text-xs text-muted-foreground">Twilio Sandbox default: <code>+14155238886</code></p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="tw_join">Sandbox Join Code</Label>
                    <Input
                      id="tw_join"
                      placeholder="using-pink"
                      value={twilioForm.sandbox_join_code}
                      onChange={(e) => setTwilioForm({ ...twilioForm, sandbox_join_code: e.target.value })}
                    />
                    <p className="text-xs text-muted-foreground">For sandbox only; customers text <code>join &lt;code&gt;</code> to opt in.</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="tw_sandbox"
                    checked={twilioForm.is_sandbox}
                    onCheckedChange={(checked) => setTwilioForm({ ...twilioForm, is_sandbox: !!checked })}
                  />
                  <Label htmlFor="tw_sandbox" className="text-sm">This is a Twilio Sandbox sender (uncheck for an approved production number)</Label>
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setShowTwilioForm(false)}>Cancel</Button>
                  <Button onClick={handleSaveTwilio} disabled={saving}>
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? 'Saving...' : 'Save & Activate'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            twilioConfigs.length === 0 && (
              <Button onClick={() => setShowTwilioForm(true)} className="w-full">
                <Plus className="h-4 w-4 mr-2" />
                Connect Twilio WhatsApp (recommended)
              </Button>
            )
          )}
        </TabsContent>

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
                    <strong>Development Mode:</strong> localhost URLs won't work with Meta webhooks.
                    For production, deploy your app to a public URL (e.g., https://kribaat.com) and set <code className="bg-amber-100 px-1 rounded">VITE_API_URL</code> in your .env file.
                    <br />
                    <span className="text-xs mt-1 block">Example: VITE_API_URL=https://kribaat.com/api</span>
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
                    {verifyingId === config.id ? (
                      <Badge variant="secondary" className="bg-blue-100">
                        <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                        Verifying...
                      </Badge>
                    ) : config.is_verified ? (
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
                {/* Health Check Panel */}
                {healthData[config.id] && (
                  <div className={`p-3 rounded-lg border text-sm space-y-2 ${healthData[config.id].overall_status === 'healthy' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                    <div className="font-semibold flex items-center gap-2">
                      {healthData[config.id].overall_status === 'healthy'
                        ? <><CheckCircle2 className="h-4 w-4 text-green-600" /> All systems healthy</>
                        : <><XCircle className="h-4 w-4 text-red-600" /> Issues detected</>}
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-xs">
                      <span>API Connection:</span>
                      <span className={healthData[config.id].api_connection === 'ok' ? 'text-green-700 font-medium' : 'text-red-700 font-medium'}>
                        {healthData[config.id].api_connection === 'ok' ? '✅ Connected' : `❌ ${healthData[config.id].api_connection}`}
                      </span>
                      <span>Webhooks (24h):</span>
                      <span>total={healthData[config.id].recent_webhooks?.total_24h}, processed={healthData[config.id].recent_webhooks?.processed_24h}, failed={healthData[config.id].recent_webhooks?.failed_24h}</span>
                    </div>
                    {healthData[config.id].issues?.length > 0 && (
                      <ul className="list-disc list-inside space-y-1 text-xs text-red-800">
                        {healthData[config.id].issues.map((issue: string, i: number) => (
                          <li key={i}>{issue}</li>
                        ))}
                      </ul>
                    )}
                    {healthData[config.id].phone_info && (
                      <p className="text-xs text-green-800">
                        Phone: {healthData[config.id].phone_info.display_phone_number || healthData[config.id].phone_info.id} — {healthData[config.id].phone_info.verified_name || 'Verified'}
                      </p>
                    )}
                  </div>
                )}
                <div className="flex justify-between items-center">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleHealthCheck('whatsapp', config.id)}
                    disabled={loadingHealth === config.id}
                  >
                    {loadingHealth === config.id
                      ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" /> Checking...</>
                      : <><CheckCircle2 className="h-4 w-4 mr-2" /> Run Health Check</>}
                  </Button>
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
          {/* Power Plan Gate for Instagram */}
          {!isPowerPlan ? (
            <Card className="border-amber-200 bg-amber-50">
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  <div className="p-3 bg-amber-100 rounded-full">
                    <Crown className="h-8 w-8 text-amber-600" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-amber-900">Power Plan Required</h3>
                    <p className="text-amber-800 mt-1">
                      Instagram integration is available on the Power plan only.
                      Contact your administrator to upgrade your organization.
                    </p>
                    <div className="mt-4 space-y-2">
                      <p className="text-sm font-medium text-amber-900">Power Plan includes:</p>
                      <ul className="text-sm text-amber-800 space-y-1">
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
                        <strong>💡 Good News:</strong> You already have WhatsApp on your Basic plan! Upgrade to Power to unlock Instagram.
                      </p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
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
                    {verifyingId === config.id ? (
                      <Badge variant="secondary" className="bg-blue-100">
                        <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                        Verifying...
                      </Badge>
                    ) : config.is_verified ? (
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
            </>
          )}
        </TabsContent>

        {/* Manager Control Tab */}
        <TabsContent value="managers" className="mt-4 space-y-4">
          {/* Info Card */}
          <Card className="border-blue-200 bg-blue-50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-blue-900">
                <UserCog className="h-5 w-5" />
                Manager WhatsApp Control
              </CardTitle>
              <CardDescription className="text-blue-800">
                Allow managers to control the chatbot directly via WhatsApp without logging into the panel.
                Managers can update hours, respond to escalated queries, and more!
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white p-3 rounded-lg border border-blue-200">
                  <h4 className="font-medium text-blue-900 flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Update Hours
                  </h4>
                  <p className="text-sm text-blue-700 mt-1">
                    "We're closed today from 5PM" - chatbot updates instantly
                  </p>
                </div>
                <div className="bg-white p-3 rounded-lg border border-blue-200">
                  <h4 className="font-medium text-blue-900 flex items-center gap-2">
                    <MessageSquare className="h-4 w-4" />
                    Answer Queries
                  </h4>
                  <p className="text-sm text-blue-700 mt-1">
                    Chatbot asks manager when unsure, formats reply professionally
                  </p>
                </div>
                <div className="bg-white p-3 rounded-lg border border-blue-200">
                  <h4 className="font-medium text-blue-900 flex items-center gap-2">
                    <Phone className="h-4 w-4" />
                    No Extra Setup
                  </h4>
                  <p className="text-sm text-blue-700 mt-1">
                    Uses your existing WhatsApp Business config automatically
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* WhatsApp Not Ready Warning */}
          {!whatsappReady && (
            <Card className="border-amber-200 bg-amber-50">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-medium text-amber-900">WhatsApp Not Configured</h4>
                    <p className="text-sm text-amber-800 mt-1">
                      Please set up WhatsApp Business in the WhatsApp tab first before adding manager numbers.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Existing Manager Numbers */}
          {managerNumbers.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">Registered Managers</h3>
              {managerNumbers.map((manager) => (
                <Card key={manager.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-purple-100 rounded-lg">
                          <UserCog className="h-5 w-5 text-purple-600" />
                        </div>
                        <div>
                          <h4 className="font-medium">{manager.name}</h4>
                          <p className="text-sm text-muted-foreground">
                            {manager.phone_number} • {manager.role}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant={manager.is_active ? "default" : "secondary"}>
                          {manager.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                        <Switch
                          checked={manager.is_active}
                          onCheckedChange={() => handleToggleManagerActive(manager.id, manager.is_active)}
                        />
                      </div>
                    </div>
                    
                    <div className="mt-4 flex flex-wrap gap-2">
                      {manager.can_update_hours && (
                        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                          <Clock className="h-3 w-3 mr-1" />
                          Update Hours
                        </Badge>
                      )}
                      {manager.can_respond_queries && (
                        <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                          <MessageSquare className="h-3 w-3 mr-1" />
                          Answer Queries
                        </Badge>
                      )}
                      {manager.can_view_bookings && (
                        <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200">
                          <Eye className="h-3 w-3 mr-1" />
                          View Bookings
                        </Badge>
                      )}
                    </div>

                    <div className="mt-4 flex justify-between items-center">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleSendTestMessage(manager.id)}
                        disabled={sendingTestMessage === manager.id || !whatsappReady}
                      >
                        {sendingTestMessage === manager.id ? (
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Send className="h-4 w-4 mr-2" />
                        )}
                        Send Test Message
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDeleteManager(manager.id)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Remove
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Add Manager Form */}
          {showManagerForm ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Plus className="h-5 w-5" />
                  Add Manager Number
                </CardTitle>
                <CardDescription>
                  Add a WhatsApp number that can control the chatbot
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="manager_phone">Phone Number *</Label>
                    <Input
                      id="manager_phone"
                      placeholder="+1234567890"
                      value={managerForm.phone_number}
                      onChange={(e) => setManagerForm({ ...managerForm, phone_number: e.target.value })}
                    />
                    <p className="text-xs text-muted-foreground">
                      Include country code (e.g., +1 for US)
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="manager_name">Name *</Label>
                    <Input
                      id="manager_name"
                      placeholder="John Smith"
                      value={managerForm.name}
                      onChange={(e) => setManagerForm({ ...managerForm, name: e.target.value })}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="manager_role">Role</Label>
                  <Input
                    id="manager_role"
                    placeholder="Manager"
                    value={managerForm.role}
                    onChange={(e) => setManagerForm({ ...managerForm, role: e.target.value })}
                  />
                </div>
                
                <div className="space-y-3">
                  <Label>Permissions</Label>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="can_update_hours"
                        checked={managerForm.can_update_hours}
                        onCheckedChange={(checked) => 
                          setManagerForm({ ...managerForm, can_update_hours: !!checked })
                        }
                      />
                      <Label htmlFor="can_update_hours" className="text-sm font-normal">
                        Update Business Hours
                      </Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="can_respond_queries"
                        checked={managerForm.can_respond_queries}
                        onCheckedChange={(checked) => 
                          setManagerForm({ ...managerForm, can_respond_queries: !!checked })
                        }
                      />
                      <Label htmlFor="can_respond_queries" className="text-sm font-normal">
                        Respond to Queries
                      </Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="can_view_bookings"
                        checked={managerForm.can_view_bookings}
                        onCheckedChange={(checked) => 
                          setManagerForm({ ...managerForm, can_view_bookings: !!checked })
                        }
                      />
                      <Label htmlFor="can_view_bookings" className="text-sm font-normal">
                        View Bookings
                      </Label>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setShowManagerForm(false)}>
                    Cancel
                  </Button>
                  <Button 
                    onClick={handleSaveManager} 
                    disabled={saving || !managerForm.phone_number || !managerForm.name}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? 'Adding...' : 'Add Manager'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Button 
              onClick={() => setShowManagerForm(true)} 
              className="w-full"
              disabled={!whatsappReady}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Manager Number
            </Button>
          )}

          {/* Active Temporary Overrides */}
          {temporaryOverrides.filter(o => o.is_active && !o.is_expired).length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">Active Temporary Overrides</h3>
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={handleDeactivateAllOverrides}
                >
                  Deactivate All
                </Button>
              </div>
              {temporaryOverrides.filter(o => o.is_active && !o.is_expired).map((override) => (
                <Card key={override.id} className="border-amber-200 bg-amber-50">
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <Badge variant="outline" className="mb-2 bg-amber-100 text-amber-800 border-amber-300">
                          {override.override_type.replace('_', ' ').toUpperCase()}
                        </Badge>
                        <p className="text-amber-900">{override.original_message}</p>
                        <p className="text-sm text-amber-700 mt-1">
                          Created by {override.created_by_manager_name || 'System'} • 
                          {override.expires_at ? ` Expires: ${new Date(override.expires_at).toLocaleString()}` : ' No expiry'}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeactivateOverride(override.id)}
                      >
                        <XCircle className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Pending Manager Queries */}
          {managerQueries.filter(q => q.status === 'pending').length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-amber-500" />
                Pending Manager Queries
              </h3>
              {managerQueries.filter(q => q.status === 'pending').map((query) => (
                <Card key={query.id} className="border-amber-200">
                  <CardContent className="pt-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Badge variant="secondary" className="bg-amber-100 text-amber-800">
                          Waiting for {query.manager_name}
                        </Badge>
                        <span className="text-sm text-muted-foreground">
                          {new Date(query.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="font-medium">Customer Question:</p>
                      <p className="text-muted-foreground bg-gray-50 p-2 rounded">
                        {query.customer_query}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Customer: {query.customer_name}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Manager Commands Help */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Manager Commands Reference</CardTitle>
              <CardDescription>
                Managers can send these commands via WhatsApp to control the chatbot
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm">
                <div className="bg-gray-50 p-3 rounded-lg">
                  <code className="font-mono text-purple-600">"We are closed today"</code>
                  <p className="text-muted-foreground mt-1">Temporarily closes the business for the day</p>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <code className="font-mono text-purple-600">"Closing early at 5PM today"</code>
                  <p className="text-muted-foreground mt-1">Updates closing time temporarily</p>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <code className="font-mono text-purple-600">"Fully booked for tonight"</code>
                  <p className="text-muted-foreground mt-1">Marks the business as fully booked</p>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <code className="font-mono text-purple-600">"STATUS"</code>
                  <p className="text-muted-foreground mt-1">Get today's stats and active overrides</p>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <code className="font-mono text-purple-600">"HELP"</code>
                  <p className="text-muted-foreground mt-1">List all available commands</p>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg border-l-4 border-blue-500">
                  <p className="font-medium text-blue-900">Replying to Queries</p>
                  <p className="text-muted-foreground mt-1">
                    When the chatbot asks you a question about a customer, simply reply normally.
                    The chatbot will format your answer professionally for the customer.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
