"""
OTP delivery observability.

Root cause of a real production incident (2026-08-21): an org had NO WhatsApp
config, so every customer login code was minted and then dropped. The public
endpoint must stay enumeration-safe — it returns the same 200 either way — which
meant the outage was completely invisible from outside. Five real attempts by
the owner produced five identical successes and zero messages.

The fix is not "make the endpoint report failures" (that would leak whether a
phone is known). It is: record the outcome on the OTP row, and give the owner a
dashboard endpoint that reads it.
"""
import pytest

from apps.coffee_pass.models import CoffeePassOTP

pytestmark = pytest.mark.django_db

HEALTH_URL = '/api/v1/coffee-pass/plans/channel-health/'


def _request_code(client, plan, phone='+85251234567'):
    return client.post(
        f'/public/coffee-pass/{plan.public_token}/auth/request-code/',
        {'phone': phone}, format='json',
    )


class TestDeliveryStatusIsRecorded:
    def test_no_whatsapp_config_is_recorded_as_no_channel(self, api, active_plan):
        """THE regression test for the live incident."""
        resp = _request_code(api, active_plan)
        assert resp.status_code == 200  # still generic — enumeration-safe

        otp = CoffeePassOTP.objects.filter(organization=active_plan.organization).latest('created_at')
        assert otp.delivery_status == 'no_channel'
        assert 'WhatsApp' in otp.delivery_detail

    def test_successful_send_is_recorded_as_sent(self, api, active_plan, monkeypatch):
        from apps.channels import whatsapp_service

        class FakeService:
            def send_message(self, to, text):
                return 'wamid.TEST123'

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: FakeService()),
        )
        _request_code(api, active_plan)
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'sent'
        assert 'wamid.TEST123' in otp.delivery_detail

    def test_api_rejection_is_recorded_as_failed_not_sent(
            self, api, active_plan, monkeypatch):
        """
        send_message swallows Meta errors (e.g. #133010 account-not-registered)
        and returns None. A bare try/except would call that a success — the
        exact failure mode that hid the outage.
        """
        from apps.channels import whatsapp_service

        class SilentlyFailingService:
            def send_message(self, to, text):
                return None

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: SilentlyFailingService()),
        )
        _request_code(api, active_plan)
        assert CoffeePassOTP.objects.latest('created_at').delivery_status == 'failed'

    def test_exception_during_send_is_recorded_and_never_500s(
            self, api, active_plan, monkeypatch):
        """A provider outage must not turn a public page into a 500."""
        from apps.channels import whatsapp_service

        class ExplodingService:
            def send_message(self, to, text):
                raise RuntimeError('connection reset')

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: ExplodingService()),
        )
        resp = _request_code(api, active_plan)
        assert resp.status_code == 200
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'failed'
        assert 'RuntimeError' in otp.delivery_detail

    def test_response_is_identical_whether_delivery_worked_or_not(
            self, api, active_plan, monkeypatch):
        """Enumeration-safety must survive the new bookkeeping."""
        broken = _request_code(api, active_plan).json()

        from apps.channels import whatsapp_service

        class FakeService:
            def send_message(self, to, text):
                return 'wamid.OK'

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: FakeService()),
        )
        working = _request_code(api, active_plan, phone='+85251234599').json()
        assert broken == working

    def test_nepali_number_normalizes_and_is_attempted(self, api, active_plan):
        """
        The reported number was blamed for the outage; it was never the cause.
        A +977 number is valid E.164 and must be recorded against that phone.
        """
        _request_code(api, active_plan, phone='+9779705651002')
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.phone == '+9779705651002'


class TestChannelHealthEndpoint:
    def test_owner_sees_no_channel_when_whatsapp_is_missing(
            self, owner_api, org, active_plan, api):
        _request_code(api, active_plan)
        body = owner_api.get(HEALTH_URL, {'organization': org.id}).json()
        assert body['whatsapp_configured'] is False
        assert body['can_deliver_codes'] is False
        assert body['status'] == 'no_channel'
        assert body['recent_failures'] >= 1

    def test_manager_may_read_channel_health(self, manager_api, org):
        assert manager_api.get(HEALTH_URL, {'organization': org.id}).status_code == 200

    def test_cross_org_health_is_404(self, owner_api, org_b):
        assert owner_api.get(HEALTH_URL, {'organization': org_b.id}).status_code == 404

    def test_missing_organization_is_400(self, owner_api):
        assert owner_api.get(HEALTH_URL).status_code == 400

    def test_anonymous_cannot_read_channel_health(self, api, org):
        assert api.get(HEALTH_URL, {'organization': org.id}).status_code in (401, 403)

    def test_status_is_ok_once_delivery_succeeds(
            self, owner_api, org, active_plan, api, monkeypatch):
        """An OLD failure followed by a success is a fixed problem, not a current one."""
        _request_code(api, active_plan)  # fails: no channel

        # A real config row must exist — `channel_health` reports 'no_channel'
        # on the CONFIG, not on the service object, because an org with no
        # config genuinely cannot deliver no matter what the service returns.
        from apps.channels.models import WhatsAppConfig
        from apps.channels import whatsapp_service

        WhatsAppConfig.objects.create(
            organization=org, phone_number_id='123', access_token='tok',
            is_active=True,
        )

        class FakeService:
            def send_message(self, to, text):
                return 'wamid.OK'

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org_: FakeService()),
        )
        _request_code(api, active_plan, phone='+85251234599')

        body = owner_api.get(HEALTH_URL, {'organization': org.id}).json()
        assert body['status'] == 'ok'
        assert body['whatsapp_configured'] is True
        # The historical failure is still counted, just no longer current.
        assert body['recent_failures'] >= 1
