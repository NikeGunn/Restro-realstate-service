import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/auth'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const tokens = useAuthStore.getState().tokens
    if (tokens?.access) {
      config.headers.Authorization = `Bearer ${tokens.access}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const tokens = useAuthStore.getState().tokens
      if (tokens?.refresh) {
        try {
          const response = await axios.post(`${API_URL}/auth/refresh/`, {
            refresh: tokens.refresh,
          })

          const newTokens = response.data
          useAuthStore.getState().setTokens(newTokens)

          originalRequest.headers.Authorization = `Bearer ${newTokens.access}`
          return api(originalRequest)
        } catch (refreshError) {
          useAuthStore.getState().logout()
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
      }
    }

    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  login: async (email: string, password: string) => {
    const response = await api.post('/auth/login/', { email, password })
    return response.data
  },

  register: async (data: {
    email: string
    username: string
    first_name: string
    last_name: string
    password: string
    password_confirm: string
  }) => {
    const response = await api.post('/auth/register/', data)
    return response.data
  },

  logout: async (refreshToken: string) => {
    const response = await api.post('/auth/logout/', { refresh: refreshToken })
    return response.data
  },

  getCurrentUser: async () => {
    const response = await api.get('/auth/me/')
    return response.data
  },
}

// Organizations API
export const organizationsApi = {
  list: async () => {
    const response = await api.get('/organizations/')
    // Handle paginated response
    return Array.isArray(response.data) ? response.data : (response.data.results || [])
  },

  get: async (id: string) => {
    const response = await api.get(`/organizations/${id}/`)
    return response.data
  },

  create: async (data: { name: string; business_type: string }) => {
    const response = await api.post('/organizations/', data)
    return response.data
  },

  update: async (id: string, data: Partial<{ name: string; widget_color: string; widget_greeting: string }>) => {
    const response = await api.patch(`/organizations/${id}/`, data)
    return response.data
  },
}

// Conversations API
export const conversationsApi = {
  list: async (params?: {
    organization?: string
    state?: string
    channel?: string
    assigned?: string
    search?: string
  }) => {
    const response = await api.get('/conversations/', { params })
    return Array.isArray(response.data) ? response.data : (response.data.results || [])
  },

  get: async (id: string) => {
    const response = await api.get(`/conversations/${id}/`)
    return response.data
  },

  lock: async (id: string) => {
    const response = await api.post(`/conversations/${id}/lock/`)
    return response.data
  },

  unlock: async (id: string) => {
    const response = await api.post(`/conversations/${id}/unlock/`)
    return response.data
  },

  resolve: async (id: string) => {
    const response = await api.post(`/conversations/${id}/resolve/`)
    return response.data
  },

  sendMessage: async (conversationId: string, content: string) => {
    const response = await api.post(`/conversations/${conversationId}/messages/`, { content })
    return response.data
  },

  markRead: async (conversationId: string) => {
    const response = await api.post(`/conversations/${conversationId}/messages/mark_read/`)
    return response.data
  },
}

// Alerts API
export const alertsApi = {
  list: async (params?: {
    organization?: string
    status?: string
    priority?: string
  }) => {
    const response = await api.get('/handoff/alerts/', { params })
    return Array.isArray(response.data) ? response.data : (response.data.results || [])
  },

  acknowledge: async (id: string) => {
    const response = await api.post(`/handoff/alerts/${id}/acknowledge/`)
    return response.data
  },

  resolve: async (id: string, notes?: string) => {
    const response = await api.post(`/handoff/alerts/${id}/resolve/`, { notes })
    return response.data
  },

  stats: async (params?: { organization?: string }) => {
    const response = await api.get('/handoff/alerts/stats/', { params })
    return response.data
  },
}

// Knowledge Base API
export const knowledgeApi = {
  list: async (params?: { organization?: string; location?: string }) => {
    const response = await api.get('/knowledge/bases/', { params })
    return Array.isArray(response.data) ? response.data : (response.data.results || [])
  },

  get: async (id: string) => {
    const response = await api.get(`/knowledge/bases/${id}/`)
    return response.data
  },

  create: async (data: {
    organization: string
    location?: string
    business_description?: string
    opening_hours?: Record<string, { open: string; close: string }>
    contact_info?: Record<string, string>
    additional_info?: string
  }) => {
    const response = await api.post('/knowledge/bases/', data)
    return response.data
  },

  update: async (id: string, data: Partial<{
    business_description: string
    opening_hours: Record<string, { open: string; close: string }>
    contact_info: Record<string, string>
    additional_info: string
  }>) => {
    const response = await api.patch(`/knowledge/bases/${id}/`, data)
    return response.data
  },

  listFAQs: async (params?: { organization?: string; location?: string }) => {
    const response = await api.get('/knowledge/faqs/', { params })
    return Array.isArray(response.data) ? response.data : (response.data.results || [])
  },

  createFAQ: async (data: {
    organization: string
    location?: string
    question: string
    answer: string
    category?: string
  }) => {
    const response = await api.post('/knowledge/faqs/', data)
    return response.data
  },

  updateFAQ: async (id: string, data: Partial<{
    question: string
    answer: string
    category: string
    is_active: boolean
  }>) => {
    const response = await api.patch(`/knowledge/faqs/${id}/`, data)
    return response.data
  },

  deleteFAQ: async (id: string) => {
    const response = await api.delete(`/knowledge/faqs/${id}/`)
    return response.data
  },
}

// Analytics API
export const analyticsApi = {
  overview: async (params: { organization: string; days?: number }) => {
    const response = await api.get('/analytics/overview/', { params })
    return response.data
  },

  byChannel: async (params: { organization: string; days?: number }) => {
    const response = await api.get('/analytics/by-channel/', { params })
    return response.data
  },

  byLocation: async (params: { organization: string; days?: number }) => {
    const response = await api.get('/analytics/by-location/', { params })
    return response.data
  },

  daily: async (params: { organization: string; days?: number }) => {
    const response = await api.get('/analytics/daily/', { params })
    return response.data
  },
}

// Locations API
export const locationsApi = {
  list: async (organizationId: string) => {
    const response = await api.get(`/organizations/${organizationId}/locations/`)
    return Array.isArray(response.data) ? response.data : (response.data.results || [])
  },

  get: async (organizationId: string, locationId: string) => {
    const response = await api.get(`/organizations/${organizationId}/locations/${locationId}/`)
    return response.data
  },

  create: async (organizationId: string, data: {
    name: string
    address?: string
    phone?: string
    email?: string
  }) => {
    const response = await api.post(`/organizations/${organizationId}/locations/`, data)
    return response.data
  },

  update: async (organizationId: string, locationId: string, data: Partial<{
    name: string
    address: string
    phone: string
    email: string
    is_active: boolean
  }>) => {
    const response = await api.patch(`/organizations/${organizationId}/locations/${locationId}/`, data)
    return response.data
  },

  delete: async (organizationId: string, locationId: string) => {
    const response = await api.delete(`/organizations/${organizationId}/locations/${locationId}/`)
    return response.data
  },
}

// FAQ API (standalone)
export const faqApi = {
  list: async (knowledgeBaseId: string) => {
    const response = await api.get(`/knowledge/faqs/?knowledge_base=${knowledgeBaseId}`)
    return response.data
  },

  create: async (knowledgeBaseId: string, data: {
    question: string
    answer: string
    order?: number
  }) => {
    const response = await api.post(`/knowledge/faqs/`, { ...data, knowledge_base: knowledgeBaseId })
    return response.data
  },

  update: async (knowledgeBaseId: string, faqId: string, data: Partial<{
    question: string
    answer: string
    order: number
    is_active: boolean
  }>) => {
    const response = await api.patch(`/knowledge/faqs/${faqId}/`, data)
    return response.data
  },

  delete: async (knowledgeBaseId: string, faqId: string) => {
    const response = await api.delete(`/knowledge/faqs/${faqId}/`)
    return response.data
  },
}

// ============================================
// Restaurant Vertical API
// ============================================

export const restaurantApi = {
  // Menu Categories
  categories: {
    list: async (params?: { organization?: string; location?: string; active?: boolean }) => {
      const response = await api.get('/restaurant/categories/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/restaurant/categories/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      location?: string
      name: string
      description?: string
      display_order?: number
      is_active?: boolean
    }) => {
      const response = await api.post('/restaurant/categories/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      name: string
      description: string
      display_order: number
      is_active: boolean
    }>) => {
      const response = await api.patch(`/restaurant/categories/${id}/`, data)
      return response.data
    },

    delete: async (id: string) => {
      const response = await api.delete(`/restaurant/categories/${id}/`)
      return response.data
    },

    reorder: async (items: { id: string; order: number }[]) => {
      const response = await api.post('/restaurant/categories/reorder/', { items })
      return response.data
    },
  },

  // Menu Items
  items: {
    list: async (params?: { organization?: string; category?: string; active?: boolean; available?: boolean }) => {
      const response = await api.get('/restaurant/items/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/restaurant/items/${id}/`)
      return response.data
    },

    create: async (data: {
      category: string
      name: string
      description?: string
      price: string
      dietary_info?: string[]
      prep_time_minutes?: number
      image_url?: string
      display_order?: number
      is_available?: boolean
      is_active?: boolean
    }) => {
      const response = await api.post('/restaurant/items/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      name: string
      description: string
      price: string
      dietary_info: string[]
      prep_time_minutes: number
      image_url: string
      display_order: number
      is_available: boolean
      is_active: boolean
    }>) => {
      const response = await api.patch(`/restaurant/items/${id}/`, data)
      return response.data
    },

    delete: async (id: string) => {
      const response = await api.delete(`/restaurant/items/${id}/`)
      return response.data
    },

    toggleAvailability: async (id: string) => {
      const response = await api.post(`/restaurant/items/${id}/toggle_availability/`)
      return response.data
    },

    reorder: async (items: { id: string; order: number }[]) => {
      const response = await api.post('/restaurant/items/reorder/', { items })
      return response.data
    },
  },

  // Opening Hours
  hours: {
    list: async (params?: { location?: string }) => {
      const response = await api.get('/restaurant/hours/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    create: async (data: {
      location: string
      day_of_week: number
      open_time?: string
      close_time?: string
      is_closed?: boolean
    }) => {
      const response = await api.post('/restaurant/hours/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      open_time: string
      close_time: string
      is_closed: boolean
    }>) => {
      const response = await api.patch(`/restaurant/hours/${id}/`, data)
      return response.data
    },

    bulkUpdate: async (data: {
      location: string
      hours: Array<{
        day_of_week: number
        open_time?: string
        close_time?: string
        is_closed?: boolean
      }>
    }) => {
      const response = await api.post('/restaurant/hours/bulk_update/', data)
      return response.data
    },
  },

  // Daily Specials
  specials: {
    list: async (params?: { organization?: string; location?: string; active?: boolean; today?: boolean }) => {
      const response = await api.get('/restaurant/specials/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/restaurant/specials/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      location?: string
      name: string
      description: string
      price: string
      original_price?: string
      start_date: string
      end_date: string
      recurring_days?: number[]
      is_active?: boolean
    }) => {
      const response = await api.post('/restaurant/specials/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      name: string
      description: string
      price: string
      original_price: string
      start_date: string
      end_date: string
      recurring_days: number[]
      is_active: boolean
    }>) => {
      const response = await api.patch(`/restaurant/specials/${id}/`, data)
      return response.data
    },

    delete: async (id: string) => {
      const response = await api.delete(`/restaurant/specials/${id}/`)
      return response.data
    },
  },

  // Bookings
  bookings: {
    list: async (params?: {
      organization?: string
      location?: string
      status?: string
      date?: string
      start_date?: string
      end_date?: string
      source?: string
    }) => {
      const response = await api.get('/restaurant/bookings/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/restaurant/bookings/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      location: string
      booking_date: string
      booking_time: string
      party_size: number
      customer_name: string
      customer_email?: string
      customer_phone: string
      special_requests?: string
      source?: string
    }) => {
      const response = await api.post('/restaurant/bookings/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      booking_date: string
      booking_time: string
      party_size: number
      customer_name: string
      customer_email: string
      customer_phone: string
      special_requests: string
      status: string
      internal_notes: string
    }>) => {
      const response = await api.patch(`/restaurant/bookings/${id}/`, data)
      return response.data
    },

    confirm: async (id: string) => {
      const response = await api.post(`/restaurant/bookings/${id}/confirm/`)
      return response.data
    },

    cancel: async (id: string, reason?: string) => {
      const response = await api.post(`/restaurant/bookings/${id}/cancel/`, { reason })
      return response.data
    },

    complete: async (id: string) => {
      const response = await api.post(`/restaurant/bookings/${id}/complete/`)
      return response.data
    },

    noShow: async (id: string) => {
      const response = await api.post(`/restaurant/bookings/${id}/no_show/`)
      return response.data
    },

    today: async (params?: { location?: string }) => {
      const response = await api.get('/restaurant/bookings/today/', { params })
      return response.data
    },

    upcoming: async (params?: { location?: string }) => {
      const response = await api.get('/restaurant/bookings/upcoming/', { params })
      return response.data
    },

    stats: async (params: { organization: string; days?: number }) => {
      const response = await api.get('/restaurant/bookings/stats/', { params })
      return response.data
    },

    availability: async (params: { location: string; date: string; party_size?: number }) => {
      const response = await api.get('/restaurant/availability/', { params })
      return response.data
    },
  },

  // Booking Settings
  bookingSettings: {
    list: async (params?: { location?: string }) => {
      const response = await api.get('/restaurant/booking-settings/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/restaurant/booking-settings/${id}/`)
      return response.data
    },

    create: async (data: {
      location: string
      max_party_size?: number
      max_bookings_per_slot?: number
      total_capacity?: number
      slot_duration_minutes?: number
      booking_buffer_minutes?: number
      min_advance_hours?: number
      max_advance_days?: number
      auto_confirm?: boolean
      cancellation_hours?: number
    }) => {
      const response = await api.post('/restaurant/booking-settings/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      max_party_size: number
      max_bookings_per_slot: number
      total_capacity: number
      slot_duration_minutes: number
      booking_buffer_minutes: number
      min_advance_hours: number
      max_advance_days: number
      auto_confirm: boolean
      cancellation_hours: number
    }>) => {
      const response = await api.patch(`/restaurant/booking-settings/${id}/`, data)
      return response.data
    },
  },
}

// ============================================
// Real Estate Vertical API
// ============================================

export const realEstateApi = {
  // Property Listings
  properties: {
    list: async (params?: {
      organization?: string
      listing_type?: string
      property_type?: string
      status?: string
      min_price?: number
      max_price?: number
      bedrooms?: number
      city?: string
      is_featured?: boolean
    }) => {
      const response = await api.get('/realestate/properties/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/realestate/properties/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      listing_type: string
      property_type: string
      title: string
      description?: string
      price: string
      bedrooms?: number
      bathrooms?: string
      square_feet?: number
      lot_size?: number
      year_built?: number
      address_line1: string
      address_line2?: string
      city: string
      state: string
      postal_code: string
      country?: string
      latitude?: string
      longitude?: string
      features?: string[]
      images?: string[]
      virtual_tour_url?: string
      status?: string
      is_featured?: boolean
    }) => {
      const response = await api.post('/realestate/properties/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      title: string
      description: string
      price: string
      bedrooms: number
      bathrooms: string
      square_feet: number
      features: string[]
      images: string[]
      status: string
      is_featured: boolean
    }>) => {
      const response = await api.patch(`/realestate/properties/${id}/`, data)
      return response.data
    },

    delete: async (id: string) => {
      const response = await api.delete(`/realestate/properties/${id}/`)
      return response.data
    },

    markSold: async (id: string, data: { sold_price?: string; sold_date?: string }) => {
      const response = await api.post(`/realestate/properties/${id}/mark_sold/`, data)
      return response.data
    },

    toggleFeatured: async (id: string) => {
      const response = await api.post(`/realestate/properties/${id}/toggle_featured/`)
      return response.data
    },

    stats: async (params: { organization: string }) => {
      const response = await api.get('/realestate/properties/stats/', { params })
      return response.data
    },
  },

  // Leads
  leads: {
    list: async (params?: {
      organization?: string
      status?: string
      intent?: string
      priority?: string
      assigned_agent?: string
      source?: string
    }) => {
      const response = await api.get('/realestate/leads/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/realestate/leads/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      name: string
      email?: string
      phone?: string
      intent: string
      budget_min?: number
      budget_max?: number
      preferred_areas?: string[]
      property_type_preference?: string
      bedrooms_min?: number
      bedrooms_max?: number
      timeline?: string
      notes?: string
      source?: string
      priority?: string
    }) => {
      const response = await api.post('/realestate/leads/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      name: string
      email: string
      phone: string
      intent: string
      budget_min: number
      budget_max: number
      preferred_areas: string[]
      property_type_preference: string
      notes: string
      priority: string
      status: string
      next_follow_up: string
    }>) => {
      const response = await api.patch(`/realestate/leads/${id}/`, data)
      return response.data
    },

    markContacted: async (id: string) => {
      const response = await api.post(`/realestate/leads/${id}/mark_contacted/`)
      return response.data
    },

    qualify: async (id: string, data: { qualification_notes?: string; priority?: string }) => {
      const response = await api.post(`/realestate/leads/${id}/qualify/`, data)
      return response.data
    },

    convert: async (id: string, data: { conversion_notes?: string; property?: string }) => {
      const response = await api.post(`/realestate/leads/${id}/convert/`, data)
      return response.data
    },

    assign: async (id: string, agentId: string) => {
      const response = await api.post(`/realestate/leads/${id}/assign/`, { agent_id: agentId })
      return response.data
    },

    recalculateScore: async (id: string) => {
      const response = await api.post(`/realestate/leads/${id}/recalculate_score/`)
      return response.data
    },

    hot: async (params?: { organization?: string }) => {
      const response = await api.get('/realestate/leads/hot/', { params })
      return response.data
    },

    stats: async (params: { organization: string; days?: number }) => {
      const response = await api.get('/realestate/leads/stats/', { params })
      return response.data
    },
  },

  // Appointments
  appointments: {
    list: async (params?: {
      organization?: string
      lead?: string
      property?: string
      status?: string
      date?: string
      start_date?: string
      end_date?: string
    }) => {
      const response = await api.get('/realestate/appointments/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/realestate/appointments/${id}/`)
      return response.data
    },

    create: async (data: {
      lead: string
      property?: string
      appointment_date: string
      appointment_time: string
      duration_minutes?: number
      appointment_type?: string
      notes?: string
    }) => {
      const response = await api.post('/realestate/appointments/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      appointment_date: string
      appointment_time: string
      duration_minutes: number
      appointment_type: string
      notes: string
    }>) => {
      const response = await api.patch(`/realestate/appointments/${id}/`, data)
      return response.data
    },

    confirm: async (id: string) => {
      const response = await api.post(`/realestate/appointments/${id}/confirm/`)
      return response.data
    },

    cancel: async (id: string, reason?: string) => {
      const response = await api.post(`/realestate/appointments/${id}/cancel/`, { cancellation_reason: reason })
      return response.data
    },

    complete: async (id: string, outcomeNotes?: string) => {
      const response = await api.post(`/realestate/appointments/${id}/complete/`, { outcome_notes: outcomeNotes })
      return response.data
    },

    noShow: async (id: string) => {
      const response = await api.post(`/realestate/appointments/${id}/no_show/`)
      return response.data
    },

    today: async (params?: { organization?: string }) => {
      const response = await api.get('/realestate/appointments/today/', { params })
      return response.data
    },

    upcoming: async (params?: { organization?: string }) => {
      const response = await api.get('/realestate/appointments/upcoming/', { params })
      return response.data
    },

    stats: async (params: { organization: string; days?: number }) => {
      const response = await api.get('/realestate/appointments/stats/', { params })
      return response.data
    },
  },
}

// ============================================
// Channels API (WhatsApp & Instagram)
// ============================================

export const channelsApi = {
  // WhatsApp Configuration
  whatsapp: {
    list: async (params?: { organization?: string }) => {
      const response = await api.get('/channels/whatsapp-config/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/channels/whatsapp-config/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      phone_number_id: string
      business_account_id: string
      access_token: string
      verify_token: string
    }) => {
      const response = await api.post('/channels/whatsapp-config/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      phone_number_id: string
      business_account_id: string
      access_token: string
      verify_token: string
      is_active: boolean
    }>) => {
      const response = await api.patch(`/channels/whatsapp-config/${id}/`, data)
      return response.data
    },

    delete: async (id: string) => {
      const response = await api.delete(`/channels/whatsapp-config/${id}/`)
      return response.data
    },

    testConnection: async (id: string) => {
      const response = await api.post(`/channels/whatsapp-config/${id}/test_connection/`)
      return response.data
    },
  },

  // Instagram Configuration
  instagram: {
    list: async (params?: { organization?: string }) => {
      const response = await api.get('/channels/instagram-config/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/channels/instagram-config/${id}/`)
      return response.data
    },

    create: async (data: {
      organization: string
      instagram_business_id: string
      page_id: string
      access_token: string
      verify_token: string
    }) => {
      const response = await api.post('/channels/instagram-config/', data)
      return response.data
    },

    update: async (id: string, data: Partial<{
      instagram_business_id: string
      page_id: string
      access_token: string
      verify_token: string
      is_active: boolean
    }>) => {
      const response = await api.patch(`/channels/instagram-config/${id}/`, data)
      return response.data
    },

    delete: async (id: string) => {
      const response = await api.delete(`/channels/instagram-config/${id}/`)
      return response.data
    },

    testConnection: async (id: string) => {
      const response = await api.post(`/channels/instagram-config/${id}/test_connection/`)
      return response.data
    },
  },

  // Webhook Logs (for debugging)
  webhookLogs: {
    list: async (params?: { organization?: string; source?: string; is_processed?: boolean }) => {
      const response = await api.get('/channels/webhook-logs/', { params })
      return Array.isArray(response.data) ? response.data : (response.data.results || [])
    },

    get: async (id: string) => {
      const response = await api.get(`/channels/webhook-logs/${id}/`)
      return response.data
    },
  },
}
