import { useEffect, useState } from 'react'
import { useAuthStore } from '@/store/auth'
import { knowledgeApi, faqApi, locationsApi } from '@/services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import {
  BookOpen,
  Plus,
  Save,
  Trash2,
  GripVertical,
  Building2,
} from 'lucide-react'
import type { KnowledgeBase, FAQ, Location } from '@/types'

export function KnowledgePage() {
  const { currentOrganization } = useAuthStore()
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null)
  const [faqs, setFaqs] = useState<FAQ[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const [formData, setFormData] = useState({
    business_description: '',
    services: [] as string[],
    opening_hours: '',
    contact_info: '',
    policies: '',
    additional_info: '',
  })

  const [newFaq, setNewFaq] = useState({ question: '', answer: '' })
  const [servicesInput, setServicesInput] = useState('')

  useEffect(() => {
    fetchData()
  }, [currentOrganization, selectedLocationId])

  const fetchData = async () => {
    if (!currentOrganization) return

    try {
      // Fetch locations
      const locsResponse = await locationsApi.list(currentOrganization.id)
      setLocations(Array.isArray(locsResponse) ? locsResponse : (locsResponse.results || []))

      // Fetch knowledge base
      const params: Record<string, string> = { organization: currentOrganization.id }
      if (selectedLocationId) {
        params.location = selectedLocationId
      }

      const kbResponse = await knowledgeApi.list(params)
      const kbArray = Array.isArray(kbResponse) ? kbResponse : (kbResponse.results || [])
      if (kbArray.length > 0) {
        const kb = kbArray[0]
        setKnowledgeBase(kb)
        setFormData({
          business_description: kb.business_description || '',
          services: kb.services || [],
          opening_hours: kb.opening_hours || '',
          contact_info: kb.contact_info || '',
          policies: kb.policies || '',
          additional_info: kb.additional_info || '',
        })
        setServicesInput((kb.services || []).join(', '))

        // Fetch FAQs
        const faqResponse = await faqApi.list(kb.id)
        setFaqs(faqResponse.results || [])
      } else {
        setKnowledgeBase(null)
        setFormData({
          business_description: '',
          services: [],
          opening_hours: '',
          contact_info: '',
          policies: '',
          additional_info: '',
        })
        setFaqs([])
      }
    } catch (error) {
      console.error('Error fetching knowledge data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveKnowledgeBase = async () => {
    if (!currentOrganization) return

    setSaving(true)
    try {
      const data = {
        ...formData,
        services: servicesInput.split(',').map((s) => s.trim()).filter(Boolean),
        organization: currentOrganization.id,
        location: selectedLocationId,
      }

      if (knowledgeBase) {
        await knowledgeApi.update(knowledgeBase.id, data)
      } else {
        await knowledgeApi.create(data)
      }

      toast({
        title: 'Saved!',
        description: 'Knowledge base updated successfully.',
      })

      await fetchData()
    } catch (error) {
      console.error('Error saving knowledge base:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to save knowledge base.',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleAddFaq = async () => {
    if (!knowledgeBase || !newFaq.question.trim() || !newFaq.answer.trim()) return

    try {
      await faqApi.create(knowledgeBase.id, {
        question: newFaq.question,
        answer: newFaq.answer,
        order: faqs.length,
      })

      setNewFaq({ question: '', answer: '' })
      await fetchData()

      toast({
        title: 'FAQ added',
        description: 'New FAQ has been added successfully.',
      })
    } catch (error) {
      console.error('Error adding FAQ:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to add FAQ.',
      })
    }
  }

  const handleDeleteFaq = async (faqId: string) => {
    if (!knowledgeBase) return

    try {
      await faqApi.delete(knowledgeBase.id, faqId)
      await fetchData()

      toast({
        title: 'FAQ deleted',
        description: 'FAQ has been removed.',
      })
    } catch (error) {
      console.error('Error deleting FAQ:', error)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to delete FAQ.',
      })
    }
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
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">Knowledge Base</h1>
          <p className="text-muted-foreground">
            Configure what your AI chatbot knows about your business.
          </p>
        </div>
      </div>

      {/* Location Selector */}
      {locations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Building2 className="h-4 w-4" />
              Location-Specific Knowledge
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant={selectedLocationId === null ? 'default' : 'outline'}
                size="sm"
                onClick={() => setSelectedLocationId(null)}
              >
                Organization Default
              </Button>
              {locations.map((loc) => (
                <Button
                  key={loc.id}
                  variant={selectedLocationId === loc.id ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedLocationId(loc.id)}
                >
                  {loc.name}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General Info</TabsTrigger>
          <TabsTrigger value="faqs">FAQs ({faqs.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Business Information</CardTitle>
              <CardDescription>
                This information helps the AI understand your business and answer customer questions accurately.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="business_description">Business Description</Label>
                <textarea
                  id="business_description"
                  className="w-full min-h-[100px] p-3 rounded-md border bg-background"
                  placeholder="Describe your business, what makes it unique, and what customers can expect..."
                  value={formData.business_description}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, business_description: e.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="services">Services Offered (comma-separated)</Label>
                <Input
                  id="services"
                  placeholder="Dine-in, Takeout, Delivery, Catering..."
                  value={servicesInput}
                  onChange={(e) => setServicesInput(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="hours">Operating Hours</Label>
                <textarea
                  id="hours"
                  className="w-full min-h-[80px] p-3 rounded-md border bg-background"
                  placeholder="Mon-Fri: 9am-9pm, Sat-Sun: 10am-10pm..."
                  value={formData.opening_hours}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, opening_hours: e.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="contact">Contact Information</Label>
                <textarea
                  id="contact"
                  className="w-full min-h-[80px] p-3 rounded-md border bg-background"
                  placeholder="Phone, email, address..."
                  value={formData.contact_info}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, contact_info: e.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="policies">Policies</Label>
                <textarea
                  id="policies"
                  className="w-full min-h-[80px] p-3 rounded-md border bg-background"
                  placeholder="Reservation policy, cancellation policy, pet policy..."
                  value={formData.policies}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, policies: e.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="additional">Additional Information</Label>
                <textarea
                  id="additional"
                  className="w-full min-h-[80px] p-3 rounded-md border bg-background"
                  placeholder="Any other information the AI should know..."
                  value={formData.additional_info}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, additional_info: e.target.value }))
                  }
                />
              </div>

              <Button onClick={handleSaveKnowledgeBase} disabled={saving}>
                <Save className="h-4 w-4 mr-2" />
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="faqs" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Add FAQ */}
            <Card>
              <CardHeader>
                <CardTitle>Add New FAQ</CardTitle>
                <CardDescription>
                  Add common questions and answers for your AI to use.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {!knowledgeBase ? (
                  <p className="text-sm text-muted-foreground">
                    Save the general info first to add FAQs.
                  </p>
                ) : (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="faq_question">Question</Label>
                      <Input
                        id="faq_question"
                        placeholder="What are your hours?"
                        value={newFaq.question}
                        onChange={(e) =>
                          setNewFaq((prev) => ({ ...prev, question: e.target.value }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="faq_answer">Answer</Label>
                      <textarea
                        id="faq_answer"
                        className="w-full min-h-[80px] p-3 rounded-md border bg-background"
                        placeholder="We're open Monday-Friday 9am-9pm..."
                        value={newFaq.answer}
                        onChange={(e) =>
                          setNewFaq((prev) => ({ ...prev, answer: e.target.value }))
                        }
                      />
                    </div>
                    <Button onClick={handleAddFaq}>
                      <Plus className="h-4 w-4 mr-2" />
                      Add FAQ
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>

            {/* FAQ List */}
            <Card>
              <CardHeader>
                <CardTitle>Existing FAQs</CardTitle>
                <CardDescription>
                  {faqs.length} FAQ{faqs.length !== 1 ? 's' : ''} configured.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {faqs.length === 0 ? (
                  <div className="text-center py-8">
                    <BookOpen className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">No FAQs yet</p>
                  </div>
                ) : (
                  <ScrollArea className="h-[400px]">
                    <div className="space-y-3">
                      {faqs.map((faq) => (
                        <div
                          key={faq.id}
                          className="p-3 bg-muted rounded-lg group"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1">
                              <p className="font-medium text-sm">{faq.question}</p>
                              <p className="text-sm text-muted-foreground mt-1">
                                {faq.answer}
                              </p>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="opacity-0 group-hover:opacity-100"
                              onClick={() => handleDeleteFaq(faq.id)}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                          {!faq.is_active && (
                            <Badge variant="secondary" className="mt-2">
                              Inactive
                            </Badge>
                          )}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
