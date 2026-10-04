# Kribaat brand memory

The single source of truth for how Kribaat looks, sounds and moves: the web app landing page
(`frontend/src/pages/LandingPage.tsx`), the public property site (`backend/apps/realestate/templates/realestate/public/`),
the chat widget, social posts and every launch / feature video (Higgsfield). If something here changes,
change it here first, then in code.

## Who we are

**Kribaat** is an agentic AI platform from Kathmandu, Nepal. Businesses (real estate agencies and restaurants
today) connect WhatsApp, Instagram and their website; an AI agent answers customers in Nepali (Devanagari and
Romanized), English and Chinese, looks everything up in the business's own data, verifies every fact before
it is sent, books viewings and tables with a real confirmation code, and hands the chat to a person when unsure.

- **Promise:** "An AI agent that never makes things up."
- **Proof points (true, shippable claims only):** every price, reference and booking code is checked against the
  business's records before it is sent; bookings need the customer's "yes" and return a receipt; replies come in
  the customer's own language and script; staff can take over any chat; reminders and follow-ups are automatic.
- **Origin line:** "Built in Kathmandu. Works anywhere."
- **Never claim:** guaranteed sales, "100% accuracy", "human-level", fake customer counts, fake testimonials,
  awards we did not win.

## Logo

- **Mark:** a rounded square in Ink with a two-peak Himalayan ridge in Gold and paper-white snow caps
  (the same SVG used in the property site header). Minimum size 24 px. Clear space = the height of one peak.
- **Wordmark:** "Kribaat" set in Fraunces 700, tracking -1%. Never all caps, never gradient-filled.
- **Lockup:** mark + wordmark, gap = 0.3 × mark height. A sub-label (e.g. "Realestate", "Nepal property") sits
  under the wordmark in Hanken Grotesk 600, 10 px, letter-spacing 0.18em, uppercase, Brick.

## Colour

| Token | Hex | Use |
|---|---|---|
| Paper | `#F5F0E6` | Page background (light surfaces) |
| Paper 2 | `#EDE4D3` | Sunken areas, chips, placeholders |
| Card | `#FFFDF8` | Cards, forms, chat bubbles on paper |
| Ink | `#14231F` | Primary text, dark sections, primary buttons |
| Pine | `#1F4D3F` | Brand green: links, focus, "verified" states, rent badges |
| Pine 2 | `#2E6A57` | Hover, ridges, secondary illustration |
| Brick | `#B4532A` | Eyebrows, sale badges, emphasis, numbers in steps |
| Brick 2 | `#8F3E1D` | Brick hover / pressed |
| Gold | `#C99A3C` | Highlights, italic display words on Ink, the logo ridge, focus ring |
| Muted | `#5F6159` | Secondary text on paper |
| Line | `#DDD2BF` | Borders, dividers |
| WhatsApp | `#128C4A` (hover `#0E7A40`) | Only on buttons that open WhatsApp |

Rules: Paper + Ink carry 80% of any layout; Pine is the brand colour; Brick and Gold are accents (never both as
large fills next to each other). No purple, no neon gradients, no glassmorphism on paper. Dark sections are Ink with
a soft radial glow of Gold (28% alpha) and Pine 2 (55% alpha). Text contrast ≥ 4.5:1 (Muted on Paper passes; Gold
text only on Ink).

## Typography

| Role | Font | Weights | Notes |
|---|---|---|---|
| Display / headings | **Fraunces** (Google Fonts, opsz 9..144) | 400 italic, 600, 700 | Tracking -2%. Emphasis = *italic 400 in Gold (on Ink) or Brick (on Paper)* |
| UI / body | **Hanken Grotesk** | 400, 500, 600, 700 | 16 px / 1.6 body; labels 12 px 700 uppercase +0.1em |
| Nepali | **Noto Sans Devanagari** | 400, 600 | Always for Devanagari; never fake-bold |
| Codes / tool calls | `ui-monospace, SFMono-Regular, Menlo` | 600 | PROP / APT codes, agent tool-call chips |

Google Fonts URL:
`https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=Hanken+Grotesk:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;600&display=swap`

Scale (desktop): H1 clamp(40px, 6vw, 76px) / 1.02 · H2 clamp(28px, 3.6vw, 44px) / 1.1 · H3 20px / 1.3 ·
eyebrow 12px 700 +0.2em uppercase Brick.

## Shape, texture, motion

- Radius: cards 18 px, big panels 28 px, chips 14 px, buttons fully round (999 px).
- Shadow: `0 1px 2px rgba(20,35,31,.06), 0 8px 24px -12px rgba(20,35,31,.18)`; hover lifts 4 px.
- Texture: a 3.5% paper-grain noise over Paper; Himalayan ridge silhouettes divide dark and light sections.
- Motion: one orchestrated entrance per view (rise 14 px + fade, 600-700 ms, cubic-bezier(.2,.7,.2,1),
  60 ms stagger). Chat demos type at a human pace (bubbles 450 ms apart, tool-call chips tick in 250 ms).
  Always honour `prefers-reduced-motion`.

## Voice

- Warm, humble, exact. Show real numbers and real flows, not adjectives.
- In Nepali always honorific (hajur / tapai, -nuhunchha / -nuhola). Never "timi".
- **No em or en dashes in any customer-facing chat text** (house style); use commas, colons or full stops.
- Money is local: "Rs 65,000/month", "Rs 2.1 crore". Codes in monospace: `PROP481475`, `APTK6XSXH`.

## Video and launch system (Higgsfield)

Use for every product launch, feature launch, update and showcase (LinkedIn first, then Instagram/YouTube).

- **Formats:** 16:9 1920×1080 (LinkedIn feed, YouTube), 1:1 1080×1080, 9:16 1080×1920 (Reels/Shorts).
  25-60 s for launches, 15 s for feature drops. Burned-in captions (Hanken Grotesk 600, white on Ink 80%).
- **Recurring character (Soul ID):** one consistent presenter, a Nepali professional in their late 20s, smart casual
  in Pine / Paper tones, filmed in a bright Kathmandu office with Himalayan light. Train once with
  `higgsfield-soul-id`; reuse the same `soul_id` in every video so the brand has a face.
- **Product footage:** real UI captures of the dashboard, the property site and a WhatsApp chat (synthetic demo
  tenant, never real customer data). Cursor: smooth eased moves, 2 px Pine click ripple.
- **Story beats:** (1) a real customer question in Nepali on WhatsApp → (2) the agent's tool calls tick in
  (search, verify) → (3) the verified answer with real price + photos → (4) "Confirm?" → "yes" → receipt with
  booking code → (5) the owner's dashboard updates live → end card.
- **End card:** Ink background, ridge mark, "Kribaat" wordmark, line "An AI agent that never makes things up.",
  URL `kribaat.com`, origin line "Built in Kathmandu. Works anywhere."
- **Lower thirds:** Paper card, 18 px radius, Brick eyebrow + Ink title.
- **Sound:** warm, minimal, light percussion; a soft madal pattern is welcome; no stock "epic" trailers.
- **Never:** fake metrics, fake customer logos, deepfakes of real people, purple neon AI clichés.
