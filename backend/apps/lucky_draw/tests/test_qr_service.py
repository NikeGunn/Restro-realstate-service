"""QR service tests (Phase 2) — entry url, QR PNG bytes, poster PNG bytes."""
import pytest

from apps.lucky_draw.models import LuckyDrawQRCode
from apps.lucky_draw.services import qr_service

pytestmark = pytest.mark.django_db

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def test_entry_url_uses_token(qr_code):
    url = qr_service.get_campaign_entry_url(qr_code)
    assert url.endswith(f'/public/lucky-draw/{qr_code.url_token}/')


def test_qr_image_is_valid_png(qr_code):
    data = qr_service.generate_qr_image(qr_service.get_campaign_entry_url(qr_code))
    assert isinstance(data, bytes)
    assert data.startswith(PNG_MAGIC)


def test_poster_is_valid_png(campaign, qr_code):
    data = qr_service.generate_poster(campaign, qr_code)
    assert isinstance(data, bytes)
    assert data.startswith(PNG_MAGIC)
    assert len(data) > 1000  # a real 1200x1800 image, not an empty buffer


def test_url_token_uniqueness_enforced(campaign, qr_code):
    """The DB unique constraint protects the token from duplication."""
    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        LuckyDrawQRCode.objects.create(
            campaign=campaign, url_token=qr_code.url_token, label='dup',
        )
