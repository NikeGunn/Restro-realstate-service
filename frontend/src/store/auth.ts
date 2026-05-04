import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, AuthTokens, Organization } from '@/types'

interface AuthState {
  user: User | null
  tokens: AuthTokens | null
  currentOrganization: Organization | null
  isAuthenticated: boolean
  isInitialized: boolean
  setUser: (user: User | null) => void
  setTokens: (tokens: AuthTokens | null) => void
  setCurrentOrganization: (org: Organization | null) => void
  setInitialized: (initialized: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      tokens: null,
      currentOrganization: null,
      isAuthenticated: false,
      isInitialized: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setTokens: (tokens) => set({ tokens }),
      setCurrentOrganization: (org) => set({ currentOrganization: org }),
      setInitialized: (initialized) => set({ isInitialized: initialized }),
      logout: () => set({
        user: null,
        tokens: null,
        currentOrganization: null,
        isAuthenticated: false,
        isInitialized: true,
      }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        tokens: state.tokens,
        currentOrganization: state.currentOrganization,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
