"""
Seed the 12 structured use cases + their high-perfection prompt templates.

Prompt-engineering philosophy — the LATEST structured technique used by leading
generation tools (Seedance 2.0, Higgsfield Popcorn), not dated free-text prompting:

  1. CHANNEL SEPARATION (Higgsfield Popcorn 6-field): the image is described as
     ordered, named control channels — SHOT & SUBJECT · FRAMING & ANGLE ·
     LIGHTING · ENVIRONMENT · LENS / FILM LOOK · MOOD — because the model honours
     locked channels far more reliably than one descriptive paragraph. Brand,
     text, and layout are kept in SEPARATE authoritative blocks (prompt_builder
     appends the brand block) so they never "fight inside one block."
  2. CINEMATOGRAPHIC LANGUAGE, NOT NARRATIVE: each channel uses precise craft
     directives (e.g. "50mm, eye-level, slow push-in") instead of vague words
     like "cinematic" or "dynamic", which force the model to guess.
  3. AFFIRMATIVE-FIRST (Seedance): say what TO render; a short AVOID line carries
     the few true prohibitions. Front-load the most important channel — the model
     weights early tokens more.
  4. EXPLICIT MATERIAL & TYPOGRAPHY control for food realism and legible on-image
     text (correct spelling, kerning, hierarchy).

These rows are admin-editable afterwards — model IDs stay empty here so they fall
back to settings (config-driven, no hardcoded IDs).
"""
from django.db import migrations


# ── Shared master instruction + quality + negative blocks ───────────────
# The system instruction sets role + non-negotiables in direct, craft language
# (cinematographic, not narrative) per the Higgsfield/Seedance guidance.
MASTER_SYSTEM = (
    "Role: award-winning food & beverage advertising art director and master "
    "retoucher producing one finished, publication-ready marketing image per "
    "request. Read each CHANNEL below as a locked instruction, in order; earlier "
    "channels dominate. Use craft directives literally (focal length, angle, "
    "light direction, grade) — never interpret them loosely. Render on-image text "
    "with correct spelling, tight kerning, and clear hierarchy. Do not invent "
    "logos, watermarks, QR codes, or placeholder text. Output a single cohesive "
    "composition, not a collage."
)

# Affirmative quality channel (specifics, not adjectives).
QUALITY = (
    "QUALITY: tack-sharp hero focus, true-to-life color, high dynamic range, "
    "clean micro-contrast, fine 2% film grain, smooth tonal gradients, "
    "print-ready resolution, edge-to-edge crisp."
)

# Short AVOID lines (affirmative-first → negatives are secondary, per Seedance).
NEG_PHOTO = (
    "garbled or misspelled text, deformed hands, melting or plastic-looking food, "
    "HDR halos, harsh flash, cluttered background, duplicate objects, watermark, "
    "stock logo, blur, low resolution, jpeg artifacts, warped or cut-off letters"
)

NEG_GRAPHIC = (
    "garbled or misspelled text, lorem ipsum, illegible overlapping type, "
    "low-contrast text, pixelated edges, watermark, off-brand colors, "
    "clashing fonts, cluttered layout, jpeg artifacts"
)


def _t(*lines):
    return "\n".join(lines)


# ── 12 use cases: (key, name, icon, credit_cost, required, optional,
#                    formats, prompt_body, negative, system) ─────────────
USE_CASES = [
    {
        "key": "offer_discount_poster",
        "name": "Offer / Discount Poster",
        "icon": "badge-percent",
        "credit_cost": 1,
        "required": [
            {"key": "offer_title", "label": "Offer Title", "type": "text", "max_length": 80},
            {"key": "discount_value", "label": "Discount", "type": "text", "max_length": 40},
        ],
        "optional": [
            {"key": "subheadline", "label": "Subheadline", "type": "text", "max_length": 120},
            {"key": "valid_until", "label": "Valid Until", "type": "text", "max_length": 60},
            {"key": "hero_dish", "label": "Hero Dish", "type": "text", "max_length": 80},
        ],
        "formats": ["square", "portrait", "landscape"],
        "body": _t(
            "SHOT & SUBJECT: advertising poster; the discount \"{{discount_value}}\" is the single "
            "dominant focal element; headline \"{{offer_title}}\"; optional appetizing hero dish: {{hero_dish}}.",
            "FRAMING & ANGLE: centered hero hierarchy, discount largest, then headline, then "
            "\"{{subheadline}}\" and \"{{valid_until}}\" smallest; rule-of-thirds anchor, generous margins.",
            "LIGHTING: soft directional key, gentle rim light separating subject from background.",
            "ENVIRONMENT: clean uncluttered backdrop with deliberate negative space for text.",
            "LENS / FILM LOOK: 50mm, shallow depth of field on any food, crisp foreground.",
            "TYPOGRAPHY: bold modern sans-serif, tiered hierarchy, tight kerning, legible at thumbnail size.",
            "MOOD: confident, premium, act-now.",
            QUALITY,
            f"AVOID: {NEG_GRAPHIC}.",
        ),
        "negative": NEG_GRAPHIC,
    },
    {
        "key": "dish_highlight_post",
        "name": "Dish Highlight Post",
        "icon": "utensils",
        "credit_cost": 1,
        "required": [
            {"key": "dish_name", "label": "Dish Name", "type": "text", "max_length": 80},
        ],
        "optional": [
            {"key": "key_ingredients", "label": "Key Ingredients", "type": "text", "max_length": 160},
            {"key": "plating_style", "label": "Plating Style", "type": "select",
             "choices": ["fine-dining", "rustic", "street-food", "homestyle"]},
            {"key": "uploaded_photo", "label": "Dish Photo (optional)", "type": "image_upload", "optional": True},
        ],
        "formats": ["square", "portrait"],
        "body": _t(
            "SHOT & SUBJECT: hero food photograph of \"{{dish_name}}\" featuring {{key_ingredients}}, "
            "styled {{plating_style}}; dish fills 60-70% of frame.",
            "FRAMING & ANGLE: 45-degree hero angle, intentional props and garnish, clean tabletop, "
            "deliberate negative space.",
            "LIGHTING: soft window-style side light with subtle fill; glistening speculars on sauces "
            "and fresh produce to read as fresh.",
            "ENVIRONMENT: shallow, softly defocused background that supports the dish.",
            "LENS / FILM LOOK: 90mm macro, f/2.8 shallow depth of field, tack-sharp on the dish, creamy bokeh.",
            "MATERIAL & TEXTURE: physically accurate steam, sear marks, juiciness, crisp edges, fresh herbs.",
            "MOOD: crave-worthy, fresh, premium — natural warm grade, true food color, no neon push.",
            QUALITY,
            f"AVOID: {NEG_PHOTO}.",
        ),
        "negative": NEG_PHOTO,
    },
    {
        "key": "buffet_promo",
        "name": "Buffet Promo",
        "icon": "concierge-bell",
        "credit_cost": 1,
        "required": [
            {"key": "buffet_name", "label": "Buffet Name", "type": "text", "max_length": 80},
            {"key": "price", "label": "Price", "type": "text", "max_length": 40},
        ],
        "optional": [
            {"key": "highlights", "label": "Spread Highlights", "type": "textarea", "max_length": 200},
            {"key": "session_time", "label": "Session Time", "type": "text", "max_length": 60},
        ],
        "formats": ["square", "portrait", "landscape"],
        "body": _t(
            "SHOT & SUBJECT: abundant buffet spread for \"{{buffet_name}}\" at \"{{price}}\", "
            "showcasing {{highlights}}; session {{session_time}}.",
            "FRAMING & ANGLE: wide overhead-to-three-quarter table laid with many dishes, layered depth, "
            "leading lines into the spread; price as a confident badge.",
            "LIGHTING: warm, plentiful, even ambient light evoking a celebratory feast.",
            "ENVIRONMENT: inviting dining setting, tasteful tableware, no clutter.",
            "LENS / FILM LOOK: 35mm wide for abundance, deep-ish focus so multiple dishes read clearly.",
            "MATERIAL & TEXTURE: varied dishes with accurate steam, gloss, and freshness cues.",
            "TYPOGRAPHY: clear price callout, legible buffet name, organized hierarchy.",
            "MOOD: generous, indulgent, value-packed — rich warm festive grade, natural saturation.",
            QUALITY,
            f"AVOID: {NEG_PHOTO}.",
        ),
        "negative": NEG_PHOTO,
    },
    {
        "key": "daily_special",
        "name": "Daily Special",
        "icon": "calendar-star",
        "credit_cost": 1,
        "required": [
            {"key": "special_name", "label": "Special Name", "type": "text", "max_length": 80},
            {"key": "day", "label": "Day", "type": "text", "max_length": 40},
        ],
        "optional": [
            {"key": "price", "label": "Price", "type": "text", "max_length": 40},
            {"key": "description", "label": "Description", "type": "textarea", "max_length": 160},
        ],
        "formats": ["square", "portrait"],
        "body": _t(
            "SHOT & SUBJECT: daily-special announcement for \"{{special_name}}\" on {{day}} ({{price}}); "
            "described as {{description}}; appetizing dish hero.",
            "FRAMING & ANGLE: dish hero with a clean banner zone reserved for the day + price; balanced.",
            "LIGHTING: soft natural daylight, fresh and inviting.",
            "ENVIRONMENT: bright, uncluttered tabletop.",
            "LENS / FILM LOOK: 50mm, shallow depth of field on the dish.",
            "TYPOGRAPHY: prominent day-of-week tag, readable special name and price.",
            "MOOD: fresh, friendly, a reason to visit today — bright true-to-life grade.",
            QUALITY,
            f"AVOID: {NEG_PHOTO}.",
        ),
        "negative": NEG_PHOTO,
    },
    {
        "key": "festival_holiday_post",
        "name": "Festival / Holiday Post",
        "icon": "party-popper",
        "credit_cost": 1,
        "required": [
            {"key": "occasion", "label": "Occasion", "type": "text", "max_length": 60},
            {"key": "greeting", "label": "Greeting Message", "type": "text", "max_length": 120},
        ],
        "optional": [
            {"key": "featured_item", "label": "Featured Item", "type": "text", "max_length": 80},
        ],
        "formats": ["square", "portrait"],
        "body": _t(
            "SHOT & SUBJECT: festive {{occasion}} greeting-card post; central message \"{{greeting}}\"; "
            "optionally featuring {{featured_item}}.",
            "FRAMING & ANGLE: culturally-appropriate festive motifs framing a clear central greeting; tasteful.",
            "LIGHTING: warm celebratory glow, soft highlights.",
            "ENVIRONMENT: elegant themed backdrop, uncluttered.",
            "LENS / FILM LOOK: refined photoreal or tasteful illustrative hero per style preference.",
            "TYPOGRAPHY: elegant greeting as the focal text, clean hierarchy.",
            "MOOD: warm, celebratory, heartfelt — occasion-appropriate harmonious palette.",
            QUALITY,
            f"AVOID: {NEG_GRAPHIC}.",
        ),
        "negative": NEG_GRAPHIC,
    },
    {
        "key": "happy_hour_drinks_promo",
        "name": "Happy Hour / Drinks Promo",
        "icon": "martini",
        "credit_cost": 1,
        "required": [
            {"key": "promo_title", "label": "Promo Title", "type": "text", "max_length": 80},
            {"key": "time_window", "label": "Time Window", "type": "text", "max_length": 60},
        ],
        "optional": [
            {"key": "featured_drinks", "label": "Featured Drinks", "type": "text", "max_length": 160},
            {"key": "deal", "label": "Deal", "type": "text", "max_length": 80},
        ],
        "formats": ["square", "portrait", "landscape"],
        "body": _t(
            "SHOT & SUBJECT: happy-hour promo \"{{promo_title}}\" for {{time_window}}, hero drinks "
            "{{featured_drinks}}; deal {{deal}} rendered prominently.",
            "FRAMING & ANGLE: hero cocktails/drinks with garnish foreground, moody bar backdrop behind.",
            "LIGHTING: dramatic low-key bar lighting, colorful rim accents, backlit liquid glow.",
            "ENVIRONMENT: defocused nightlife bar with warm bokeh practical lights.",
            "LENS / FILM LOOK: 85mm, f/2.0, glistening glassware tack-sharp, creamy bokeh behind.",
            "MATERIAL & TEXTURE: condensation droplets, ice clarity, citrus zest, fizzing bubbles.",
            "MOOD: lively, social, after-work unwind — rich saturated accents on the drinks.",
            QUALITY,
            f"AVOID: {NEG_PHOTO}.",
        ),
        "negative": NEG_PHOTO,
    },
    {
        "key": "new_menu_launch",
        "name": "New Menu Launch",
        "icon": "sparkles",
        "credit_cost": 1,
        "required": [
            {"key": "menu_name", "label": "Menu / Item Name", "type": "text", "max_length": 80},
        ],
        "optional": [
            {"key": "tagline", "label": "Tagline", "type": "text", "max_length": 120},
            {"key": "launch_date", "label": "Launch Date", "type": "text", "max_length": 60},
        ],
        "formats": ["square", "portrait", "landscape"],
        "body": _t(
            "SHOT & SUBJECT: premium 'new on the menu' announcement for \"{{menu_name}}\", "
            "tagline \"{{tagline}}\", launching {{launch_date}}; elegant hero presentation with a 'NEW' accent.",
            "FRAMING & ANGLE: editorial, aspirational product-shot framing, generous negative space.",
            "LIGHTING: clean studio softbox, controlled speculars, premium finish.",
            "ENVIRONMENT: minimal upscale surface, refined props.",
            "LENS / FILM LOOK: 100mm, shallow depth of field, crisp product detail.",
            "MATERIAL & TEXTURE: hero item rendered with accurate, appetizing texture.",
            "TYPOGRAPHY: refined headline, tasteful 'NEW' badge, clear date callout.",
            "MOOD: exciting, premium, must-try — sophisticated restrained grade.",
            QUALITY,
            f"AVOID: {NEG_PHOTO}.",
        ),
        "negative": NEG_PHOTO,
    },
    {
        "key": "review_testimonial_graphic",
        "name": "Review / Testimonial Graphic",
        "icon": "quote",
        "credit_cost": 1,
        "required": [
            {"key": "review_text", "label": "Review Text", "type": "textarea", "max_length": 280},
            {"key": "reviewer_name", "label": "Reviewer Name", "type": "text", "max_length": 80},
            {"key": "permission_confirmed", "label":
                "I confirm this review is genuine and I have the customer's permission to use it publicly.",
                "type": "checkbox"},
        ],
        "optional": [
            {"key": "rating", "label": "Star Rating", "type": "select",
             "choices": ["5", "4", "3"]},
        ],
        "formats": ["square", "portrait"],
        "body": _t(
            "SHOT & SUBJECT: clean customer-testimonial graphic; hero quote \"{{review_text}}\" "
            "attributed to {{reviewer_name}}; {{rating}}-star rating rendered clearly.",
            "FRAMING & ANGLE: flat graphic composition (not a photo), large readable quotation as hero, "
            "attribution beneath, generous whitespace.",
            "LIGHTING: even, neutral.",
            "ENVIRONMENT: calm on-brand background, high text-contrast.",
            "LENS / FILM LOOK: crisp vector-clean rendering.",
            "TYPOGRAPHY: elegant quotation typography, clear quote marks, precise star icons, "
            "impeccable spelling and kerning.",
            "MOOD: credible, warm, reassuring.",
            QUALITY,
            f"AVOID: {NEG_GRAPHIC}.",
        ),
        "negative": NEG_GRAPHIC,
    },
    {
        "key": "lucky_draw_qr_poster",
        "name": "Lucky Draw QR Poster",
        "icon": "gift",
        "credit_cost": 1,
        "required": [
            {"key": "campaign_title", "label": "Campaign Title", "type": "text", "max_length": 80},
            {"key": "prize_line", "label": "Prize Line", "type": "text", "max_length": 100},
        ],
        "optional": [
            {"key": "instructions", "label": "How to Enter", "type": "text", "max_length": 120},
        ],
        "formats": ["portrait"],
        "body": _t(
            "SHOT & SUBJECT: eye-catching lucky-draw poster titled \"{{campaign_title}}\" promoting "
            "\"{{prize_line}}\"; entry instructions {{instructions}}.",
            "FRAMING & ANGLE: 'Scan to win!' hero headline top, prize line mid, and a prominent EMPTY "
            "high-contrast square placeholder centered-lower for the QR code.",
            "LIGHTING: bright, energetic.",
            "ENVIRONMENT: celebratory high-contrast backdrop, uncluttered.",
            "LENS / FILM LOOK: bold flat graphic poster rendering.",
            "TYPOGRAPHY: punchy 'Scan to win' headline, readable prize and instructions.",
            "MOOD: fun, rewarding, urgent.",
            QUALITY,
            "HARD CONSTRAINT: leave a clean, unobstructed white square area for the QR code; "
            "do NOT draw, fabricate, or scribble any QR pixels — it is added in post.",
            f"AVOID: {NEG_GRAPHIC}, fake QR code, scribbled QR pattern.",
        ),
        "negative": NEG_GRAPHIC + ", fake QR code, scribbled QR pattern",
    },
    {
        "key": "wifi_signin_poster",
        "name": "WiFi Sign-In Poster",
        "icon": "wifi",
        "credit_cost": 1,
        "required": [
            {"key": "network_name", "label": "WiFi Network Name", "type": "text", "max_length": 80},
        ],
        "optional": [
            {"key": "instructions", "label": "Instructions", "type": "text", "max_length": 120},
        ],
        "formats": ["portrait"],
        "body": _t(
            "SHOT & SUBJECT: tidy in-store 'Free WiFi' poster for network \"{{network_name}}\"; "
            "instructions {{instructions}}.",
            "FRAMING & ANGLE: friendly 'Free WiFi' headline, network name, clear numbered steps, and a "
            "clean EMPTY square placeholder for the sign-in QR code.",
            "LIGHTING: bright, welcoming.",
            "ENVIRONMENT: calm on-brand backdrop, high legibility.",
            "LENS / FILM LOOK: clean flat graphic poster rendering.",
            "TYPOGRAPHY: clear WiFi glyph, readable steps, obvious QR zone.",
            "MOOD: welcoming, convenient.",
            QUALITY,
            "HARD CONSTRAINT: leave a clean white square area for the QR code; do NOT draw or "
            "fabricate QR pixels — it is added in post.",
            f"AVOID: {NEG_GRAPHIC}, fake QR code, scribbled QR pattern.",
        ),
        "negative": NEG_GRAPHIC + ", fake QR code, scribbled QR pattern",
    },
    {
        "key": "event_poster",
        "name": "Event Poster",
        "icon": "ticket",
        "credit_cost": 1,
        "required": [
            {"key": "event_name", "label": "Event Name", "type": "text", "max_length": 80},
            {"key": "event_date", "label": "Date & Time", "type": "text", "max_length": 80},
        ],
        "optional": [
            {"key": "details", "label": "Details", "type": "textarea", "max_length": 200},
        ],
        "formats": ["square", "portrait"],
        "body": _t(
            "SHOT & SUBJECT: striking event poster for \"{{event_name}}\" on {{event_date}}; "
            "details {{details}}; bold event title as hero.",
            "FRAMING & ANGLE: title dominant, date/time prominent second, supporting details organized.",
            "LIGHTING: dramatic, themed to the event mood.",
            "ENVIRONMENT: atmospheric themed backdrop matching the event.",
            "LENS / FILM LOOK: cinematic 35mm poster framing, controlled depth.",
            "TYPOGRAPHY: poster-grade title typography, clear date hierarchy, legible details.",
            "MOOD: exciting, can't-miss — cohesive high-impact grade.",
            QUALITY,
            f"AVOID: {NEG_GRAPHIC}.",
        ),
        "negative": NEG_GRAPHIC,
    },
    {
        "key": "campaign_pack",
        "name": "Campaign Pack (4 images)",
        "icon": "layers",
        "credit_cost": 4,
        "required": [
            {"key": "campaign_theme", "label": "Campaign Theme", "type": "text", "max_length": 100},
            {"key": "core_message", "label": "Core Message", "type": "text", "max_length": 160},
        ],
        "optional": [
            {"key": "hero_item", "label": "Hero Item", "type": "text", "max_length": 80},
        ],
        "formats": ["square", "portrait", "landscape"],
        "body": _t(
            "SHOT & SUBJECT: cohesive marketing visual for campaign theme \"{{campaign_theme}}\" "
            "carrying core message \"{{core_message}}\", optionally featuring {{hero_item}}.",
            "FRAMING & ANGLE: flexible hero composition that holds as social square, story portrait, and "
            "banner; repeatable layout grammar with intentional negative space for text overlays.",
            "LIGHTING: one signature lighting setup applied consistently across the set.",
            "ENVIRONMENT: consistent branded backdrop system.",
            "LENS / FILM LOOK: premium product/food framing, controlled depth, identical look across frames.",
            "MATERIAL & TEXTURE: hero item rendered with accurate appetizing texture.",
            "TYPOGRAPHY: one type system, consistent placement, message legible at every size.",
            "MOOD: a unified, recognizable brand campaign — a single cohesive grade across the pack.",
            QUALITY,
            f"AVOID: {NEG_PHOTO}.",
        ),
        "negative": NEG_PHOTO,
    },
]


def seed(apps, schema_editor):
    ContentUseCase = apps.get_model('content_studio', 'ContentUseCase')
    ContentPromptTemplate = apps.get_model('content_studio', 'ContentPromptTemplate')

    for order, spec in enumerate(USE_CASES):
        uc, _ = ContentUseCase.objects.update_or_create(
            use_case_key=spec['key'],
            defaults={
                'display_name': spec['name'],
                'icon': spec['icon'],
                'credit_cost': spec['credit_cost'],
                'required_fields': spec['required'],
                'optional_fields': spec['optional'],
                'supported_formats': spec['formats'],
                'active': True,
                'sort_order': order,
            },
        )
        ContentPromptTemplate.objects.update_or_create(
            use_case=uc,
            defaults={
                'prompt_template': spec['body'],
                'negative_prompt': spec['negative'],
                'system_instructions': MASTER_SYSTEM,
                'provider': '',   # fall back to settings (config-driven)
                'model': '',
                'version': 1,
            },
        )


def unseed(apps, schema_editor):
    ContentUseCase = apps.get_model('content_studio', 'ContentUseCase')
    ContentUseCase.objects.filter(
        use_case_key__in=[s['key'] for s in USE_CASES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('content_studio', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(seed, unseed),
    ]
