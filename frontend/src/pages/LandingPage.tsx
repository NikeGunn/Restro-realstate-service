import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import CardFanCarousel, { type CardItem } from '@/components/ui/card-fan-carousel'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import {
  MessageSquare, Bot, Users, Zap, Building2, UtensilsCrossed, Home,
  BarChart3, Shield, Globe, Clock, HeadphonesIcon, ChevronRight,
  Star, Check, ArrowRight, Menu, X, Sparkles,
  LayoutDashboard, Gift, Image as ImageIcon, Wallet, Boxes,
} from 'lucide-react'

/* ------------------------------------------------------------------ *
 * Kribaat landing page — a premium, dark "AI platform" experience.
 *
 * Design intent (psychology-led):
 *  - Dark aurora canvas + glass surfaces read as modern/AI/premium, which
 *    primes trust and perceived value before a word is read.
 *  - Two opposing horizontal marquees (features L→R, channels R→L) create
 *    motion energy and an "always-on, always-moving" feel for an AI product,
 *    while pausing on hover/focus so nothing feels out of the user's control.
 *  - Generous, consistent horizontal gutters (px-6 / lg:px-8, max-w-7xl) give
 *    the page room to breathe and feel expensive.
 *  - All copy comes from existing i18n keys → en / zh-CN / zh-TW unchanged.
 *  - Accessibility per Vercel Web Interface Guidelines: focus-visible rings,
 *    aria-labels on icon buttons, aria-hidden on decorative icons,
 *    prefers-reduced-motion honored in CSS, touch-action on controls.
 * ------------------------------------------------------------------ */

const SHELL = 'mx-auto w-full max-w-7xl px-6 lg:px-8'

export function LandingPage() {
  const { t } = useTranslation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const scrollToSection = (sectionId: string) => {
    const el = document.getElementById(sectionId)
    if (!el) return
    const top = el.getBoundingClientRect().top + window.pageYOffset - 72
    window.scrollTo({ top, behavior: 'smooth' })
    setMobileMenuOpen(false)
  }

  const navItems = ['features', 'solutions', 'showcase', 'pricing', 'testimonials'] as const

  return (
    // `dark` scopes shadcn tokens (LanguageSwitcher dropdown, Buttons, focus
    // rings) to their dark-theme values so they stay legible on the slate canvas.
    <div className="dark min-h-screen scroll-smooth bg-slate-950 text-slate-100 antialiased [touch-action:manipulation] selection:bg-indigo-500/30">
      {/* ====================== NAV ====================== */}
      <nav className="fixed inset-x-0 top-0 z-50 border-b border-white/5 bg-slate-950/70 backdrop-blur-xl">
        <div className={`${SHELL} flex h-[72px] items-center justify-between`}>
          <a href="#top" className="group flex items-center gap-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            aria-label="Kribaat home">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/30 transition-transform group-hover:scale-105">
              <MessageSquare className="h-5 w-5 text-white" aria-hidden="true" />
            </span>
            <span className="bg-gradient-to-r from-white to-slate-300 bg-clip-text text-xl font-bold tracking-tight text-transparent">
              Kribaat
            </span>
          </a>

          <div className="hidden items-center gap-1 md:flex">
            {navItems.map(item => (
              <button
                key={item}
                onClick={() => scrollToSection(item)}
                className="rounded-lg px-3.5 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                {t(`landing.nav.${item}`)}
              </button>
            ))}
          </div>

          <div className="hidden items-center gap-3 md:flex">
            <LanguageSwitcher variant="compact" />
            <Link to="/login">
              <Button variant="ghost" className="font-medium text-slate-200 hover:bg-white/5 hover:text-white">
                {t('landing.nav.signIn')}
              </Button>
            </Link>
            <Link to="/register">
              <Button className="bg-gradient-to-r from-indigo-500 to-violet-600 font-semibold text-white shadow-lg shadow-indigo-500/30 transition-transform hover:scale-[1.03] hover:from-indigo-400 hover:to-violet-500">
                {t('landing.nav.getStarted')}
              </Button>
            </Link>
          </div>

          <div className="flex items-center gap-2 md:hidden">
            <LanguageSwitcher variant="compact" />
            <button
              onClick={() => setMobileMenuOpen(v => !v)}
              className="rounded-lg p-2 text-slate-200 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? <X className="h-6 w-6" aria-hidden="true" /> : <Menu className="h-6 w-6" aria-hidden="true" />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="border-t border-white/5 bg-slate-950/95 px-6 py-4 md:hidden">
            <div className="flex flex-col gap-1">
              {navItems.map(item => (
                <button
                  key={item}
                  onClick={() => scrollToSection(item)}
                  className="rounded-lg px-3 py-2.5 text-left font-medium text-slate-300 hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  {t(`landing.nav.${item}`)}
                </button>
              ))}
            </div>
            <div className="mt-4 flex flex-col gap-2 border-t border-white/5 pt-4">
              <Link to="/login">
                <Button variant="outline" className="w-full border-white/15 bg-transparent text-white hover:bg-white/5">
                  {t('landing.nav.signIn')}
                </Button>
              </Link>
              <Link to="/register">
                <Button className="w-full bg-gradient-to-r from-indigo-500 to-violet-600 font-semibold">
                  {t('landing.nav.getStarted')}
                </Button>
              </Link>
            </div>
          </div>
        )}
      </nav>

      {/* ====================== HERO ====================== */}
      <section id="top" className="relative overflow-hidden pb-24 pt-36">
        {/* aurora + grid backdrop (decorative) */}
        <div className="pointer-events-none absolute inset-0" aria-hidden="true">
          <div className="absolute inset-0 bg-grid-glow opacity-60" />
          <div className="absolute -left-32 -top-32 h-[28rem] w-[28rem] animate-aurora-drift rounded-full bg-indigo-600/25 blur-[120px]" />
          <div className="absolute -right-32 top-10 h-[26rem] w-[26rem] animate-aurora-drift rounded-full bg-violet-600/20 blur-[120px] [animation-delay:-6s]" />
          <div className="absolute bottom-0 left-1/2 h-[22rem] w-[40rem] -translate-x-1/2 rounded-full bg-fuchsia-600/10 blur-[120px]" />
        </div>

        <div className={`${SHELL} relative`}>
          <div className="grid items-center gap-14 lg:grid-cols-2">
            {/* Left: copy */}
            <div className="text-center lg:text-left">
              <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm font-medium text-indigo-200 backdrop-blur">
                <Sparkles className="h-4 w-4 text-indigo-300" aria-hidden="true" />
                {t('landing.hero.badge')}
              </div>

              <h1 className="text-balance text-4xl font-bold leading-[1.05] tracking-tight text-white sm:text-5xl lg:text-6xl">
                {t('landing.hero.title')}{' '}
                <span className="bg-gradient-to-r from-indigo-300 via-violet-300 to-fuchsia-300 bg-clip-text text-transparent">
                  {t('landing.hero.titleHighlight')}
                </span>
              </h1>

              <p className="mx-auto mt-6 max-w-xl text-pretty text-lg text-slate-300 lg:mx-0">
                {t('landing.hero.subtitle')}
              </p>

              <div className="mt-9 flex flex-col justify-center gap-4 sm:flex-row lg:justify-start">
                <Link to="/register" className="w-full sm:w-auto">
                  <Button size="lg" className="group w-full bg-gradient-to-r from-indigo-500 to-violet-600 px-8 py-6 text-lg font-semibold text-white shadow-xl shadow-indigo-500/30 transition-all hover:scale-[1.03] hover:shadow-2xl hover:shadow-indigo-500/40 sm:w-auto">
                    {t('landing.hero.cta')}
                    <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                  </Button>
                </Link>
                <button onClick={() => scrollToSection('pricing')} className="w-full sm:w-auto">
                  <Button size="lg" variant="outline" className="w-full border-2 border-white/15 bg-white/5 px-8 py-6 text-lg font-semibold text-white backdrop-blur transition-all hover:border-indigo-400/50 hover:bg-white/10 sm:w-auto">
                    {t('landing.hero.watchDemo')}
                  </Button>
                </button>
              </div>

              <ul className="mt-10 flex flex-col items-center gap-5 sm:flex-row lg:justify-start">
                {(['trustBadge1', 'trustBadge2', 'trustBadge3'] as const).map(b => (
                  <li key={b} className="flex items-center gap-2 text-sm text-slate-400">
                    <Check className="h-5 w-5 text-emerald-400" aria-hidden="true" />
                    {t(`landing.hero.${b}`)}
                  </li>
                ))}
              </ul>
            </div>

            {/* Right: live chat demo (glass) */}
            <div className="relative">
              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-indigo-950/50 backdrop-blur-xl">
                <div className="flex items-center gap-3 border-b border-white/10 pb-4">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600">
                    <Bot className="h-5 w-5 text-white" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="font-semibold text-white">Kribaat AI</p>
                    <p className="flex items-center gap-1.5 text-xs text-emerald-400">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" aria-hidden="true" />
                      {t('landing.hero.chatOnline')}
                    </p>
                  </div>
                </div>

                <div className="space-y-3 py-4">
                  <div className="ml-auto max-w-[80%] rounded-2xl rounded-tr-sm bg-gradient-to-r from-indigo-500 to-violet-600 p-4">
                    <p className="text-sm text-white">{t('landing.hero.chatMsg1')}</p>
                  </div>
                  <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-white/10 p-4">
                    <p className="text-sm text-slate-100">{t('landing.hero.chatMsg2')}</p>
                  </div>
                  <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-white/10 p-4">
                    <p className="text-sm text-slate-100">{t('landing.hero.chatMsg3')}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <span className="flex gap-1" aria-hidden="true">
                    {[0, 150, 300].map(d => (
                      <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-indigo-400" style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </span>
                  {t('landing.hero.aiTyping')}
                </div>
              </div>

              {/* floating stat chips */}
              <div className="absolute -bottom-6 -left-6 hidden animate-float-y rounded-2xl border border-white/10 bg-slate-900/80 p-4 shadow-xl backdrop-blur sm:block">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/15">
                    <BarChart3 className="h-5 w-5 text-emerald-400" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-2xl font-bold text-white">95%</p>
                    <p className="text-xs text-slate-400">{t('landing.hero.statAutomated')}</p>
                  </div>
                </div>
              </div>
              <div className="absolute -right-4 -top-4 hidden animate-float-y rounded-2xl border border-white/10 bg-slate-900/80 p-4 shadow-xl backdrop-blur [animation-delay:-3s] sm:block">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-500/15">
                    <Clock className="h-5 w-5 text-indigo-300" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-2xl font-bold text-white">24/7</p>
                    <p className="text-xs text-slate-400">{t('landing.hero.statSupport')}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ MARQUEE 1: channels, scrolls LEFT → RIGHT ============ */}
      <section className="border-y border-white/5 bg-slate-900/40 py-10">
        <p className="mb-6 text-center text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
          {t('landing.logos.title')}
        </p>
        <Marquee direction="right" speed="50s">
          {CHANNELS.map(({ icon: Icon, label }, i) => (
            <div key={i} className="flex items-center gap-3 rounded-2xl border border-white/5 bg-white/[0.03] px-7 py-4 text-slate-300">
              <Icon className="h-7 w-7 text-indigo-300/80" aria-hidden="true" />
              <span className="whitespace-nowrap text-lg font-semibold">{label}</span>
            </div>
          ))}
        </Marquee>
      </section>

      {/* ====================== FEATURES (marquee L→R) ====================== */}
      <section id="features" className="scroll-mt-20 py-20 md:py-28">
        <div className={`${SHELL} text-center`}>
          <SectionBadge icon={Zap} tone="indigo">{t('landing.features.badge')}</SectionBadge>
          <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
            {t('landing.features.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-pretty text-lg text-slate-400">
            {t('landing.features.subtitle')}
          </p>
        </div>

        {/* Row scrolling left → right */}
        <div className="mt-14">
          <Marquee direction="left" speed="55s">
            {FEATURES.map((f, i) => (
              <FeatureCard key={`a-${i}`} icon={f.icon} fkey={f.key} gradient={f.gradient} t={t} />
            ))}
          </Marquee>
        </div>
        {/* Second row scrolling right → left for the opposing-motion effect */}
        <div className="mt-6">
          <Marquee direction="right" speed="65s">
            {[...FEATURES].reverse().map((f, i) => (
              <FeatureCard key={`b-${i}`} icon={f.icon} fkey={f.key} gradient={f.gradient} t={t} />
            ))}
          </Marquee>
        </div>
      </section>

      {/* ====================== SOLUTIONS ====================== */}
      <section id="solutions" className="scroll-mt-20 py-20 md:py-28">
        <div className={SHELL}>
          <div className="mb-14 text-center">
            <SectionBadge icon={Building2} tone="violet">{t('landing.solutions.badge')}</SectionBadge>
            <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
              {t('landing.solutions.title')}
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-pretty text-lg text-slate-400">
              {t('landing.solutions.subtitle')}
            </p>
          </div>

          <div className="grid gap-8 lg:grid-cols-2">
            <SolutionCard
              icon={UtensilsCrossed}
              gradient="from-orange-500 to-rose-500"
              accent="text-orange-300 hover:text-orange-200"
              title={t('landing.solutions.restaurant.title')}
              subtitle={t('landing.solutions.restaurant.subtitle')}
              features={[1, 2, 3, 4].map(n => t(`landing.solutions.restaurant.feature${n}`))}
              learnMore={t('landing.solutions.learnMore')}
            />
            <SolutionCard
              icon={Building2}
              gradient="from-indigo-500 to-violet-600"
              accent="text-indigo-300 hover:text-indigo-200"
              title={t('landing.solutions.realEstate.title')}
              subtitle={t('landing.solutions.realEstate.subtitle')}
              features={[1, 2, 3, 4].map(n => t(`landing.solutions.realEstate.feature${n}`))}
              learnMore={t('landing.solutions.learnMore')}
            />
          </div>
        </div>
      </section>

      {/* ====================== SHOWCASE (interactive card fan) ====================== */}
      <section id="showcase" className="relative scroll-mt-20 overflow-hidden py-20 md:py-28">
        {/* decorative glow behind the fan */}
        <div className="pointer-events-none absolute inset-0" aria-hidden="true">
          <div className="absolute left-1/2 top-1/3 h-[30rem] w-[30rem] -translate-x-1/2 animate-aurora-drift rounded-full bg-violet-600/15 blur-[140px]" />
        </div>

        <div className={`${SHELL} relative text-center`}>
          <SectionBadge icon={Sparkles} tone="violet">{t('landing.showcase.badge')}</SectionBadge>
          <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
            {t('landing.showcase.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-pretty text-lg text-slate-400">
            {t('landing.showcase.subtitle')}
          </p>
        </div>

        {/* The fan itself: drag a card to the top, hover to spread, paginate with arrows. */}
        <div className="relative mt-10">
          <CardFanCarousel cards={SHOWCASE_CARDS} />
        </div>

        {/* Caption strip naming the surfaces the cards represent. */}
        <div className={`${SHELL} relative mt-6`}>
          <ul className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-3">
            {SHOWCASE_SURFACES.map(({ icon: Icon, key }) => (
              <li
                key={key}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-slate-300 backdrop-blur transition-colors hover:border-violet-400/40 hover:text-white"
              >
                <Icon className="h-4 w-4 text-violet-300" aria-hidden="true" />
                {t(`landing.showcase.surfaces.${key}`)}
              </li>
            ))}
          </ul>
          <p className="mt-6 text-center text-sm text-slate-500">{t('landing.showcase.hint')}</p>
        </div>
      </section>

      {/* ====================== STATS ====================== */}
      <section className="py-8">
        <div className={SHELL}>
          <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-r from-indigo-600/90 via-violet-600/90 to-fuchsia-600/90 px-6 py-14">
            <div className="pointer-events-none absolute inset-0 bg-grid-glow opacity-30" aria-hidden="true" />
            <div className="relative grid grid-cols-2 gap-8 text-center text-white lg:grid-cols-4">
              {STATS.map(({ value, key }) => (
                <div key={key}>
                  <p className="text-4xl font-bold sm:text-5xl">{value}</p>
                  <p className="mt-1 text-sm text-indigo-100">{t(`landing.stats.${key}`)}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ====================== PRICING ====================== */}
      <section id="pricing" className="scroll-mt-20 py-20 md:py-28">
        <div className={SHELL}>
          <div className="mb-14 text-center">
            <SectionBadge icon={Zap} tone="emerald">{t('landing.pricing.badge')}</SectionBadge>
            <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
              {t('landing.pricing.title')}
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-pretty text-lg text-slate-400">
              {t('landing.pricing.subtitle')}
            </p>
          </div>

          <div className="mx-auto grid max-w-5xl gap-6 md:grid-cols-2 lg:grid-cols-3 lg:gap-8">
            <PricingCard
              name={t('landing.pricing.starter.name')}
              description={t('landing.pricing.starter.description')}
              price="$49" per={t('landing.pricing.perMonth')}
              features={[1, 2, 3, 4, 5, 6].map(n => t(`landing.pricing.starter.feature${n}`))}
              cta={t('landing.pricing.getStarted')}
            />
            <PricingCard
              featured
              popularLabel={t('landing.pricing.popular')}
              name={t('landing.pricing.pro.name')}
              description={t('landing.pricing.pro.description')}
              price="$99" per={t('landing.pricing.perMonth')}
              features={[1, 2, 3, 4, 5, 6].map(n => t(`landing.pricing.pro.feature${n}`))}
              cta={t('landing.pricing.getStarted')}
            />
            <PricingCard
              name={t('landing.pricing.enterprise.name')}
              description={t('landing.pricing.enterprise.description')}
              price={t('landing.pricing.custom')}
              features={[1, 2, 3, 4, 5, 6].map(n => t(`landing.pricing.enterprise.feature${n}`))}
              cta={t('landing.pricing.contactSales')}
            />
          </div>
        </div>
      </section>

      {/* ====================== TESTIMONIALS ====================== */}
      <section id="testimonials" className="scroll-mt-20 py-20 md:py-28">
        <div className={`${SHELL} text-center`}>
          <SectionBadge icon={Star} tone="fuchsia">{t('landing.testimonials.badge')}</SectionBadge>
          <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
            {t('landing.testimonials.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-pretty text-lg text-slate-400">
            {t('landing.testimonials.subtitle')}
          </p>
        </div>

        <div className="mt-14">
          <Marquee direction="left" speed="70s">
            {TESTIMONIALS.map(({ id, initials, gradient }, i) => (
              <figure key={i} className="flex w-[22rem] shrink-0 flex-col rounded-2xl border border-white/10 bg-white/[0.04] p-7 backdrop-blur">
                <div className="mb-4 flex gap-1" aria-hidden="true">
                  {Array.from({ length: 5 }).map((_, s) => (
                    <Star key={s} className="h-4 w-4 fill-amber-400 text-amber-400" />
                  ))}
                </div>
                <blockquote className="flex-1 text-pretty text-slate-300">
                  “{t(`landing.testimonials.${id}.text`)}”
                </blockquote>
                <figcaption className="mt-6 flex items-center gap-3">
                  <span className={`flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br ${gradient} text-sm font-bold text-white`}>
                    {initials}
                  </span>
                  <span>
                    <span className="block font-semibold text-white">{t(`landing.testimonials.${id}.name`)}</span>
                    <span className="block text-sm text-slate-400">{t(`landing.testimonials.${id}.role`)}</span>
                  </span>
                </figcaption>
              </figure>
            ))}
          </Marquee>
        </div>
      </section>

      {/* ====================== FINAL CTA ====================== */}
      <section className="py-20">
        <div className={SHELL}>
          <div className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 px-6 py-20 text-center">
            <div className="pointer-events-none absolute inset-0" aria-hidden="true">
              <div className="absolute -right-24 -top-24 h-72 w-72 animate-aurora-drift rounded-full bg-white/15 blur-3xl" />
              <div className="absolute -bottom-24 -left-24 h-72 w-72 animate-aurora-drift rounded-full bg-white/10 blur-3xl [animation-delay:-7s]" />
            </div>
            <div className="relative mx-auto max-w-3xl">
              <h2 className="text-balance text-3xl font-bold text-white sm:text-4xl lg:text-5xl">
                {t('landing.cta.title')}
              </h2>
              <p className="mx-auto mt-5 max-w-2xl text-pretty text-lg text-indigo-100">
                {t('landing.cta.subtitle')}
              </p>
              <div className="mt-10 flex flex-col justify-center gap-4 sm:flex-row">
                <Link to="/register" className="w-full sm:w-auto">
                  <Button size="lg" className="group w-full bg-white px-8 py-6 text-lg font-semibold text-indigo-700 shadow-xl hover:bg-indigo-50 sm:w-auto">
                    {t('landing.cta.button')}
                    <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                  </Button>
                </Link>
                <Link to="/login" className="w-full sm:w-auto">
                  <Button size="lg" variant="outline" className="w-full border-2 border-white/40 bg-white/10 px-8 py-6 text-lg font-semibold text-white backdrop-blur transition-all hover:bg-white hover:text-indigo-700 sm:w-auto">
                    {t('landing.cta.loginButton')}
                  </Button>
                </Link>
              </div>
              <p className="mt-6 text-sm text-indigo-100">{t('landing.cta.noCreditCard')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ====================== FOOTER ====================== */}
      <footer className="border-t border-white/5 bg-slate-950 py-16">
        <div className={SHELL}>
          <div className="mb-12 grid gap-12 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className="mb-5 flex items-center gap-2.5">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600">
                  <MessageSquare className="h-5 w-5 text-white" aria-hidden="true" />
                </span>
                <span className="text-xl font-bold text-white">Kribaat</span>
              </div>
              <p className="max-w-xs text-pretty text-sm text-slate-400">{t('landing.footer.description')}</p>
            </div>

            <FooterCol title={t('landing.footer.product')}>
              <FooterBtn onClick={() => scrollToSection('features')}>{t('landing.footer.features')}</FooterBtn>
              <FooterBtn onClick={() => scrollToSection('pricing')}>{t('landing.footer.pricing')}</FooterBtn>
              <FooterBtn onClick={() => scrollToSection('solutions')}>{t('landing.footer.solutions')}</FooterBtn>
            </FooterCol>

            <FooterCol title={t('landing.footer.company')}>
              <FooterSoon>{t('landing.footer.about')}</FooterSoon>
              <FooterSoon>{t('landing.footer.contact')}</FooterSoon>
              <FooterSoon>{t('landing.footer.careers')}</FooterSoon>
            </FooterCol>

            <FooterCol title={t('landing.footer.legal')}>
              <li><Link to="/privacy" className="text-slate-400 transition-colors hover:text-white">{t('landing.footer.privacy')}</Link></li>
              <li><Link to="/terms" className="text-slate-400 transition-colors hover:text-white">{t('landing.footer.terms')}</Link></li>
            </FooterCol>
          </div>

          <div className="flex flex-col items-center justify-between gap-4 border-t border-white/5 pt-8 md:flex-row">
            <p className="text-sm text-slate-500">© {new Date().getFullYear()} Kribaat. {t('landing.footer.rights')}</p>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <HeadphonesIcon className="h-5 w-5" aria-hidden="true" />
              {t('landing.footer.support')}
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

/* ============================ DATA ============================ */

const CHANNELS = [
  { icon: MessageSquare, label: 'WhatsApp' },
  { icon: Globe, label: 'Website Chat' },
  { icon: Users, label: 'Instagram' },
  { icon: UtensilsCrossed, label: 'Restaurants' },
  { icon: Building2, label: 'Real Estate' },
  { icon: Home, label: 'Property Mgmt' },
  { icon: Bot, label: 'AI Assistant' },
]

const FEATURES = [
  { icon: Bot, key: 'ai', gradient: 'from-indigo-500 to-blue-600' },
  { icon: MessageSquare, key: 'omnichannel', gradient: 'from-violet-500 to-indigo-600' },
  { icon: Users, key: 'handoff', gradient: 'from-fuchsia-500 to-violet-600' },
  { icon: BarChart3, key: 'analytics', gradient: 'from-emerald-500 to-teal-600' },
  { icon: Globe, key: 'multilingual', gradient: 'from-amber-500 to-orange-600' },
  { icon: Shield, key: 'security', gradient: 'from-rose-500 to-pink-600' },
] as const

/**
 * Showcase fan cards. Each card depicts one product surface using a stable
 * Unsplash photo (id-pinned, portrait crop so it sits well in the 2:3 card).
 * Ordered so the platform story reads center-out: the AI inbox sits in the
 * middle slot, with the verticals and growth tools fanning to either side.
 */
const UNSPLASH = (id: string) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=600&h=900&q=80`

const SHOWCASE_CARDS: CardItem[] = [
  { imgUrl: UNSPLASH('photo-1551434678-e076c223a692'), alt: 'Real-time analytics dashboard' },
  { imgUrl: UNSPLASH('photo-1556742502-ec7c0e9f34b1'), alt: 'AI credit wallet and billing' },
  { imgUrl: UNSPLASH('photo-1414235077428-338989a2e8c0'), alt: 'Restaurant bookings and menu' },
  { imgUrl: UNSPLASH('photo-1531746790731-6c087fecd65a'), alt: 'Unified AI inbox' },
  { imgUrl: UNSPLASH('photo-1560518883-ce09059eeffa'), alt: 'Real estate listings and leads' },
  { imgUrl: UNSPLASH('photo-1607082348824-0a96f2a4b9da'), alt: 'AI content studio image generation' },
  { imgUrl: UNSPLASH('photo-1556745753-b2904692b3cd'), alt: 'Inventory and recipe management' },
]

const SHOWCASE_SURFACES = [
  { icon: Bot, key: 'inbox' },
  { icon: LayoutDashboard, key: 'analytics' },
  { icon: Users, key: 'crm' },
  { icon: Gift, key: 'luckyDraw' },
  { icon: ImageIcon, key: 'studio' },
  { icon: Boxes, key: 'inventory' },
  { icon: Wallet, key: 'billing' },
] as const

const STATS = [
  { value: '95%', key: 'automation' },
  { value: '24/7', key: 'availability' },
  { value: '3x', key: 'efficiency' },
  { value: '50%', key: 'savings' },
] as const

const TESTIMONIALS = [
  { id: 'review1', initials: 'JC', gradient: 'from-orange-400 to-rose-500' },
  { id: 'review2', initials: 'SL', gradient: 'from-indigo-400 to-violet-500' },
  { id: 'review3', initials: 'MW', gradient: 'from-emerald-400 to-teal-500' },
] as const

/* ============================ PIECES ============================ */

type TFn = (key: string) => string

/**
 * Seamless horizontal marquee. Renders the children twice and translates the
 * track by 50% so it loops without a visible seam. Pauses on hover/focus and
 * is disabled under prefers-reduced-motion (see index.css).
 */
function Marquee({
  children, direction, speed = '60s',
}: {
  children: React.ReactNode
  direction: 'left' | 'right'
  speed?: string
}) {
  const anim = direction === 'left' ? 'animate-marquee-left' : 'animate-marquee-right'
  return (
    <div className="marquee-mask group/marquee w-full overflow-hidden">
      <div
        className={`marquee-track flex w-max ${anim} gap-6 px-6 lg:px-8`}
        style={{ ['--marquee-duration' as string]: speed }}
      >
        {/* duplicated track for a seamless loop; aria-hidden on the clone */}
        <div className="flex shrink-0 gap-6">{children}</div>
        <div className="flex shrink-0 gap-6" aria-hidden="true">{children}</div>
      </div>
    </div>
  )
}

function FeatureCard({
  icon: Icon, fkey, gradient, t,
}: {
  icon: React.ComponentType<{ className?: string }>
  fkey: string
  gradient: string
  t: TFn
}) {
  return (
    <article className="flex w-[20rem] shrink-0 flex-col rounded-2xl border border-white/10 bg-white/[0.04] p-7 backdrop-blur transition-colors hover:border-indigo-400/30 hover:bg-white/[0.07]">
      <span className={`mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${gradient} shadow-lg`}>
        <Icon className="h-6 w-6 text-white" />
      </span>
      <h3 className="mb-2 text-lg font-bold text-white">{t(`landing.features.${fkey}.title`)}</h3>
      <p className="text-pretty text-sm leading-relaxed text-slate-400">{t(`landing.features.${fkey}.description`)}</p>
    </article>
  )
}

function SectionBadge({
  icon: Icon, tone, children,
}: {
  icon: React.ComponentType<{ className?: string }>
  tone: 'indigo' | 'violet' | 'emerald' | 'fuchsia'
  children: React.ReactNode
}) {
  const tones = {
    indigo: 'text-indigo-300',
    violet: 'text-violet-300',
    emerald: 'text-emerald-300',
    fuchsia: 'text-fuchsia-300',
  } as const
  return (
    <div className={`mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm font-medium ${tones[tone]}`}>
      <Icon className="h-4 w-4" />
      {children}
    </div>
  )
}

function SolutionCard({
  icon: Icon, gradient, accent, title, subtitle, features, learnMore,
}: {
  icon: React.ComponentType<{ className?: string }>
  gradient: string
  accent: string
  title: string
  subtitle: string
  features: string[]
  learnMore: string
}) {
  return (
    <div className="group overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] backdrop-blur transition-all hover:-translate-y-1 hover:border-white/20">
      <div className={`bg-gradient-to-br ${gradient} p-8`}>
        <Icon className="mb-4 h-11 w-11 text-white transition-transform group-hover:scale-110" aria-hidden="true" />
        <h3 className="text-2xl font-bold text-white">{title}</h3>
        <p className="mt-1 text-white/90">{subtitle}</p>
      </div>
      <div className="p-8">
        <ul className="space-y-4">
          {features.map((f, i) => (
            <li key={i} className="flex items-start gap-3">
              <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
              <span className="text-slate-300">{f}</span>
            </li>
          ))}
        </ul>
        <Link to="/register" className={`mt-7 inline-flex items-center gap-2 font-semibold transition-all group-hover:gap-3 ${accent}`}>
          {learnMore}
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </div>
  )
}

function PricingCard({
  name, description, price, per, features, cta, featured, popularLabel,
}: {
  name: string
  description: string
  price: string
  per?: string
  features: string[]
  cta: string
  featured?: boolean
  popularLabel?: string
}) {
  return (
    <div className={`relative rounded-3xl border p-8 backdrop-blur transition-all hover:-translate-y-1 ${
      featured
        ? 'border-indigo-400/50 bg-gradient-to-b from-indigo-500/10 to-white/[0.03] shadow-2xl shadow-indigo-500/20'
        : 'border-white/10 bg-white/[0.03] hover:border-white/20'
    }`}>
      {featured && popularLabel && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-500 to-violet-600 px-4 py-1 text-xs font-semibold text-white shadow-lg">
          {popularLabel}
        </span>
      )}
      <h3 className="text-lg font-bold text-white">{name}</h3>
      <p className="mt-1 text-sm text-slate-400">{description}</p>
      <div className="mt-6 flex items-baseline gap-1">
        <span className="text-4xl font-bold text-white">{price}</span>
        {per && <span className="text-slate-400">{per}</span>}
      </div>
      <ul className="mt-7 space-y-3">
        {features.map((f, i) => (
          <li key={i} className="flex items-center gap-2 text-sm text-slate-300">
            <Check className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
            {f}
          </li>
        ))}
      </ul>
      <Link to="/register" className="mt-8 block">
        <Button className={`w-full font-semibold ${
          featured
            ? 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30 hover:from-indigo-400 hover:to-violet-500'
            : 'border border-white/15 bg-white/5 text-white hover:bg-white/10'
        }`}>
          {cta}
        </Button>
      </Link>
    </div>
  )
}

function FooterCol({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-4 font-semibold text-white">{title}</h4>
      <ul className="space-y-3 text-sm">{children}</ul>
    </div>
  )
}

function FooterBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <li>
      <button onClick={onClick} className="text-left text-slate-400 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400">
        {children}
      </button>
    </li>
  )
}

function FooterSoon({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 text-slate-400">
      {children}
      <span className="rounded bg-indigo-500/15 px-2 py-0.5 text-xs text-indigo-300">Coming Soon</span>
    </li>
  )
}
