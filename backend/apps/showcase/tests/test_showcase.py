"""Showcase videos: superuser-only admin upload, public list, range-streamed media."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.showcase.models import MAX_VIDEO_BYTES, ShowcaseVideo, validate_video

pytestmark = pytest.mark.django_db

MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 4000  # a valid-looking MP4 header


@pytest.fixture(autouse=True)
def local_media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    for k in ('R2_BUCKET', 'R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_PUBLIC_DOMAIN'):
        setattr(settings, k, '')


def _video(**kw):
    data = dict(title='Meet the Kribaat agent', video=SimpleUploadedFile('film.mp4', MP4, content_type='video/mp4'))
    data.update(kw)
    return ShowcaseVideo.objects.create(**data)


def test_validator_accepts_mp4_and_rejects_fakes_and_oversize():
    validate_video(SimpleUploadedFile('a.mp4', MP4))
    with pytest.raises(ValidationError):
        validate_video(SimpleUploadedFile('a.mp4', b'<html>not a video</html>' * 10))
    with pytest.raises(ValidationError):
        validate_video(SimpleUploadedFile('a.exe', MP4))
    big = SimpleUploadedFile('a.mp4', MP4)
    big.size = MAX_VIDEO_BYTES + 1
    with pytest.raises(ValidationError):
        validate_video(big)


def test_public_list_only_shows_active_videos_for_the_placement(client):
    live = _video(sort_order=1)
    _video(title='Draft', is_active=False)
    _video(title='Property site film', placement='properties')
    r = client.get('/api/public/showcase/?placement=landing')
    assert r.status_code == 200
    vids = r.json()['videos']
    assert [v['title'] for v in vids] == [live.title] and vids[0]['type'] == 'video/mp4'
    assert client.get('/api/public/showcase/?placement=nope').status_code == 400


def test_media_supports_range_requests_for_seeking(client):
    v = _video()
    name = v.video.name.split('/', 1)[1]
    full = client.get(f'/showcase/{name}')
    assert full.status_code == 200 and b''.join(full.streaming_content) == MP4
    part = client.get(f'/showcase/{name}', HTTP_RANGE='bytes=4-11')
    assert part.status_code == 206 and part['Content-Range'] == f'bytes 4-11/{len(MP4)}'
    assert b''.join(part.streaming_content) == MP4[4:12]
    tail = client.get(f'/showcase/{name}', HTTP_RANGE='bytes=-10')
    assert b''.join(tail.streaming_content) == MP4[-10:]
    assert client.get(f'/showcase/{name}', HTTP_RANGE=f'bytes={len(MP4) + 5}-').status_code == 416


def test_media_never_serves_other_keys(client):
    assert client.get('/showcase/../listings/x.jpg').status_code == 404
    assert client.get('/showcase/notahexname.mp4').status_code == 404


def test_admin_is_superuser_only(client):
    staff = User.objects.create_user(username='s@x.com', email='s@x.com', password='pw-12345678', is_staff=True)
    client.force_login(staff)
    assert client.get('/admin/showcase/showcasevideo/').status_code == 403
    boss = User.objects.create_superuser(username='b@x.com', email='b@x.com', password='pw-12345678')
    client.force_login(boss)
    assert client.get('/admin/showcase/showcasevideo/add/').status_code == 200


def test_superuser_uploads_through_admin_and_it_goes_live(client):
    boss = User.objects.create_superuser(username='b@x.com', email='b@x.com', password='pw-12345678')
    client.force_login(boss)
    r = client.post('/admin/showcase/showcasevideo/add/', {
        'title': 'Launch film', 'caption': 'From search to site visit', 'placement': 'landing',
        'is_active': 'on', 'sort_order': 0, 'video': SimpleUploadedFile('launch.mp4', MP4, content_type='video/mp4'),
    })
    assert r.status_code == 302, r.content[:500]
    assert client.get('/api/public/showcase/').json()['videos'][0]['title'] == 'Launch film'


def test_property_site_shows_the_properties_film(client, settings):
    from apps.accounts.models import Location, Organization
    o = Organization.objects.create(name='Kribaat Realestate', business_type='real_estate')
    Location.objects.create(organization=o, name='HQ', is_primary=True, is_active=True, country='Nepal')
    settings.PUBLIC_LISTINGS_ORG = str(o.id)
    _video(title='How Kribaat finds your kotha', placement='properties')
    html = client.get('/realestate/properties/').content.decode()
    assert 'How Kribaat finds your kotha' in html and '<video' in html
