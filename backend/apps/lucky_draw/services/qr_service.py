"""
QR + poster generation (Phase 2).

generate_qr_image  -> raw PNG bytes of the QR pointing at the public entry URL.
get_campaign_entry_url -> the public path a QR resolves to.
generate_poster    -> a 1200×1800 marketing poster (zh-TW copy by default) with
                      the QR embedded, ready to print and stand on a table.

All image bytes go through Django default storage at the call site (the view/
service that persists them), per the Media & Storage cross-cutting rule.
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


def get_public_base_url():
    """Public origin the QR codes resolve against (configmap-driven)."""
    return getattr(settings, 'PUBLIC_BASE_URL', '') or 'https://kribaat.com'


def get_campaign_entry_url(qr_code):
    """The public entry URL a QR routes to: /public/lucky-draw/{url_token}/."""
    return f"{get_public_base_url().rstrip('/')}/public/lucky-draw/{qr_code.url_token}/"


def generate_qr_image(url, box_size=12, border=4):
    """Return PNG bytes for a QR code encoding `url`."""
    if qrcode is None:
        raise RuntimeError("qrcode library is not installed")
    qr = qrcode.QRCode(
        version=None,
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


# Default poster copy per language (zh-TW is the HK default).
_POSTER_COPY = {
    'zh-TW': {'win': '掃描贏取高達 {pct}% 折扣！', 'cta': '立即掃描參加', 'terms': '條款及細則適用'},
    'zh-CN': {'win': '扫描赢取高达 {pct}% 折扣！', 'cta': '立即扫描参加', 'terms': '条款及细则适用'},
    'en':    {'win': 'Scan to win up to {pct}% off!', 'cta': 'Scan now to enter', 'terms': 'Terms & conditions apply'},
}


#: CJK-capable fonts first (so zh-TW/zh-CN posters don't render tofu), then
#: DejaVu for Latin, then PIL's bitmap default. Noto CJK is installed in
#: Dockerfile.prod (fonts-noto-cjk).
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


def _load_font(size, bold=False):
    """
    Best-effort font load. Prefers a CJK-capable font (Noto CJK) so Chinese
    glyphs render on HK posters; falls back to DejaVu, then PIL's bitmap default.
    """
    for path in _CJK_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    for path in _LATIN_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _max_discount(campaign):
    pcts = [p.discount_percent for p in campaign.prizes.filter(active=True)]
    return int(max(pcts)) if pcts else 0


def _strip_emoji(text):
    """
    Drop emoji / pictographs from poster text. Noto CJK has no color-emoji glyphs,
    so an emoji in a campaign name (e.g. '🍤') would render as a tofu box on the
    poster. CJK and Latin text are kept; only the symbol ranges are removed.
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


#: Hong Kong neon-night palette.
_HK_NEON_PINK = (255, 45, 149)
_HK_NEON_CYAN = (0, 229, 255)
_HK_NEON_PURPLE = (168, 85, 247)
_HK_GOLD = (255, 213, 74)


def _vertical_gradient(size, top, bottom):
    """A top→bottom RGB gradient image (cheap, no numpy)."""
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


def _radial_glow(size, center, color, radius, max_alpha=150):
    """An additive radial glow layer (RGBA) centered at `center`."""
    w, h = size
    glow = Image.new('L', size, 0)
    gd = ImageDraw.Draw(glow)
    cx, cy = center
    steps = 36
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        a = int(max_alpha * (1 - i / steps))
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)
    colored = Image.new('RGBA', size, color + (0,))
    colored.putalpha(glow)
    return colored


def generate_poster(campaign, qr_code, brand_color=None):
    """
    Build a 1200×1800 PNG poster with a Hong-Kong neon-night look: dark gradient,
    radial neon glows, a glowing prize headline, a gold-framed QR, and a CTA.
    zh-TW copy unless the campaign default differs. Returns PNG bytes.
    """
    if Image is None:
        raise RuntimeError("Pillow is not installed")

    W, H = 1200, 1800
    lang = campaign.default_language if campaign.default_language in _POSTER_COPY else 'zh-TW'
    copy = _POSTER_COPY[lang]
    pct = _max_discount(campaign)

    # Base dark gradient + neon glows.
    img = _vertical_gradient((W, H), (22, 7, 38), (10, 4, 20)).convert('RGBA')
    img.alpha_composite(_radial_glow((W, H), (180, 120), _HK_NEON_PINK, 900, 130))
    img.alpha_composite(_radial_glow((W, H), (W - 120, 260), _HK_NEON_CYAN, 820, 120))
    img.alpha_composite(_radial_glow((W, H), (W // 2, H - 120), _HK_NEON_PURPLE, 900, 110))
    draw = ImageDraw.Draw(img)

    # Neon border frame.
    for off, col, a in ((26, _HK_NEON_PINK, 200), (34, _HK_NEON_CYAN, 130)):
        draw.rounded_rectangle(
            [off, off, W - off, H - off], radius=44,
            outline=col + (a,), width=4,
        )

    # Decorative "neon ring" mark up top (drawn, not an emoji — emoji render as
    # tofu under Noto CJK which carries no color-emoji glyphs).
    draw.ellipse([W // 2 - 46, 86, W // 2 + 46, 178], outline=_HK_GOLD + (255,), width=8)
    draw.ellipse([W // 2 - 24, 108, W // 2 + 24, 156], outline=_HK_NEON_PINK + (255,), width=6)

    # Organization.
    org_font = _load_font(40, bold=True)
    _centered_text(draw, W, 200, (campaign.organization.name or '')[:28], org_font, fill=_HK_NEON_CYAN)

    # Campaign name (glow via a soft shadow pass; emoji stripped to avoid tofu).
    name_font = _load_font(66, bold=True)
    _glow_text(draw, W, 268, _strip_emoji(campaign.name)[:30], name_font, _HK_NEON_PINK, (255, 255, 255))

    # Headline win line in gold.
    win_font = _load_font(58, bold=True)
    _centered_text(draw, W, 388, copy['win'].format(pct=pct), win_font, fill=_HK_GOLD)

    # Gold-framed QR card.
    qr_bytes = generate_qr_image(get_campaign_entry_url(qr_code), box_size=14, border=2)
    qr_img = Image.open(io.BytesIO(qr_bytes)).convert('RGB')
    qr_size = 700
    qr_img = qr_img.resize((qr_size, qr_size))
    qx, qy = (W - qr_size) // 2, 540
    pad = 34
    draw.rounded_rectangle(
        [qx - pad, qy - pad, qx + qr_size + pad, qy + qr_size + pad],
        radius=30, fill=(255, 255, 255, 255), outline=_HK_GOLD + (255,), width=8,
    )
    img.paste(qr_img, (qx, qy))

    # CTA pill.
    cta_font = _load_font(50, bold=True)
    cy = 1380
    draw.rounded_rectangle([200, cy - 24, W - 200, cy + 84], radius=54,
                           fill=_HK_NEON_PINK + (235,))
    _centered_text(draw, W, cy, copy['cta'], cta_font, fill=(255, 255, 255))

    # Scan hint + terms.
    hint_font = _load_font(34)
    _centered_text(draw, W, 1520, copy['cta'], hint_font, fill=_HK_NEON_CYAN)
    terms_font = _load_font(30)
    _centered_text(draw, W, 1690, copy['terms'] + '   ·   KRIBAAT', terms_font, fill=(148, 163, 184))

    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='PNG')
    return buf.getvalue()


def _glow_text(draw, width, y, text, font, glow_color, fill):
    """Draw centered text with a soft neon halo behind it."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * 20
    x = (width - tw) / 2
    for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)):
        draw.text((x + dx, y + dy), text, font=font, fill=glow_color)
    draw.text((x, y), text, font=font, fill=fill)


def _centered_text(draw, width, y, text, font, fill):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * 20
    draw.text(((width - tw) / 2, y), text, font=font, fill=fill)
