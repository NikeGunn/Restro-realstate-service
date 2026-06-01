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


def _load_font(size, bold=False):
    """Best-effort font load; falls back to PIL's default bitmap font."""
    candidates = [
        'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold
        else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _max_discount(campaign):
    pcts = [p.discount_percent for p in campaign.prizes.filter(active=True)]
    return int(max(pcts)) if pcts else 0


def generate_poster(campaign, qr_code, brand_color=(99, 102, 241)):
    """
    Build a 1200×1800 PNG poster: campaign name, the headline win line, the QR,
    a CTA, and a terms footer. zh-TW copy unless the campaign default differs.
    Returns PNG bytes.
    """
    if Image is None:
        raise RuntimeError("Pillow is not installed")

    W, H = 1200, 1800
    lang = campaign.default_language if campaign.default_language in _POSTER_COPY else 'zh-TW'
    copy = _POSTER_COPY[lang]
    pct = _max_discount(campaign)

    img = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(img)

    # Top brand band.
    draw.rectangle([0, 0, W, 230], fill=brand_color)
    name_font = _load_font(72, bold=True)
    _centered_text(draw, W, 70, campaign.name[:40], name_font, fill='white')

    # Headline win line.
    win_font = _load_font(58, bold=True)
    _centered_text(draw, W, 320, copy['win'].format(pct=pct), win_font, fill=(17, 24, 39))

    # QR in the centre.
    qr_bytes = generate_qr_image(get_campaign_entry_url(qr_code), box_size=14, border=2)
    qr_img = Image.open(io.BytesIO(qr_bytes)).convert('RGB')
    qr_size = 720
    qr_img = qr_img.resize((qr_size, qr_size))
    img.paste(qr_img, ((W - qr_size) // 2, 470))

    # CTA + terms.
    cta_font = _load_font(54, bold=True)
    _centered_text(draw, W, 1260, copy['cta'], cta_font, fill=brand_color)
    terms_font = _load_font(34)
    _centered_text(draw, W, 1680, copy['terms'], terms_font, fill=(107, 114, 128))

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _centered_text(draw, width, y, text, font, fill):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * 20
    draw.text(((width - tw) / 2, y), text, font=font, fill=fill)
