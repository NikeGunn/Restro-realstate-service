import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { showcaseApi, type ShowcaseVideo } from '@/services/api'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import {
  ArrowRight, ArrowUpRight, Check, Menu, X, MessageCircle, Instagram, Globe,
  Building2, UtensilsCrossed, Bot, Users, BarChart3, Shield, Languages, ShieldCheck, Play,
} from 'lucide-react'

/* ------------------------------------------------------------------ *
 * kribaat.com landing page. Brand: brand-memory.md (repo root).
 *
 * Direction "Himalayan editorial": warm paper, ink and pine, Fraunces display with gold/brick
 * italic emphasis, paper grain, ridge-line dividers. The one thing to remember is the live agent
 * demo: a real-looking WhatsApp chat in Romanized Nepali where the agent's tool calls and the
 * verification step tick in before each answer, so "agentic" is shown, not claimed.
 * Every claim on this page is something the product actually does (no invented metrics).
 * ------------------------------------------------------------------ */

const SHELL = 'mx-auto w-full max-w-6xl px-5 sm:px-8'
const PROPERTIES_URL = '/realestate/properties/'

export function LandingPage() {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  // Showcase films uploaded by a superuser in Django admin; the demo section only exists when one is live.
  const { data: videos = [] } = useQuery({
    queryKey: ['showcase', 'landing'], queryFn: () => showcaseApi.list('landing'), staleTime: 5 * 60_000, retry: 1,
  })
  const [playing, setPlaying] = useState<ShowcaseVideo | null>(null)

  const go = (id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    window.scrollTo({ top: el.getBoundingClientRect().top + window.pageYOffset - 76, behavior: 'smooth' })
    setMenuOpen(false)
  }

  const nav: { id: string; label: string }[] = [
    ...(videos.length ? [{ id: 'demo', label: t('home.video.nav') }] : []),
    { id: 'agent', label: t('home.nav.agent') },
    { id: 'verticals', label: t('home.nav.verticals') },
    { id: 'pricing', label: t('home.nav.pricing') },
  ]

  return (
    <div className="kb-grain min-h-screen bg-kb-paper font-brand text-kb-ink antialiased selection:bg-kb-gold/30 [touch-action:manipulation]">
      {/* ============================== NAV ============================== */}
      <header className="fixed inset-x-0 top-0 z-50 border-b border-kb-line/80 bg-kb-paper/85 backdrop-blur-md">
        <div className={`${SHELL} flex h-[68px] items-center gap-6`}>
          <a href="#top" className="flex items-center gap-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kb-gold" aria-label="Kribaat home">
            <RidgeMark />
            <span className="font-display text-[22px] font-bold tracking-tight">Kribaat</span>
          </a>
          <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="Main">
            {nav.map(n => (
              <button key={n.id} onClick={() => go(n.id)} className="rounded-full px-3.5 py-2 text-[15px] font-semibold text-kb-muted transition-colors hover:bg-kb-paper2 hover:text-kb-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kb-gold">
                {n.label}
              </button>
            ))}
            <a href={PROPERTIES_URL} className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[15px] font-semibold text-kb-pine transition-colors hover:bg-kb-paper2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kb-gold">
              <span className="relative flex h-2 w-2" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-kb-wa opacity-50 motion-reduce:animate-none" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-kb-wa" />
              </span>
              {t('home.nav.live')}
            </a>
          </nav>
          <div className="ml-auto hidden items-center gap-2 md:flex">
            <LanguageSwitcher variant="compact" />
            <Link to="/login" className="whitespace-nowrap rounded-full px-4 py-2 text-[15px] font-semibold text-kb-ink hover:bg-kb-paper2">{t('home.nav.signIn')}</Link>
            <Link to="/register" className="whitespace-nowrap rounded-full bg-kb-ink px-5 py-2.5 text-[15px] font-semibold text-kb-paper shadow-sm transition-colors hover:bg-kb-pine">{t('home.nav.start')}</Link>
          </div>
          <div className="ml-auto flex items-center gap-1 md:hidden">
            <LanguageSwitcher variant="compact" />
            <button onClick={() => setMenuOpen(v => !v)} className="rounded-lg p-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kb-gold"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}>
              {menuOpen ? <X className="h-6 w-6" aria-hidden="true" /> : <Menu className="h-6 w-6" aria-hidden="true" />}
            </button>
          </div>
        </div>
        {menuOpen && (
          <div className="border-t border-kb-line bg-kb-paper px-5 pb-5 pt-2 md:hidden">
            {nav.map(n => (
              <button key={n.id} onClick={() => go(n.id)} className="block w-full rounded-lg px-2 py-3 text-left text-base font-semibold">{n.label}</button>
            ))}
            <a href={PROPERTIES_URL} className="block rounded-lg px-2 py-3 text-base font-semibold text-kb-pine">{t('home.nav.live')}</a>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Link to="/login" className="rounded-full border border-kb-line py-3 text-center font-semibold">{t('home.nav.signIn')}</Link>
              <Link to="/register" className="rounded-full bg-kb-ink py-3 text-center font-semibold text-kb-paper">{t('home.nav.start')}</Link>
            </div>
          </div>
        )}
      </header>

      <main id="top">
        {/* ============================== HERO ============================== */}
        <section className="relative overflow-hidden pb-24 pt-32 md:pb-28 md:pt-40">
          <div className={`${SHELL} grid items-center gap-14 lg:grid-cols-[1.08fr_.92fr]`}>
            <div>
              <p className="animate-rise text-xs font-bold uppercase tracking-[.22em] text-kb-brick">{t('home.hero.eyebrow')}</p>
              <h1 className="mt-5 animate-rise font-display text-[clamp(40px,6vw,74px)] font-semibold leading-[1.02] tracking-[-.02em] [animation-delay:80ms]">
                {t('home.hero.title')}{' '}
                <em className="font-normal italic text-kb-brick">{t('home.hero.titleEm')}</em>
              </h1>
              <p className="mt-6 max-w-[54ch] animate-rise text-lg leading-relaxed text-kb-muted [animation-delay:160ms]">{t('home.hero.sub')}</p>
              <div className="mt-9 flex animate-rise flex-col gap-3 sm:flex-row [animation-delay:220ms]">
                <Link to="/register" className="group inline-flex items-center justify-center gap-2 rounded-full bg-kb-ink px-7 py-4 text-base font-semibold text-kb-paper shadow-[0_14px_30px_-14px_rgba(20,35,31,.7)] transition-colors hover:bg-kb-pine">
                  {t('home.hero.ctaPrimary')}
                  <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                </Link>
                {videos.length > 0 ? (
                  <button onClick={() => setPlaying(videos[0])} className="group inline-flex items-center justify-center gap-3 rounded-full py-2 pl-2 pr-6 text-base font-semibold text-kb-ink ring-[1.5px] ring-inset ring-kb-line transition hover:ring-kb-ink">
                    <span className="flex h-10 w-10 items-center justify-center rounded-full bg-kb-brick text-kb-paper transition-transform group-hover:scale-105">
                      <Play className="ml-0.5 h-4 w-4 fill-current" aria-hidden="true" />
                    </span>
                    {t('home.video.watch')}
                  </button>
                ) : (
                  <a href={PROPERTIES_URL} className="group inline-flex items-center justify-center gap-2 rounded-full px-7 py-4 text-base font-semibold text-kb-ink ring-[1.5px] ring-inset ring-kb-line transition hover:ring-kb-ink">
                    {t('home.hero.ctaLive')}
                    <ArrowUpRight className="h-5 w-5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden="true" />
                  </a>
                )}
              </div>
              <ul className="mt-10 grid animate-rise gap-3 text-[15px] text-kb-ink/80 [animation-delay:300ms] sm:grid-cols-3 sm:gap-5">
                {(['proof1', 'proof2', 'proof3'] as const).map(k => (
                  <li key={k} className="flex items-start gap-2.5">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-kb-pine text-kb-paper"><Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" /></span>
                    <span className="leading-snug">{t(`home.hero.${k}`)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="animate-rise [animation-delay:180ms]">
              <AgentDemo />
            </div>
          </div>
        </section>

        {/* ============================== STRIP ============================== */}
        <section className="border-y border-kb-line bg-kb-card/70">
          <div className={`${SHELL} grid gap-6 py-8 text-[15px] sm:grid-cols-3`}>
            <StripItem icon={<span className="flex gap-1.5"><MessageCircle className="h-5 w-5" /><Instagram className="h-5 w-5" /><Globe className="h-5 w-5" /></span>} title={t('home.strip.channels')} />
            <StripItem icon={<Languages className="h-5 w-5" />} title={<span className="font-deva">{t('home.strip.languages')}</span>} />
            <StripItem icon={<Users className="h-5 w-5" />} title={t('home.strip.human')} />
          </div>
        </section>

        {/* ============================== WATCH THE DEMO (admin-uploaded films) ============================== */}
        {videos.length > 0 && <DemoSection videos={videos} onPlay={setPlaying} />}

        {/* ============================== HOW THE AGENT THINKS ============================== */}
        <section id="agent" className="relative mt-24 scroll-mt-20 bg-kb-ink text-kb-paper">
          <Ridge className="absolute -top-[59px] left-0 h-[60px] w-full text-kb-ink" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(800px_380px_at_85%_0%,rgba(201,154,60,.22),transparent_60%),radial-gradient(700px_360px_at_0%_100%,rgba(46,106,87,.5),transparent_60%)]" aria-hidden="true" />
          <div className={`${SHELL} relative py-24 md:py-28`}>
            <p className="text-xs font-bold uppercase tracking-[.22em] text-kb-gold">{t('home.agent.eyebrow')}</p>
            <h2 className="mt-4 max-w-[20ch] font-display text-[clamp(30px,4vw,48px)] font-semibold leading-[1.08] tracking-[-.02em]">
              {t('home.agent.title')} <em className="font-normal italic text-kb-gold">{t('home.agent.titleEm')}</em>
            </h2>
            <ol className="mt-14 grid gap-px overflow-hidden rounded-[22px] border border-white/10 bg-white/10 md:grid-cols-2 lg:grid-cols-4">
              {(['understand', 'lookup', 'verify', 'act'] as const).map((k, i) => (
                <li key={k} className="bg-kb-ink/95 p-7">
                  <div className="flex items-baseline justify-between">
                    <span className="font-display text-5xl font-semibold text-kb-gold/90">{String(i + 1).padStart(2, '0')}</span>
                    <code className="rounded-md bg-white/5 px-2 py-1 font-mono text-[11px] text-kb-paper/60">{STEP_CODE[k]}</code>
                  </div>
                  <h3 className="mt-6 text-xl font-semibold">{t(`home.agent.${k}.title`)}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-kb-paper/70">{t(`home.agent.${k}.body`)}</p>
                </li>
              ))}
            </ol>
          </div>
          <Ridge className="absolute -bottom-px left-0 h-[60px] w-full rotate-180 text-kb-paper" />
        </section>

        {/* ============================== VERTICALS ============================== */}
        <section id="verticals" className="scroll-mt-20 py-24 md:py-28">
          <div className={SHELL}>
            <SectionHead eyebrow={t('home.verticals.eyebrow')} title={t('home.verticals.title')} />
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              <VerticalCard
                icon={<Building2 className="h-6 w-6" aria-hidden="true" />}
                tone="pine"
                image="https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=70"
                title={t('home.verticals.realEstate.title')}
                body={t('home.verticals.realEstate.body')}
                bullets={[1, 2, 3, 4].map(n => t(`landing.solutions.realEstate.feature${n}`))}
                link={{ href: PROPERTIES_URL, label: t('home.verticals.realEstate.link'), external: true }}
              />
              <VerticalCard
                icon={<UtensilsCrossed className="h-6 w-6" aria-hidden="true" />}
                tone="brick"
                image="https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1200&q=70"
                title={t('home.verticals.restaurant.title')}
                body={t('home.verticals.restaurant.body')}
                bullets={[1, 2, 3, 4].map(n => t(`landing.solutions.restaurant.feature${n}`))}
                link={{ href: '/register', label: t('home.verticals.restaurant.link') }}
              />
            </div>
            <p className="mt-6 flex items-center gap-2 text-sm text-kb-muted">
              <ShieldCheck className="h-4 w-4 text-kb-pine" aria-hidden="true" />{t('home.verticals.isolated')}
            </p>
          </div>
        </section>

        {/* ============================== LIVE AGENCY ============================== */}
        <section className="pb-24">
          <div className={SHELL}>
            <a href={PROPERTIES_URL} className="group relative grid overflow-hidden rounded-[28px] bg-kb-pine text-kb-paper shadow-[0_30px_60px_-30px_rgba(20,35,31,.7)] md:grid-cols-[1.1fr_.9fr]">
              <div className="relative z-10 p-8 md:p-12">
                <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold uppercase tracking-[.18em] text-kb-gold">
                  <span className="h-2 w-2 rounded-full bg-[#5BE38C]" aria-hidden="true" />{t('home.live.eyebrow')}
                </p>
                <h2 className="mt-5 font-display text-[clamp(28px,3.6vw,44px)] font-semibold leading-[1.08] tracking-[-.02em]">{t('home.live.title')}</h2>
                <p className="mt-4 max-w-[46ch] text-[17px] leading-relaxed text-kb-paper/80">{t('home.live.body')}</p>
                <p className="mt-3 font-deva text-kb-paper/70">{t('home.live.ne')}</p>
                <span className="mt-8 inline-flex items-center gap-2 rounded-full bg-kb-paper px-6 py-3.5 font-semibold text-kb-ink transition-transform group-hover:translate-x-1">
                  {t('home.live.cta')}<ArrowUpRight className="h-5 w-5" aria-hidden="true" />
                </span>
              </div>
              <div className="relative min-h-[240px]">
                <img src="https://images.unsplash.com/photo-1544735716-392fe2489ffa?auto=format&fit=crop&w=1100&q=70" alt="Kathmandu valley and the Himalaya at dusk"
                  className="absolute inset-0 h-full w-full object-cover opacity-90 transition-transform duration-700 group-hover:scale-[1.03]" loading="lazy" />
                <div className="absolute inset-0 bg-gradient-to-r from-kb-pine via-kb-pine/30 to-transparent md:via-kb-pine/10" aria-hidden="true" />
              </div>
            </a>
          </div>
        </section>

        {/* ============================== FEATURES ============================== */}
        <section className="border-t border-kb-line bg-kb-card/60 py-24 md:py-28">
          <div className={SHELL}>
            <SectionHead eyebrow={t('home.features.eyebrow')} title={t('home.features.title')} />
            <div className="mt-12 grid gap-px overflow-hidden rounded-[22px] border border-kb-line bg-kb-line sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(({ key, icon: Icon }) => (
                <article key={key} className="bg-kb-card p-7 transition-colors hover:bg-kb-paper">
                  <Icon className="h-6 w-6 text-kb-brick" aria-hidden="true" />
                  <h3 className="mt-5 text-lg font-semibold">{t(`landing.features.${key}.title`)}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-kb-muted">{t(`landing.features.${key}.description`)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ============================== PRICING ============================== */}
        <section id="pricing" className="scroll-mt-20 py-24 md:py-28">
          <div className={SHELL}>
            <SectionHead eyebrow={t('landing.pricing.badge')} title={t('landing.pricing.title')} sub={t('landing.pricing.subtitle')} />
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              <PriceCard name={t('landing.pricing.starter.name')} desc={t('landing.pricing.starter.description')} price="$49" per={t('landing.pricing.perMonth')}
                features={[1, 2, 3, 4, 5, 6].map(n => t(`landing.pricing.starter.feature${n}`))} cta={t('landing.pricing.getStarted')} />
              <PriceCard featured badge={t('landing.pricing.popular')} name={t('landing.pricing.pro.name')} desc={t('landing.pricing.pro.description')} price="$99" per={t('landing.pricing.perMonth')}
                features={[1, 2, 3, 4, 5, 6].map(n => t(`landing.pricing.pro.feature${n}`))} cta={t('landing.pricing.getStarted')} />
              <PriceCard name={t('landing.pricing.enterprise.name')} desc={t('landing.pricing.enterprise.description')} price={t('landing.pricing.custom')}
                features={[1, 2, 3, 4, 5, 6].map(n => t(`landing.pricing.enterprise.feature${n}`))} cta={t('landing.pricing.contactSales')} />
            </div>
          </div>
        </section>

        {/* ============================== CTA ============================== */}
        <section className="pb-24">
          <div className={SHELL}>
            <div className="relative overflow-hidden rounded-[28px] bg-kb-ink px-6 py-16 text-center text-kb-paper md:py-20">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_300px_at_50%_0%,rgba(201,154,60,.25),transparent_70%)]" aria-hidden="true" />
              <Ridge className="absolute bottom-0 left-0 h-16 w-full text-kb-pine/60" />
              <div className="relative mx-auto max-w-2xl">
                <h2 className="font-display text-[clamp(30px,4.4vw,52px)] font-semibold leading-[1.06] tracking-[-.02em]">
                  {t('home.cta.title')} <em className="font-normal italic text-kb-gold">{t('home.cta.titleEm')}</em>
                </h2>
                <p className="mx-auto mt-5 max-w-[48ch] text-lg text-kb-paper/75">{t('home.cta.body')}</p>
                <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
                  <Link to="/register" className="inline-flex items-center justify-center gap-2 rounded-full bg-kb-paper px-7 py-4 font-semibold text-kb-ink transition-colors hover:bg-white">
                    {t('home.cta.primary')}<ArrowRight className="h-5 w-5" aria-hidden="true" />
                  </Link>
                  <Link to="/login" className="inline-flex items-center justify-center rounded-full px-7 py-4 font-semibold text-kb-paper ring-[1.5px] ring-inset ring-white/25 hover:ring-white/60">
                    {t('home.cta.secondary')}
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {playing && <VideoModal video={playing} onClose={() => setPlaying(null)} />}

      {/* ============================== FOOTER ============================== */}
      <footer className="border-t border-kb-line bg-kb-paper2/60">
        <div className={`${SHELL} grid gap-10 py-16 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]`}>
          <div>
            <div className="flex items-center gap-2.5"><RidgeMark /><span className="font-display text-[22px] font-bold">Kribaat</span></div>
            <p className="mt-4 max-w-[30ch] font-display text-lg italic text-kb-ink/80">{t('home.footer.tagline')}</p>
            <p className="mt-3 text-sm text-kb-muted">{t('home.footer.origin')}</p>
          </div>
          <FooterCol title={t('landing.footer.product')}>
            <li><button onClick={() => go('agent')} className="hover:text-kb-brick">{t('home.nav.agent')}</button></li>
            <li><button onClick={() => go('verticals')} className="hover:text-kb-brick">{t('home.nav.verticals')}</button></li>
            <li><button onClick={() => go('pricing')} className="hover:text-kb-brick">{t('home.nav.pricing')}</button></li>
          </FooterCol>
          <FooterCol title={t('home.footer.live')}>
            <li><a href={PROPERTIES_URL} className="hover:text-kb-brick">{t('home.nav.live')}</a></li>
            <li><a href="/realestate/properties/land-for-sale/" className="hover:text-kb-brick">{t('home.footer.land')}</a></li>
            <li><a href="/realestate/properties/rooms-for-rent/" className="hover:text-kb-brick">{t('home.footer.rooms')}</a></li>
          </FooterCol>
          <FooterCol title={t('landing.footer.legal')}>
            <li><Link to="/privacy" className="hover:text-kb-brick">{t('landing.footer.privacy')}</Link></li>
            <li><Link to="/terms" className="hover:text-kb-brick">{t('landing.footer.terms')}</Link></li>
            <li><Link to="/login" className="hover:text-kb-brick">{t('home.nav.signIn')}</Link></li>
          </FooterCol>
        </div>
        <div className={`${SHELL} flex flex-col gap-2 border-t border-kb-line py-6 text-sm text-kb-muted sm:flex-row sm:items-center sm:justify-between`}>
          <span>© {new Date().getFullYear()} Kribaat. {t('landing.footer.rights')}</span>
          <span>{t('landing.footer.support')}</span>
        </div>
      </footer>
    </div>
  )
}

/* ============================ DATA ============================ */

const STEP_CODE = { understand: 'turn_brief', lookup: 'search · details · slots', verify: 'verify_reply', act: 'preview → yes → receipt' } as const

const FEATURES = [
  { key: 'ai', icon: Bot },
  { key: 'omnichannel', icon: MessageCircle },
  { key: 'handoff', icon: Users },
  { key: 'analytics', icon: BarChart3 },
  { key: 'multilingual', icon: Languages },
  { key: 'security', icon: Shield },
] as const

/**
 * The scripted demo chat (real product behaviour, synthetic data). `tools` are the agent's tool
 * calls shown ticking in before its reply; the last one is always the verification gate.
 */
type DemoLine = { who: 'customer' | 'agent'; text: string; tools?: string[] }
const DEMO: DemoLine[] = [
  { who: 'customer', text: 'Kirtipur tira 15 hajar samma kotha chha?' },
  { who: 'agent', tools: ['search_properties · Kirtipur · ≤ Rs 15,000', 'verify · 2 prices match records'],
    text: 'Hajur, Kirtipur ma 2 wata kotha chhan:\n1. PROP803052 · Room near TU gate · Rs 9,500/month\n2. PROP803114 · Room with balcony · Rs 12,000/month\nPhoto herna chahanuhunchha?' },
  { who: 'customer', text: 'pahilo wala bholi 2 baje herna milchha? naam Martas' },
  { who: 'agent', tools: ['get_viewing_slots · Mon 14:00 free', 'prepare_viewing · preview saved'],
    text: 'Yo viewing confirm garidiu?\nPROP803052, Monday 14:00 (Nepal time), naam Martas.' },
  { who: 'customer', text: 'hunxa' },
  { who: 'agent', tools: ['confirm_pending_action · locked', 'receipt · APTK6XSXH'],
    text: 'Confirm bhayo: viewing APTK6XSXH, Monday 14:00. Ek ghanta agadi reminder pathaunchhu.' },
]

/* ============================ PIECES ============================ */

function DemoSection({ videos, onPlay }: { videos: ShowcaseVideo[]; onPlay: (v: ShowcaseVideo) => void }) {
  const { t } = useTranslation()
  const [main, ...more] = videos
  return (
    <section id="demo" className="scroll-mt-20 pt-24">
      <div className={SHELL}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-xs font-bold uppercase tracking-[.22em] text-kb-brick">{t('home.video.eyebrow')}</p>
            <h2 className="mt-4 font-display text-[clamp(30px,4vw,46px)] font-semibold leading-[1.08] tracking-[-.02em]">{main.title}</h2>
            {main.caption && <p className="mt-3 text-lg text-kb-muted">{main.caption}</p>}
          </div>
        </div>
        <button onClick={() => onPlay(main)} aria-label={`${t('home.video.play')}: ${main.title}`}
          className="group relative mt-10 block aspect-video w-full overflow-hidden rounded-[28px] bg-kb-ink shadow-[0_40px_80px_-40px_rgba(20,35,31,.7)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-kb-gold">
          {main.poster_url
            ? <img src={main.poster_url} alt="" className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.02]" />
            : <video src={`${main.video_url}#t=2`} muted playsInline preload="metadata" className="absolute inset-0 h-full w-full object-cover opacity-90" />}
          <span className="absolute inset-0 bg-gradient-to-t from-kb-ink/70 via-kb-ink/10 to-transparent" aria-hidden="true" />
          <span className="absolute left-1/2 top-1/2 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-kb-paper/95 text-kb-ink shadow-2xl transition-transform duration-300 group-hover:scale-110">
            <span className="absolute inset-0 animate-ping rounded-full bg-kb-paper/40 motion-reduce:animate-none" aria-hidden="true" />
            <Play className="relative ml-1 h-9 w-9 fill-current" aria-hidden="true" />
          </span>
          <span className="absolute bottom-5 left-6 flex items-center gap-2 text-sm font-semibold text-kb-paper/90">
            <RidgeMark light /> Kribaat
          </span>
        </button>
        {more.length > 0 && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {more.map(v => (
              <button key={v.id} onClick={() => onPlay(v)} className="group flex items-center gap-4 rounded-2xl border border-kb-line bg-kb-card p-3 text-left transition hover:border-kb-ink">
                <span className="relative aspect-video w-32 shrink-0 overflow-hidden rounded-xl bg-kb-ink">
                  {v.poster_url ? <img src={v.poster_url} alt="" className="h-full w-full object-cover" />
                    : <video src={`${v.video_url}#t=2`} muted preload="metadata" className="h-full w-full object-cover" />}
                  <Play className="absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 fill-kb-paper text-kb-paper" aria-hidden="true" />
                </span>
                <span><span className="block font-semibold">{v.title}</span>{v.caption && <span className="mt-1 block text-sm text-kb-muted">{v.caption}</span>}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function VideoModal({ video, onClose }: { video: ShowcaseVideo; onClose: () => void }) {
  const { t } = useTranslation()
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = prev; window.removeEventListener('keydown', onKey) }
  }, [onClose])
  return (
    <div role="dialog" aria-modal="true" aria-label={video.title}
      className="fixed inset-0 z-[100] flex animate-rise items-center justify-center bg-kb-ink/90 p-4 backdrop-blur-md sm:p-8"
      onClick={onClose}>
      <div className="relative w-full max-w-6xl" onClick={e => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between gap-4 text-kb-paper">
          <p className="truncate font-display text-xl font-semibold">{video.title}</p>
          <button ref={closeRef} onClick={onClose} aria-label={t('home.video.close')}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white/10 transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kb-gold">
            <X className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>
        <video key={video.id} controls autoPlay playsInline preload="auto" poster={video.poster_url || undefined}
          className="aspect-video w-full rounded-2xl bg-black shadow-2xl">
          <source src={video.video_url} type={video.type} />
        </video>
      </div>
    </div>
  )
}

function AgentDemo() {
  const { t } = useTranslation()
  const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [shown, setShown] = useState(reduce ? DEMO.length : 0)
  const [ticks, setTicks] = useState(0)
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (reduce) return
    let line = 0, tick = 0
    const timers: number[] = []
    const step = () => {
      if (line >= DEMO.length) {
        timers.push(window.setTimeout(() => { line = 0; tick = 0; setShown(0); setTicks(0); step() }, 4200))
        return
      }
      const cur = DEMO[line]
      if (cur.who === 'agent' && cur.tools && tick < cur.tools.length) {
        tick += 1
        setTicks(tick)
        timers.push(window.setTimeout(step, 650))
        return
      }
      line += 1
      tick = 0
      setShown(line)
      setTicks(0)
      timers.push(window.setTimeout(step, cur.who === 'customer' ? 900 : 1700))
    }
    timers.push(window.setTimeout(step, 700))
    return () => timers.forEach(window.clearTimeout)
  }, [reduce])

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: reduce ? 'auto' : 'smooth' })
  }, [shown, ticks, reduce])

  const pendingAgent = shown < DEMO.length && DEMO[shown].who === 'agent' ? DEMO[shown] : null

  return (
    <div className="relative mx-auto w-full max-w-[440px]">
      <div className="absolute -inset-6 -z-10 rounded-[44px] bg-[radial-gradient(closest-side,rgba(201,154,60,.25),transparent)]" aria-hidden="true" />
      <div className="overflow-hidden rounded-[30px] border border-kb-line bg-kb-card shadow-[0_40px_80px_-40px_rgba(20,35,31,.55)]">
        <div className="flex items-center gap-3 bg-kb-ink px-5 py-4 text-kb-paper">
          <RidgeMark light />
          <div className="min-w-0">
            <p className="font-semibold leading-tight">{t('home.demo.name')}</p>
            <p className="flex items-center gap-1.5 text-xs text-kb-paper/70"><span className="h-1.5 w-1.5 rounded-full bg-[#5BE38C]" aria-hidden="true" />{t('home.demo.status')}</p>
          </div>
          <span className="ml-auto rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-kb-gold">WhatsApp</span>
        </div>
        <div ref={scroller} className="h-[430px] space-y-3 overflow-hidden bg-[#EFE7D8] px-4 py-5" aria-live="polite" aria-label={t('home.demo.aria')}>
          {DEMO.slice(0, shown).map((l, i) => <Bubble key={i} line={l} done />)}
          {pendingAgent && ticks > 0 && <ToolChips tools={pendingAgent.tools ?? []} count={ticks} />}
        </div>
        <div className="flex items-center gap-2 border-t border-kb-line px-5 py-3 text-xs text-kb-muted">
          <ShieldCheck className="h-4 w-4 text-kb-pine" aria-hidden="true" />{t('home.demo.footer')}
        </div>
      </div>
    </div>
  )
}

function Bubble({ line }: { line: DemoLine; done?: boolean }) {
  const mine = line.who === 'customer'
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'} animate-rise`}>
      <div className="max-w-[86%] space-y-1.5">
        {!mine && line.tools && <ToolChips tools={line.tools} count={line.tools.length} compact />}
        <p className={`whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-[14px] leading-snug shadow-sm ${
          mine ? 'rounded-tr-md bg-[#D9F2C9] text-kb-ink' : 'rounded-tl-md bg-kb-card text-kb-ink'}`}>
          {line.text}
        </p>
      </div>
    </div>
  )
}

function ToolChips({ tools, count, compact }: { tools: string[]; count: number; compact?: boolean }) {
  return (
    <div className={`flex flex-col gap-1 ${compact ? 'opacity-70' : ''}`}>
      {tools.slice(0, count).map((tool, i) => {
        const verify = i === tools.length - 1
        return (
          <span key={tool} className={`inline-flex w-fit animate-rise items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[11px] ${
            verify ? 'bg-kb-pine text-kb-paper' : 'bg-kb-ink/[.06] text-kb-ink/75'}`}>
            {verify ? <ShieldCheck className="h-3 w-3 text-kb-gold" aria-hidden="true" /> : <span className="text-kb-brick">›</span>}
            {tool}
          </span>
        )
      })}
    </div>
  )
}

function RidgeMark({ light }: { light?: boolean }) {
  return (
    <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true" className="shrink-0">
      <rect width="34" height="34" rx="10" fill={light ? '#F5F0E6' : '#14231F'} />
      <path d="M5 25 L13 13 L18 19 L22 14 L29 25 Z" fill="#C99A3C" />
      <path d="M13 13 L15.5 16.6 L11.2 16.6 Z M22 14 L24 17 L20.3 17 Z" fill={light ? '#14231F' : '#F5F0E6'} />
    </svg>
  )
}

function Ridge({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 1440 60" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 60 V38 L110 18 L190 32 L300 6 L380 28 L470 14 L560 34 L660 2 L760 26 L850 16 L960 36 L1060 10 L1150 30 L1250 18 L1350 34 L1440 20 V60 Z" fill="currentColor" />
    </svg>
  )
}

function StripItem({ icon, title }: { icon: React.ReactNode; title: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 text-kb-ink/80">
      <span className="flex h-10 w-auto min-w-10 items-center justify-center rounded-xl bg-kb-paper2 px-2.5 text-kb-pine">{icon}</span>
      <span className="font-semibold">{title}</span>
    </div>
  )
}

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-bold uppercase tracking-[.22em] text-kb-brick">{eyebrow}</p>
      <h2 className="mt-4 font-display text-[clamp(30px,4vw,46px)] font-semibold leading-[1.08] tracking-[-.02em]">{title}</h2>
      {sub && <p className="mt-4 text-lg text-kb-muted">{sub}</p>}
    </div>
  )
}

function VerticalCard({ icon, tone, image, title, body, bullets, link }: {
  icon: React.ReactNode; tone: 'pine' | 'brick'; image: string; title: string; body: string; bullets: string[]
  link: { href: string; label: string; external?: boolean }
}) {
  const accent = tone === 'pine' ? 'bg-kb-pine' : 'bg-kb-brick'
  const linkCls = `mt-7 inline-flex items-center gap-2 font-semibold ${tone === 'pine' ? 'text-kb-pine' : 'text-kb-brick'} group-hover:gap-3 transition-all`
  const inner = (
    <>
      <div className="relative h-52 overflow-hidden">
        <img src={image} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.04]" />
        <span className={`absolute left-5 top-5 flex h-12 w-12 items-center justify-center rounded-2xl ${accent} text-kb-paper shadow-lg`}>{icon}</span>
      </div>
      <div className="p-7">
        <h3 className="font-display text-[28px] font-semibold tracking-[-.01em]">{title}</h3>
        <p className="mt-2 text-[15.5px] leading-relaxed text-kb-muted">{body}</p>
        <ul className="mt-6 space-y-3">
          {bullets.map((b, i) => (
            <li key={i} className="flex gap-3 text-[15px]"><Check className="mt-0.5 h-5 w-5 shrink-0 text-kb-pine" aria-hidden="true" />{b}</li>
          ))}
        </ul>
        <span className={linkCls}>{link.label}<ArrowRight className="h-4 w-4" aria-hidden="true" /></span>
      </div>
    </>
  )
  const cls = 'group overflow-hidden rounded-[24px] border border-kb-line bg-kb-card shadow-[0_1px_2px_rgba(20,35,31,.06),0_8px_24px_-12px_rgba(20,35,31,.18)] transition-transform hover:-translate-y-1'
  return link.external
    ? <a href={link.href} className={cls}>{inner}</a>
    : <Link to={link.href} className={cls}>{inner}</Link>
}

function PriceCard({ name, desc, price, per, features, cta, featured, badge }: {
  name: string; desc: string; price: string; per?: string; features: string[]; cta: string; featured?: boolean; badge?: string
}) {
  return (
    <div className={`relative flex flex-col rounded-[24px] p-8 ${featured
      ? 'bg-kb-ink text-kb-paper shadow-[0_30px_60px_-30px_rgba(20,35,31,.8)]'
      : 'border border-kb-line bg-kb-card'}`}>
      {featured && badge && <span className="absolute -top-3 left-8 rounded-full bg-kb-gold px-3 py-1 text-xs font-bold text-kb-ink">{badge}</span>}
      <h3 className="text-lg font-semibold">{name}</h3>
      <p className={`mt-1 text-sm ${featured ? 'text-kb-paper/70' : 'text-kb-muted'}`}>{desc}</p>
      <p className="mt-6 flex items-baseline gap-1"><span className="font-display text-5xl font-semibold">{price}</span>{per && <span className={featured ? 'text-kb-paper/60' : 'text-kb-muted'}>{per}</span>}</p>
      <ul className="mt-7 flex-1 space-y-3 text-[15px]">
        {features.map((f, i) => (
          <li key={i} className="flex gap-2.5"><Check className={`mt-0.5 h-5 w-5 shrink-0 ${featured ? 'text-kb-gold' : 'text-kb-pine'}`} aria-hidden="true" />{f}</li>
        ))}
      </ul>
      <Link to="/register" className={`mt-8 rounded-full py-3.5 text-center font-semibold transition-colors ${featured
        ? 'bg-kb-paper text-kb-ink hover:bg-white' : 'bg-kb-ink text-kb-paper hover:bg-kb-pine'}`}>{cta}</Link>
    </div>
  )
}

function FooterCol({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-bold uppercase tracking-[.18em] text-kb-brick">{title}</h4>
      <ul className="mt-4 space-y-3 text-[15px] text-kb-ink/80">{children}</ul>
    </div>
  )
}
