import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/auth'
import { authApi, organizationsApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/hooks/use-toast'
import { MessageSquare } from 'lucide-react'

export function LoginPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser, setTokens, setCurrentOrganization } = useAuthStore()
  const navigate = useNavigate()
  const { toast } = useToast()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      // Login
      const tokens = await authApi.login(email, password)
      setTokens(tokens)

      // Get user info
      const user = await authApi.getCurrentUser()
      setUser(user)

      // Get organizations
      try {
        const organizations = await organizationsApi.list()
        if (organizations.length > 0) {
          setCurrentOrganization(organizations[0])
          toast({
            title: t('auth.loginSuccess'),
            description: t('auth.loginSuccessDescription'),
          })
          navigate('/dashboard')
        } else {
          // No organizations - redirect to setup
          toast({
            title: t('auth.loginSuccess'),
            description: t('auth.loginSuccessDescription'),
          })
          navigate('/setup-organization')
        }
      } catch (orgError) {
        // If org fetch fails, redirect to setup
        console.error('Error fetching organizations:', orgError)
        navigate('/setup-organization')
      }
    } catch (error: unknown) {
      console.error('Login error:', error)
      toast({
        variant: 'destructive',
        title: t('auth.loginError'),
        description: t('auth.loginErrorDescription'),
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="shadow-xl border-0 bg-white/95 backdrop-blur-sm">
      <CardHeader className="text-center space-y-4 pb-6">
        <div className="flex justify-center">
          <div className="p-4 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl shadow-lg shadow-blue-500/30">
            <MessageSquare className="h-10 w-10 text-white" />
          </div>
        </div>
        <div className="space-y-2">
          <CardTitle className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
            {t('auth.welcomeBack')}
          </CardTitle>
          <CardDescription className="text-base">{t('auth.signInDescription')}</CardDescription>
        </div>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t('auth.email')}</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{t('auth.password')}</Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t('auth.signingIn') : t('auth.signIn')}
          </Button>
          <p className="text-sm text-muted-foreground text-center">
            {t('auth.noAccount')}{' '}
            <Link to="/register" className="text-primary hover:underline">
              {t('auth.register')}
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  )
}
