import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import {
  MessageSquare,
  Bot,
  Users,
  Zap,
  Building2,
  UtensilsCrossed,
  Home,
  BarChart3,
  Shield,
  Globe,
  Clock,
  HeadphonesIcon,
  ChevronRight,
  Star,
  Check,
  ArrowRight,
  Menu,
  X
} from 'lucide-react'
import { useState } from 'react'

export function LandingPage() {
  const { t } = useTranslation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId)
    if (element) {
      const navHeight = 64 // Height of fixed nav
      const elementPosition = element.getBoundingClientRect().top + window.pageYOffset
      const offsetPosition = elementPosition - navHeight

      window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
      })
      setMobileMenuOpen(false)
    }
  }

  return (
    <div className="min-h-screen bg-white scroll-smooth">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-sm border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl flex items-center justify-center">
                <MessageSquare className="h-6 w-6 text-white" />
              </div>
              <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                Kribaat
              </span>
            </div>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center gap-8">
              <button
                onClick={() => scrollToSection('features')}
                className="text-gray-600 hover:text-blue-600 transition-colors font-medium"
              >
                {t('landing.nav.features')}
              </button>
              <button
                onClick={() => scrollToSection('solutions')}
                className="text-gray-600 hover:text-blue-600 transition-colors font-medium"
              >
                {t('landing.nav.solutions')}
              </button>
              <button
                onClick={() => scrollToSection('pricing')}
                className="text-gray-600 hover:text-blue-600 transition-colors font-medium"
              >
                {t('landing.nav.pricing')}
              </button>
              <button
                onClick={() => scrollToSection('testimonials')}
                className="text-gray-600 hover:text-blue-600 transition-colors font-medium"
              >
                {t('landing.nav.testimonials')}
              </button>
            </div>

            {/* CTA Buttons */}
            <div className="hidden md:flex items-center gap-4">
              <LanguageSwitcher variant="compact" />
              <Link to="/login">
                <Button variant="ghost" className="font-medium">
                  {t('landing.nav.signIn')}
                </Button>
              </Link>
              <Link to="/register">
                <Button className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-medium shadow-lg shadow-blue-500/25">
                  {t('landing.nav.getStarted')}
                </Button>
              </Link>
            </div>

            {/* Mobile menu button */}
            <div className="md:hidden flex items-center gap-2">
              <LanguageSwitcher variant="compact" />
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="p-2 rounded-lg hover:bg-gray-100"
              >
                {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-white border-t border-gray-100 px-4 py-4 space-y-4">
            <button
              onClick={() => scrollToSection('features')}
              className="block w-full text-left text-gray-600 hover:text-blue-600 py-2 font-medium"
            >
              {t('landing.nav.features')}
            </button>
            <button
              onClick={() => scrollToSection('solutions')}
              className="block w-full text-left text-gray-600 hover:text-blue-600 py-2 font-medium"
            >
              {t('landing.nav.solutions')}
            </button>
            <button
              onClick={() => scrollToSection('pricing')}
              className="block w-full text-left text-gray-600 hover:text-blue-600 py-2 font-medium"
            >
              {t('landing.nav.pricing')}
            </button>
            <button
              onClick={() => scrollToSection('testimonials')}
              className="block w-full text-left text-gray-600 hover:text-blue-600 py-2 font-medium"
            >
              {t('landing.nav.testimonials')}
            </button>
            <div className="flex flex-col gap-2 pt-4 border-t border-gray-100">
              <Link to="/login">
                <Button variant="outline" className="w-full">{t('landing.nav.signIn')}</Button>
              </Link>
              <Link to="/register">
                <Button className="w-full bg-gradient-to-r from-blue-600 to-indigo-600">
                  {t('landing.nav.getStarted')}
                </Button>
              </Link>
            </div>
          </div>
        )}
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 overflow-hidden relative">
        {/* Background decoration */}
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-400/20 rounded-full blur-3xl" />
          <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-indigo-400/20 rounded-full blur-3xl" />
        </div>

        <div className="max-w-7xl mx-auto relative">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="text-center lg:text-left">
              {/* Badge */}
              <div className="inline-flex items-center gap-2 bg-blue-100 text-blue-700 px-4 py-2 rounded-full text-sm font-medium mb-6">
                <Zap className="h-4 w-4" />
                {t('landing.hero.badge')}
              </div>

              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 leading-tight mb-6">
                {t('landing.hero.title')}{' '}
                <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                  {t('landing.hero.titleHighlight')}
                </span>
              </h1>

              <p className="text-xl text-gray-600 mb-8 max-w-xl mx-auto lg:mx-0">
                {t('landing.hero.subtitle')}
              </p>

              <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                <Link to="/register">
                  <Button size="lg" className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white px-8 py-6 text-lg font-semibold shadow-xl shadow-blue-500/30 hover:shadow-2xl hover:shadow-blue-500/40 transition-all hover:scale-105 w-full sm:w-auto">
                    {t('landing.hero.cta')}
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                </Link>
                <a href="#pricing">
                  <Button size="lg" variant="outline" className="px-8 py-6 text-lg font-semibold border-2 hover:bg-blue-50 hover:border-blue-600 hover:text-blue-600 transition-all w-full sm:w-auto">
                    {t('landing.hero.watchDemo')}
                  </Button>
                </a>
              </div>

              {/* Trust badges */}
              <div className="mt-10 flex flex-col sm:flex-row items-center gap-6 justify-center lg:justify-start">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Check className="h-5 w-5 text-green-500" />
                  {t('landing.hero.trustBadge1')}
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Check className="h-5 w-5 text-green-500" />
                  {t('landing.hero.trustBadge2')}
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Check className="h-5 w-5 text-green-500" />
                  {t('landing.hero.trustBadge3')}
                </div>
              </div>
            </div>

            {/* Hero Image/Demo */}
            <div className="relative">
              <div className="bg-white rounded-2xl shadow-2xl p-6 border border-gray-100">
                {/* Chat Demo */}
                <div className="space-y-4">
                  <div className="flex items-center gap-3 pb-4 border-b border-gray-100">
                    <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-full flex items-center justify-center">
                      <Bot className="h-5 w-5 text-white" />
                    </div>
                    <div>
                      <p className="font-semibold text-gray-900">Kribaat AI</p>
                      <p className="text-xs text-green-500 flex items-center gap-1">
                        <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        {t('landing.hero.chatOnline')}
                      </p>
                    </div>
                  </div>

                  {/* Chat messages */}
                  <div className="space-y-3">
                    <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl rounded-tr-sm p-4 max-w-[80%] ml-auto">
                      <p className="text-white">{t('landing.hero.chatMsg1')}</p>
                    </div>
                    <div className="bg-gray-100 rounded-2xl rounded-tl-sm p-4 max-w-[80%]">
                      <p className="text-gray-800">{t('landing.hero.chatMsg2')}</p>
                    </div>
                    <div className="bg-gray-100 rounded-2xl rounded-tl-sm p-4 max-w-[80%]">
                      <p className="text-gray-800">{t('landing.hero.chatMsg3')}</p>
                    </div>
                  </div>

                  {/* Typing indicator */}
                  <div className="flex items-center gap-2 text-gray-400 text-sm">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    {t('landing.hero.aiTyping')}
                  </div>
                </div>
              </div>

              {/* Floating stats cards */}
              <div className="absolute -bottom-6 -left-6 bg-white rounded-xl shadow-lg p-4 border border-gray-100 hidden sm:block">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                    <BarChart3 className="h-5 w-5 text-green-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-gray-900">95%</p>
                    <p className="text-sm text-gray-500">{t('landing.hero.statAutomated')}</p>
                  </div>
                </div>
              </div>

              <div className="absolute -top-4 -right-4 bg-white rounded-xl shadow-lg p-4 border border-gray-100 hidden sm:block">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                    <Clock className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-gray-900">24/7</p>
                    <p className="text-sm text-gray-500">{t('landing.hero.statSupport')}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Logos Section */}
      <section className="py-12 bg-white border-y border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-gray-500 mb-8">{t('landing.logos.title')}</p>
          <div className="flex flex-wrap justify-center items-center gap-8 md:gap-16 opacity-60">
            <div className="flex items-center gap-2 text-gray-400">
              <UtensilsCrossed className="h-8 w-8" />
              <span className="text-lg font-semibold">Restaurants</span>
            </div>
            <div className="flex items-center gap-2 text-gray-400">
              <Building2 className="h-8 w-8" />
              <span className="text-lg font-semibold">Real Estate</span>
            </div>
            <div className="flex items-center gap-2 text-gray-400">
              <Home className="h-8 w-8" />
              <span className="text-lg font-semibold">Property Mgmt</span>
            </div>
            <div className="flex items-center gap-2 text-gray-400">
              <Globe className="h-8 w-8" />
              <span className="text-lg font-semibold">Multi-Channel</span>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-16 md:py-24 px-4 sm:px-6 lg:px-8 bg-white scroll-mt-16">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 bg-indigo-100 text-indigo-700 px-4 py-2 rounded-full text-sm font-medium mb-4">
              <Zap className="h-4 w-4" />
              {t('landing.features.badge')}
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
              {t('landing.features.title')}
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              {t('landing.features.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
            {/* Feature 1 */}
            <Card className="border-0 shadow-lg hover:shadow-2xl transition-all hover:-translate-y-1 bg-gradient-to-br from-blue-50 to-white">
              <CardContent className="p-6 md:p-8">
                <div className="w-14 h-14 bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-blue-500/30">
                  <Bot className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{t('landing.features.ai.title')}</h3>
                <p className="text-gray-600">{t('landing.features.ai.description')}</p>
              </CardContent>
            </Card>

            {/* Feature 2 */}
            <Card className="border-0 shadow-lg hover:shadow-2xl transition-all hover:-translate-y-1 bg-gradient-to-br from-indigo-50 to-white">
              <CardContent className="p-6 md:p-8">
                <div className="w-14 h-14 bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-indigo-500/30">
                  <MessageSquare className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{t('landing.features.omnichannel.title')}</h3>
                <p className="text-gray-600">{t('landing.features.omnichannel.description')}</p>
              </CardContent>
            </Card>

            {/* Feature 3 */}
            <Card className="border-0 shadow-lg hover:shadow-2xl transition-all hover:-translate-y-1 bg-gradient-to-br from-purple-50 to-white">
              <CardContent className="p-6 md:p-8">
                <div className="w-14 h-14 bg-gradient-to-br from-purple-500 to-purple-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-purple-500/30">
                  <Users className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{t('landing.features.handoff.title')}</h3>
                <p className="text-gray-600">{t('landing.features.handoff.description')}</p>
              </CardContent>
            </Card>

            {/* Feature 4 */}
            <Card className="border-0 shadow-lg hover:shadow-2xl transition-all hover:-translate-y-1 bg-gradient-to-br from-green-50 to-white">
              <CardContent className="p-6 md:p-8">
                <div className="w-14 h-14 bg-gradient-to-br from-green-500 to-green-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-green-500/30">
                  <BarChart3 className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{t('landing.features.analytics.title')}</h3>
                <p className="text-gray-600">{t('landing.features.analytics.description')}</p>
              </CardContent>
            </Card>

            {/* Feature 5 */}
            <Card className="border-0 shadow-lg hover:shadow-2xl transition-all hover:-translate-y-1 bg-gradient-to-br from-orange-50 to-white">
              <CardContent className="p-6 md:p-8">
                <div className="w-14 h-14 bg-gradient-to-br from-orange-500 to-orange-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-orange-500/30">
                  <Globe className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{t('landing.features.multilingual.title')}</h3>
                <p className="text-gray-600">{t('landing.features.multilingual.description')}</p>
              </CardContent>
            </Card>

            {/* Feature 6 */}
            <Card className="border-0 shadow-lg hover:shadow-2xl transition-all hover:-translate-y-1 bg-gradient-to-br from-pink-50 to-white">
              <CardContent className="p-6 md:p-8">
                <div className="w-14 h-14 bg-gradient-to-br from-pink-500 to-pink-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-pink-500/30">
                  <Shield className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{t('landing.features.security.title')}</h3>
                <p className="text-gray-600">{t('landing.features.security.description')}</p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Solutions Section */}
      <section id="solutions" className="py-16 md:py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-slate-50 to-blue-50 scroll-mt-16">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 bg-blue-100 text-blue-700 px-4 py-2 rounded-full text-sm font-medium mb-4">
              <Building2 className="h-4 w-4" />
              {t('landing.solutions.badge')}
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
              {t('landing.solutions.title')}
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              {t('landing.solutions.subtitle')}
            </p>
          </div>

          <div className="grid lg:grid-cols-2 gap-8">
            {/* Restaurant Solution */}
            <Card className="border-0 shadow-xl hover:shadow-2xl transition-all hover:-translate-y-2 bg-white overflow-hidden group">
              <CardContent className="p-0">
                <div className="bg-gradient-to-br from-orange-500 to-red-500 p-8 text-white">
                  <UtensilsCrossed className="h-12 w-12 mb-4 group-hover:scale-110 transition-transform" />
                  <h3 className="text-2xl font-bold mb-2">{t('landing.solutions.restaurant.title')}</h3>
                  <p className="opacity-90">{t('landing.solutions.restaurant.subtitle')}</p>
                </div>
                <div className="p-8">
                  <ul className="space-y-4">
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.restaurant.feature1')}</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.restaurant.feature2')}</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.restaurant.feature3')}</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.restaurant.feature4')}</span>
                    </li>
                  </ul>
                  <Link to="/register" className="mt-6 inline-flex items-center text-orange-600 font-semibold hover:text-orange-700 group-hover:gap-3 gap-2 transition-all">
                    {t('landing.solutions.learnMore')}
                    <ChevronRight className="h-4 w-4" />
                  </Link>
                </div>
              </CardContent>
            </Card>

            {/* Real Estate Solution */}
            <Card className="border-0 shadow-xl hover:shadow-2xl transition-all hover:-translate-y-2 bg-white overflow-hidden group">
              <CardContent className="p-0">
                <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-8 text-white">
                  <Building2 className="h-12 w-12 mb-4 group-hover:scale-110 transition-transform" />
                  <h3 className="text-2xl font-bold mb-2">{t('landing.solutions.realEstate.title')}</h3>
                  <p className="opacity-90">{t('landing.solutions.realEstate.subtitle')}</p>
                </div>
                <div className="p-8">
                  <ul className="space-y-4">
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.realEstate.feature1')}</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.realEstate.feature2')}</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.realEstate.feature3')}</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{t('landing.solutions.realEstate.feature4')}</span>
                    </li>
                  </ul>
                  <Link to="/register" className="mt-6 inline-flex items-center text-blue-600 font-semibold hover:text-blue-700 group-hover:gap-3 gap-2 transition-all">
                    {t('landing.solutions.learnMore')}
                    <ChevronRight className="h-4 w-4" />
                  </Link>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 bg-gradient-to-r from-blue-600 to-indigo-600">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 text-center text-white">
            <div>
              <p className="text-4xl sm:text-5xl font-bold mb-2">95%</p>
              <p className="text-blue-100">{t('landing.stats.automation')}</p>
            </div>
            <div>
              <p className="text-4xl sm:text-5xl font-bold mb-2">24/7</p>
              <p className="text-blue-100">{t('landing.stats.availability')}</p>
            </div>
            <div>
              <p className="text-4xl sm:text-5xl font-bold mb-2">3x</p>
              <p className="text-blue-100">{t('landing.stats.efficiency')}</p>
            </div>
            <div>
              <p className="text-4xl sm:text-5xl font-bold mb-2">50%</p>
              <p className="text-blue-100">{t('landing.stats.savings')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-16 md:py-24 px-4 sm:px-6 lg:px-8 bg-white scroll-mt-16">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12 md:mb-16">
            <div className="inline-flex items-center gap-2 bg-green-100 text-green-700 px-4 py-2 rounded-full text-sm font-medium mb-4">
              <Zap className="h-4 w-4" />
              {t('landing.pricing.badge')}
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
              {t('landing.pricing.title')}
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              {t('landing.pricing.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8 max-w-5xl mx-auto">
            {/* Basic Plan */}
            <Card className="border-2 border-gray-200 hover:border-blue-400 hover:shadow-xl transition-all hover:-translate-y-1">
              <CardContent className="p-6 md:p-8">
                <h3 className="text-xl font-bold text-gray-900 mb-2">{t('landing.pricing.starter.name')}</h3>
                <p className="text-gray-600 mb-6">{t('landing.pricing.starter.description')}</p>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-gray-900">$49</span>
                  <span className="text-gray-600">{t('landing.pricing.perMonth')}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.starter.feature1')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.starter.feature2')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.starter.feature3')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.starter.feature4')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.starter.feature5')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.starter.feature6')}
                  </li>
                </ul>
                <Link to="/register">
                  <Button variant="outline" className="w-full font-semibold">
                    {t('landing.pricing.getStarted')}
                  </Button>
                </Link>
              </CardContent>
            </Card>

            {/* Power Plan - Popular */}
            <Card className="border-2 border-blue-500 shadow-2xl hover:shadow-3xl transition-all hover:-translate-y-2 relative">
              <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                <span className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold px-4 py-1 rounded-full shadow-lg">
                  {t('landing.pricing.popular')}
                </span>
              </div>
              <CardContent className="p-6 md:p-8">
                <h3 className="text-xl font-bold text-gray-900 mb-2">{t('landing.pricing.pro.name')}</h3>
                <p className="text-gray-600 mb-6">{t('landing.pricing.pro.description')}</p>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-gray-900">$99</span>
                  <span className="text-gray-600">{t('landing.pricing.perMonth')}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.pro.feature1')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.pro.feature2')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.pro.feature3')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.pro.feature4')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.pro.feature5')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.pro.feature6')}
                  </li>
                </ul>
                <Link to="/register">
                  <Button className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold">
                    {t('landing.pricing.getStarted')}
                  </Button>
                </Link>
              </CardContent>
            </Card>

            {/* Enterprise Plan */}
            <Card className="border-2 border-gray-200 hover:border-blue-400 hover:shadow-xl transition-all hover:-translate-y-1">
              <CardContent className="p-6 md:p-8">
                <h3 className="text-xl font-bold text-gray-900 mb-2">{t('landing.pricing.enterprise.name')}</h3>
                <p className="text-gray-600 mb-6">{t('landing.pricing.enterprise.description')}</p>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-gray-900">{t('landing.pricing.custom')}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.enterprise.feature1')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.enterprise.feature2')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.enterprise.feature3')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.enterprise.feature4')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.enterprise.feature5')}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="h-5 w-5 text-green-500" />
                    {t('landing.pricing.enterprise.feature6')}
                  </li>
                </ul>
                <Link to="/register">
                  <Button variant="outline" className="w-full font-semibold">
                    {t('landing.pricing.contactSales')}
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Testimonials Section */}
      <section id="testimonials" className="py-16 md:py-24 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-slate-50 to-blue-50 scroll-mt-16">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12 md:mb-16">
            <div className="inline-flex items-center gap-2 bg-purple-100 text-purple-700 px-4 py-2 rounded-full text-sm font-medium mb-4">
              <Star className="h-4 w-4" />
              {t('landing.testimonials.badge')}
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
              {t('landing.testimonials.title')}
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              {t('landing.testimonials.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
            {/* Testimonial 1 */}
            <Card className="border-0 shadow-lg hover:shadow-xl transition-all hover:-translate-y-1 bg-white">
              <CardContent className="p-6 md:p-8">
                <div className="flex gap-1 mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="h-5 w-5 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 mb-6 italic">"{t('landing.testimonials.review1.text')}"</p>
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-orange-400 to-red-500 rounded-full flex items-center justify-center text-white font-bold">
                    JC
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">{t('landing.testimonials.review1.name')}</p>
                    <p className="text-sm text-gray-600">{t('landing.testimonials.review1.role')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Testimonial 2 */}
            <Card className="border-0 shadow-lg hover:shadow-xl transition-all hover:-translate-y-1 bg-white">
              <CardContent className="p-6 md:p-8">
                <div className="flex gap-1 mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="h-5 w-5 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 mb-6 italic">"{t('landing.testimonials.review2.text')}"</p>
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-400 to-indigo-500 rounded-full flex items-center justify-center text-white font-bold">
                    SL
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">{t('landing.testimonials.review2.name')}</p>
                    <p className="text-sm text-gray-600">{t('landing.testimonials.review2.role')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Testimonial 3 */}
            <Card className="border-0 shadow-lg hover:shadow-xl transition-all hover:-translate-y-1 bg-white">
              <CardContent className="p-6 md:p-8">
                <div className="flex gap-1 mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="h-5 w-5 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 mb-6 italic">"{t('landing.testimonials.review3.text')}"</p>
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center text-white font-bold">
                    MW
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900">{t('landing.testimonials.review3.name')}</p>
                    <p className="text-sm text-gray-600">{t('landing.testimonials.review3.role')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 relative overflow-hidden">
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 -right-40 w-80 h-80 bg-white/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-white/10 rounded-full blur-3xl" />
        </div>
        <div className="max-w-4xl mx-auto text-center relative">
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-6">
            {t('landing.cta.title')}
          </h2>
          <p className="text-xl text-blue-100 mb-10 max-w-2xl mx-auto">
            {t('landing.cta.subtitle')}
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/register">
              <Button size="lg" className="bg-white text-blue-600 hover:bg-blue-50 px-8 py-6 text-lg font-semibold shadow-xl w-full sm:w-auto">
                {t('landing.cta.button')}
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </Link>
            <Link to="/login">
              <Button size="lg" className="bg-white/20 backdrop-blur-sm border-2 border-white text-white hover:bg-white hover:text-blue-600 px-8 py-6 text-lg font-semibold w-full sm:w-auto transition-all">
                {t('landing.cta.loginButton')}
              </Button>
            </Link>
          </div>
          <p className="mt-6 text-blue-100 text-sm">
            {t('landing.cta.noCreditCard')}
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-12 mb-12">
            {/* Brand */}
            <div className="lg:col-span-1">
              <div className="flex items-center gap-2 mb-6">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-500 rounded-xl flex items-center justify-center">
                  <MessageSquare className="h-6 w-6 text-white" />
                </div>
                <span className="text-xl font-bold">Kribaat</span>
              </div>
              <p className="text-gray-400 mb-6">
                {t('landing.footer.description')}
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="font-semibold mb-4">{t('landing.footer.product')}</h4>
              <ul className="space-y-3 text-gray-400">
                <li>
                  <button
                    onClick={() => scrollToSection('features')}
                    className="hover:text-white transition-colors text-left"
                  >
                    {t('landing.footer.features')}
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => scrollToSection('pricing')}
                    className="hover:text-white transition-colors text-left"
                  >
                    {t('landing.footer.pricing')}
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => scrollToSection('solutions')}
                    className="hover:text-white transition-colors text-left"
                  >
                    {t('landing.footer.solutions')}
                  </button>
                </li>
              </ul>
            </div>

            {/* Company */}
            <div>
              <h4 className="font-semibold mb-4">{t('landing.footer.company')}</h4>
              <ul className="space-y-3 text-gray-400">
                <li>
                  <span className="hover:text-white transition-colors cursor-not-allowed flex items-center gap-2">
                    {t('landing.footer.about')}
                    <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">Coming Soon</span>
                  </span>
                </li>
                <li>
                  <span className="hover:text-white transition-colors cursor-not-allowed flex items-center gap-2">
                    {t('landing.footer.contact')}
                    <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">Coming Soon</span>
                  </span>
                </li>
                <li>
                  <span className="hover:text-white transition-colors cursor-not-allowed flex items-center gap-2">
                    {t('landing.footer.careers')}
                    <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">Coming Soon</span>
                  </span>
                </li>
              </ul>
            </div>

            {/* Legal */}
            <div>
              <h4 className="font-semibold mb-4">{t('landing.footer.legal')}</h4>
              <ul className="space-y-3 text-gray-400">
                <li>
                  <span className="hover:text-white transition-colors cursor-not-allowed flex items-center gap-2">
                    {t('landing.footer.privacy')}
                    <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">Coming Soon</span>
                  </span>
                </li>
                <li>
                  <span className="hover:text-white transition-colors cursor-not-allowed flex items-center gap-2">
                    {t('landing.footer.terms')}
                    <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">Coming Soon</span>
                  </span>
                </li>
              </ul>
            </div>
          </div>

          <div className="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-gray-400 text-sm">
              © {new Date().getFullYear()} Kribaat. {t('landing.footer.rights')}
            </p>
            <div className="flex items-center gap-6">
              <span className="text-gray-500 text-xs">v2.0.0 • Powered by Kubernetes</span>
              <div className="flex items-center gap-2">
                <HeadphonesIcon className="h-5 w-5 text-gray-400" />
                <span className="text-gray-400 text-sm">{t('landing.footer.support')}</span>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
