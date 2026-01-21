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

export function RegisterPage() {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    first_name: '',
    last_name: '',
    password: '',
    password_confirm: '',
  })
  const [loading, setLoading] = useState(false)
  const { setUser, setTokens, setCurrentOrganization } = useAuthStore()
  const navigate = useNavigate()
  const { toast } = useToast()

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (formData.password !== formData.password_confirm) {
      toast({
        variant: 'destructive',
        title: t('common.error'),
        description: t('auth.passwordMismatch'),
      })
      return
    }

    setLoading(true)

    try {
      const response = await authApi.register(formData)
      setUser(response.user)
      setTokens(response.tokens)

      // After successful registration, always redirect to organization setup
      // User needs to choose business type (restaurant or real estate)
      toast({
        title: t('auth.registerSuccess'),
        description: t('auth.registerSuccessDescription'),
      })
      navigate('/setup-organization')
    } catch (error: unknown) {
      console.error('Registration error:', error)
      toast({
        variant: 'destructive',
        title: t('auth.registerError'),
        description: t('auth.registerErrorDescription'),
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
            {t('auth.createAccount')}
          </CardTitle>
          <CardDescription className="text-base">{t('auth.createAccountDescription')}</CardDescription>
        </div>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="first_name">{t('auth.firstName')}</Label>
              <Input
                id="first_name"
                name="first_name"
                placeholder="John"
                value={formData.first_name}
                onChange={handleChange}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">{t('auth.lastName')}</Label>
              <Input
                id="last_name"
                name="last_name"
                placeholder="Doe"
                value={formData.last_name}
                onChange={handleChange}
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">{t('auth.email')}</Label>
            <Input
              id="email"
              name="email"
              type="email"
              placeholder="you@example.com"
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="username">{t('auth.username')}</Label>
            <Input
              id="username"
              name="username"
              placeholder="johndoe"
              value={formData.username}
              onChange={handleChange}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{t('auth.password')}</Label>
            <Input
              id="password"
              name="password"
              type="password"
              placeholder="••••••••"
              value={formData.password}
              onChange={handleChange}
              required
              minLength={8}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password_confirm">{t('auth.confirmPassword')}</Label>
            <Input
              id="password_confirm"
              name="password_confirm"
              type="password"
              placeholder="••••••••"
              value={formData.password_confirm}
              onChange={handleChange}
              required
            />
          </div>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t('auth.creatingAccount') : t('auth.createAccount')}
          </Button>
          <p className="text-sm text-muted-foreground text-center">
            {t('auth.haveAccount')}{' '}
            <Link to="/login" className="text-primary hover:underline">
              {t('auth.signIn')}
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  )
}
