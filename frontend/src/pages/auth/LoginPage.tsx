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
import { LanguageSwitcher } from '@/components/LanguageSwitcher'

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
    <Card className="shadow-lg">
      <CardHeader className="text-center">
        <div className="flex justify-end mb-2">
          <LanguageSwitcher variant="compact" />
        </div>
        <div className="flex justify-center mb-4">
          <div className="p-3 bg-primary/10 rounded-full">
            <MessageSquare className="h-8 w-8 text-primary" />
          </div>
        </div>
        <CardTitle className="text-2xl">{t('auth.welcomeBack')}</CardTitle>
        <CardDescription>{t('auth.signInDescription')}</CardDescription>
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
