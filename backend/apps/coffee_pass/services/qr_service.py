"""
Coffee Pass QR + counter-card generation.

An owner needs a QR they can print and stand on the table — the guide's §4 Step 5
previously told them to paste the link into "any generator", which is the one
manual step in an otherwise self-serve setup.

get_plan_entry_url -> the public URL a plan's QR resolves to.
generate_qr_image  -> raw PNG bytes of that QR (plain, for stickers/receipts).
generate_poster    -> a 1200x1800 printable counter card with the QR embedded.

Mirrors `apps.lucky_draw.services.qr_service` deliberately: that generator is
proven in production (fonts, CJK fallback, emoji stripping). This module differs
only in copy and palette — Coffee Pass is a calm cafe card, not a neon lucky
draw — so the two are intentionally NOT merged behind a shared abstraction.
Same-shaped code answering a different question (AHA over DRY).

Both entry points return BYTES and never touch the database or storage; the
caller decides whether to persist. That keeps this module import-safe and makes
it trivially testable without a media root.
"""
import io
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:  # pragma: no cover - qrcode is in requirements
    qrcode = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - Pillow is in requirements
    Image = ImageDraw = ImageFont = None


class QRGenerationError(RuntimeError):
    """Raised when an image cannot be produced (missing lib, bad input)."""


def get_public_base_url():
    """Public origin the QR codes resolve against (configmap-driven)."""
    return getattr(settings, 'PUBLIC_BASE_URL', '') or 'https://kribaat.com'


def get_plan_entry_url(plan):
    """The public customer URL a plan's QR routes to."""
    if not getattr(plan, 'public_token', ''):
        # A plan always gets a token in save(); an empty one means the caller
        # handed us an unsaved instance. Fail loudly rather than minting a QR
        # that resolves to a 404 after it has been printed and glued to a table.
        raise QRGenerationError('Plan has no public_token; save the plan first.')
    return f"{get_public_base_url().rstrip('/')}/public/coffee-pass/{plan.public_token}/"


def generate_qr_image(url, box_size=12, border=4):
    """Return PNG bytes for a QR code encoding `url`."""
    if qrcode is None:
        raise QRGenerationError('qrcode library is not installed')
    qr = qrcode.QRCode(
        version=None,
        # M tolerates ~15% damage — a counter card gets coffee spilled on it.
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


#: Counter-card copy per language (zh-TW is the HK default).
_CARD_COPY = {
    'zh-TW': {
        'eyebrow': '咖啡通行證',
        'headline': '會員可享 {pct}% 折扣',
        'sub': '{days} 天 · 適用於本店咖啡',
        'cta': '掃描即可開始',
        'terms': '掃描了解詳情及條款',
    },
    'zh-CN': {
        'eyebrow': '咖啡通行证',
        'headline': '会员可享 {pct}% 折扣',
        'sub': '{days} 天 · 适用于本店咖啡',
        'cta': '扫描即可开始',
        'terms': '扫描了解详情及条款',
    },
    'en': {
        'eyebrow': 'COFFEE PASS',
        'headline': '{pct}% off your coffee',
        'sub': '{days} days · at this cafe',
        'cta': 'Scan to get started',
        'terms': 'Scan for full details and terms',
    },
}

#: CJK-capable fonts first (so zh-TW cards don't render tofu), then DejaVu for
#: Latin, then PIL's bitmap default. Noto CJK ships in Dockerfile.prod.
_CJK_FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
]
_LATIN_FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf',
]


def _load_font(size):
    """Best-effort font load; never raises, so a poster always renders."""
    for path in _CJK_FONT_CANDIDATES + _LATIN_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _strip_emoji(text):
    """
    Drop emoji / pictographs. Noto CJK carries no colour-emoji glyphs, so an
    emoji in a plan or cafe name (e.g. 'Bagaicha ☕') renders as a tofu box.
    CJK and Latin text are kept; only symbol ranges are removed.
    """
    if not text:
        return ''
    out = []
    for ch in text:
        cp = ord(ch)
        is_emoji = (
            0x1F000 <= cp <= 0x1FAFF      # pictographs, emoji, symbols
            or 0x2600 <= cp <= 0x27BF     # misc symbols + dingbats
            or 0x2190 <= cp <= 0x21FF     # arrows
            or 0xFE00 <= cp <= 0xFE0F     # variation selectors
            or cp in (0x20E3, 0x2B50, 0x2B55)
        )
        if not is_emoji:
            out.append(ch)
    return ''.join(out).strip()


#: Warm cafe palette — espresso browns and cream, not the lucky-draw neon.
_CREAM = (247, 241, 232)
_ESPRESSO = (46, 30, 22)
_CARAMEL = (176, 122, 66)
_MUTED = (124, 106, 92)


def _vertical_gradient(size, top, bottom):
    """A top-to-bottom RGB gradient image (cheap, no numpy)."""
    w, h = size
    base = Image.new('RGB', (1, h))
    px = base.load()
    for y in range(h):
        f = y / max(h - 1, 1)
        px[0, y] = (
            int(top[0] + (bottom[0] - top[0]) * f),
            int(top[1] + (bottom[1] - top[1]) * f),
            int(top[2] + (bottom[2] - top[2]) * f),
        )
    return base.resize((w, h))


def _fit_text(draw, text, font_loader, max_width, start_size, min_size=22):
    """
    Shrink a font until the text fits `max_width`.

    A cafe called "Bagaicha Restaurant & Bar" and one called a 60-character
    legal entity name must both produce a printable card, so the card adapts
    rather than letting long text run off the edge.
    """
    size = start_size
    while size > min_size:
        font = font_loader(size)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return font
        except Exception:
            return font
        size -= 2
    return font_loader(min_size)


def _centered_text(draw, width, y, text, font, fill):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * 20
    draw.text(((width - tw) / 2, y), text, font=font, fill=fill)


def generate_poster(plan, language='zh-TW'):
    """
    Build a 1200x1800 PNG counter card: cafe name, the discount, the QR, and a
    scan CTA. Returns PNG bytes. Never raises for cosmetic reasons — only a
    genuinely missing imaging library or an unsaved plan is fatal.
    """
    if Image is None:
        raise QRGenerationError('Pillow is not installed')

    # Resolve the URL FIRST: if the plan has no token there is no point drawing.
    entry_url = get_plan_entry_url(plan)

    W, H = 1200, 1800
    lang = language if language in _CARD_COPY else 'zh-TW'
    copy = _CARD_COPY[lang]
    pct = int(plan.discount_percent) if plan.discount_percent is not None else 0
    days = plan.duration_days or 30

    img = _vertical_gradient((W, H), _CREAM, (235, 224, 209)).convert('RGBA')
    draw = ImageDraw.Draw(img)

    # Card border.
    draw.rounded_rectangle([28, 28, W - 28, H - 28], radius=42,
                           outline=_CARAMEL + (200,), width=5)

    # Decorative cup mark (drawn, not an emoji — emoji render as tofu).
    cx, cy = W // 2, 150
    draw.rounded_rectangle([cx - 52, cy - 34, cx + 34, cy + 46], radius=16,
                           outline=_ESPRESSO + (255,), width=7)
    draw.arc([cx + 22, cy - 16, cx + 78, cy + 28], start=-70, end=70,
             fill=_ESPRESSO + (255,), width=7)
    for dx in (-26, 0, 26):
        draw.arc([cx + dx - 12, cy - 92, cx + dx + 12, cy - 52],
                 start=200, end=340, fill=_MUTED + (255,), width=5)

    # Organization + location.
    org_name = _strip_emoji(getattr(plan.organization, 'name', ''))[:40]
    org_font = _fit_text(draw, org_name, _load_font, W - 260, 46)
    _centered_text(draw, W, 250, org_name, org_font, fill=_ESPRESSO)

    loc_name = _strip_emoji(getattr(plan.location, 'name', ''))[:40]
    if loc_name:
        loc_font = _fit_text(draw, loc_name, _load_font, W - 300, 32)
        _centered_text(draw, W, 312, loc_name, loc_font, fill=_MUTED)

    # Eyebrow.
    eyebrow_font = _load_font(34)
    _centered_text(draw, W, 384, copy['eyebrow'], eyebrow_font, fill=_CARAMEL)

    # Headline discount.
    headline = copy['headline'].format(pct=pct)
    head_font = _fit_text(draw, headline, _load_font, W - 200, 76)
    _centered_text(draw, W, 442, headline, head_font, fill=_ESPRESSO)

    sub = copy['sub'].format(days=days)
    sub_font = _fit_text(draw, sub, _load_font, W - 260, 38)
    _centered_text(draw, W, 546, sub, sub_font, fill=_MUTED)

    # QR on a white card.
    qr_bytes = generate_qr_image(entry_url, box_size=14, border=2)
    qr_img = Image.open(io.BytesIO(qr_bytes)).convert('RGB')
    qr_size = 680
    qr_img = qr_img.resize((qr_size, qr_size))
    qx, qy = (W - qr_size) // 2, 660
    pad = 36
    draw.rounded_rectangle(
        [qx - pad, qy - pad, qx + qr_size + pad, qy + qr_size + pad],
        radius=28, fill=(255, 255, 255, 255), outline=_CARAMEL + (255,), width=6,
    )
    img.paste(qr_img, (qx, qy))

    # CTA pill.
    cta_font = _load_font(48)
    cta_y = 1470
    draw.rounded_rectangle([190, cta_y - 26, W - 190, cta_y + 82], radius=54,
                           fill=_ESPRESSO + (255,))
    _centered_text(draw, W, cta_y, copy['cta'], cta_font, fill=_CREAM)

    # Terms line.
    terms_font = _load_font(28)
    _centered_text(draw, W, 1640, copy['terms'], terms_font, fill=_MUTED)
    _centered_text(draw, W, 1692, 'KRIBAAT', _load_font(26), fill=_CARAMEL)

    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='PNG')
    return buf.getvalue()
