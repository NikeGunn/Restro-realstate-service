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
    return response.data
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
    return response.data
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
    return response.data
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
    return response.data
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
    return response.data
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
    return response.data
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
