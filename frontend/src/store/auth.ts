import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, AuthTokens, Organization } from '@/types'

interface AuthState {
  user: User | null
  tokens: AuthTokens | null
  currentOrganization: Organization | null
  isAuthenticated: boolean
  setUser: (user: User | null) => void
  setTokens: (tokens: AuthTokens | null) => void
  setCurrentOrganization: (org: Organization | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      tokens: null,
      currentOrganization: null,
      isAuthenticated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setTokens: (tokens) => set({ tokens }),
      setCurrentOrganization: (org) => set({ currentOrganization: org }),
      logout: () => set({
        user: null,
        tokens: null,
        currentOrganization: null,
        isAuthenticated: false
      }),
    }),
    {
      name: 'auth-storage',
    }
  )
)
