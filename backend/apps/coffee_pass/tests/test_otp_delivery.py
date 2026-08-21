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

    def test_free_form_text_is_unverified_not_sent(self, api, active_plan, monkeypatch):
        """
        THE regression test for the second production incident (2026-08-21).

        With no Authentication template configured the code goes out as
        free-form text. Meta returns a message id for that and then DROPS the
        message unless the number opened a 24h customer service window by
        messaging the business. Acceptance is therefore not delivery, and
        recording it as 'sent' is what made a total OTP outage look healthy:
        the owner's own handset worked (its window was open) while every real
        customer got nothing.
        """
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
        assert otp.delivery_status == 'unverified'
        assert otp.delivery_status != 'sent'

    def test_template_send_is_recorded_as_sent(
            self, api, active_plan, monkeypatch, settings):
        """With a template configured, delivery is real and recorded as sent."""
        from apps.channels import whatsapp_service

        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS,
            'OTP_TEMPLATE_NAME': 'coffee_pass_otp',
            'OTP_TEMPLATE_LANGUAGE': 'en',
        }

        class FakeService:
            def send_template(self, **kwargs):
                return 'wamid.TEMPLATE123'

            def send_message(self, to, text):
                raise AssertionError('must use the template, never free-form text')

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: FakeService()),
        )
        _request_code(api, active_plan)
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'sent'
        assert 'wamid.TEMPLATE123' in otp.delivery_detail

    def test_template_carries_the_code_in_body_and_button(
            self, api, active_plan, monkeypatch, settings):
        """
        An Authentication template renders the code in the body ({{1}}) and
        again as the one-tap copy-code button parameter. Getting either wrong
        makes Meta reject the send with a parameter-count mismatch.
        """
        from apps.channels import whatsapp_service

        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS,
            'OTP_TEMPLATE_NAME': 'coffee_pass_otp',
            'OTP_TEMPLATE_LANGUAGE': 'en',
        }
        captured = {}

        class FakeService:
            def send_template(self, **kwargs):
                captured.update(kwargs)
                return 'wamid.OK'

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: FakeService()),
        )
        _request_code(api, active_plan)

        assert captured['template_name'] == 'coffee_pass_otp'
        assert captured['language_code'] == 'en'
        assert len(captured['body_params']) == 1
        assert len(captured['button_params']) == 1
        code = str(captured['body_params'][0])
        assert code.isdigit() and len(code) == 6
        # Body and button must carry the SAME code, or the copy button pastes
        # a code that fails verification.
        assert str(captured['button_params'][0]) == code

    def test_template_rejection_is_failed_and_never_falls_back_to_text(
            self, api, active_plan, monkeypatch, settings):
        """
        A rejected template (unapproved, wrong language, wrong variable count)
        must be recorded as a hard failure. Silently retrying as free-form text
        would reintroduce the original bug for every cold number.
        """
        from apps.channels import whatsapp_service

        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS,
            'OTP_TEMPLATE_NAME': 'coffee_pass_otp',
            'OTP_TEMPLATE_LANGUAGE': 'en',
        }

        class RejectingService:
            def send_template(self, **kwargs):
                return None

            def send_message(self, to, text):
                raise AssertionError('must NOT fall back to free-form text')

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: RejectingService()),
        )
        resp = _request_code(api, active_plan)
        assert resp.status_code == 200  # still enumeration-safe
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'failed'
        assert 'coffee_pass_otp' in otp.delivery_detail

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

    def test_config_without_template_is_not_deliverable(self, owner_api, org):
        """
        An active WhatsApp config is necessary but NOT sufficient. Without an
        Authentication template only numbers inside their 24h window get a code.
        Reporting that as 'ok' is the false-green that hid the outage: the
        operator's own phone worked, so the dashboard looked healthy.
        """
        from apps.channels.models import WhatsAppConfig

        WhatsAppConfig.objects.create(
            organization=org, phone_number_id='123', access_token='tok',
            is_active=True,
        )
        body = owner_api.get(HEALTH_URL, {'organization': org.id}).json()
        assert body['whatsapp_configured'] is True
        assert body['otp_template_configured'] is False
        assert body['can_deliver_codes'] is False
        assert body['status'] == 'no_template'

    def test_manager_may_read_channel_health(self, manager_api, org):
        assert manager_api.get(HEALTH_URL, {'organization': org.id}).status_code == 200

    def test_cross_org_health_is_404(self, owner_api, org_b):
        assert owner_api.get(HEALTH_URL, {'organization': org_b.id}).status_code == 404

    def test_missing_organization_is_400(self, owner_api):
        assert owner_api.get(HEALTH_URL).status_code == 400

    def test_anonymous_cannot_read_channel_health(self, api, org):
        assert api.get(HEALTH_URL, {'organization': org.id}).status_code in (401, 403)

    def test_status_is_ok_once_delivery_succeeds(
            self, owner_api, org, active_plan, api, monkeypatch, settings):
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

        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS,
            'OTP_TEMPLATE_NAME': 'coffee_pass_otp',
            'OTP_TEMPLATE_LANGUAGE': 'en',
        }

        class FakeService:
            def send_template(self, **kwargs):
                return 'wamid.OK'

        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org_: FakeService()),
        )
        _request_code(api, active_plan, phone='+85251234599')

        body = owner_api.get(HEALTH_URL, {'organization': org.id}).json()
        assert body['status'] == 'ok'
        assert body['whatsapp_configured'] is True
        assert body['can_deliver_codes'] is True
        # The historical failure is still counted, just no longer current.
        assert body['recent_failures'] >= 1


class TestWorstCaseDelivery:
    """
    Adversarial + failure-mode coverage for the production OTP path.

    Every case here answers one question: can a real customer who has NEVER
    messaged this business scan the QR and receive a code? Anything that breaks
    that must fail loudly, never look healthy.
    """

    def _use_template(self, settings, name='coffee_pass_otp', lang='en'):
        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS,
            'OTP_TEMPLATE_NAME': name,
            'OTP_TEMPLATE_LANGUAGE': lang,
        }

    def _patch(self, monkeypatch, service):
        from apps.channels import whatsapp_service
        monkeypatch.setattr(
            whatsapp_service.WhatsAppService, 'get_for_organization',
            classmethod(lambda cls, org: service),
        )

    def test_cold_number_still_gets_a_template_send(
            self, api, active_plan, monkeypatch, settings):
        """
        THE core acceptance criterion: a brand-new customer (no 24h window, no
        prior conversation, not in the CRM) must still be sent a code.
        """
        self._use_template(settings)
        seen = {}

        class Svc:
            def send_template(self, **kw):
                seen['to'] = kw['to']
                return 'wamid.COLD'

        self._patch(monkeypatch, Svc())
        _request_code(api, active_plan, phone='+85298765432')
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'sent'
        assert seen['to'] == '+85298765432'

    def test_template_send_raising_is_caught_and_never_500s(
            self, api, active_plan, monkeypatch, settings):
        """A provider outage on the template path must not break a public page."""
        self._use_template(settings)

        class Exploding:
            def send_template(self, **kw):
                raise RuntimeError('connection reset by peer')

        self._patch(monkeypatch, Exploding())
        resp = _request_code(api, active_plan)
        assert resp.status_code == 200
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'failed'
        assert 'RuntimeError' in otp.delivery_detail

    def test_delivery_detail_never_contains_the_raw_code(
            self, api, active_plan, monkeypatch, settings):
        """
        SECURITY: delivery_detail is operator-visible. Leaking the code there
        would turn a dashboard read into an account takeover.
        """
        self._use_template(settings)
        codes = []

        class Svc:
            def send_template(self, **kw):
                codes.append(str(kw['body_params'][0]))
                return 'wamid.OK'

        self._patch(monkeypatch, Svc())
        _request_code(api, active_plan)
        otp = CoffeePassOTP.objects.latest('created_at')
        assert codes and codes[0] not in otp.delivery_detail
        assert codes[0] not in str(otp.code_hash)

    def test_http_response_body_never_contains_the_code(
            self, api, active_plan, monkeypatch, settings):
        """The raw code must never travel back over the requesting connection."""
        self._use_template(settings)
        codes = []

        class Svc:
            def send_template(self, **kw):
                codes.append(str(kw['body_params'][0]))
                return 'wamid.OK'

        self._patch(monkeypatch, Svc())
        resp = _request_code(api, active_plan)
        assert codes[0] not in resp.content.decode()

    def test_response_identical_across_every_failure_mode(
            self, api, active_plan, monkeypatch, settings):
        """
        Enumeration-safety under the new template path: sent, rejected, and
        crashed must be indistinguishable to the caller. Otherwise response
        shape becomes an oracle for which numbers are real.
        """
        self._use_template(settings)
        bodies = []

        class Ok:
            def send_template(self, **kw):
                return 'wamid.OK'

        class Rejected:
            def send_template(self, **kw):
                return None

        class Boom:
            def send_template(self, **kw):
                raise RuntimeError('boom')

        for idx, svc in enumerate((Ok(), Rejected(), Boom())):
            self._patch(monkeypatch, svc)
            r = _request_code(api, active_plan, phone='+8525123' + str(idx) + '001')
            bodies.append((r.status_code, r.json()))

        assert len({repr(b) for b in bodies}) == 1, bodies

    def test_verification_still_works_after_a_template_send(
            self, api, active_plan, monkeypatch, settings):
        """
        End-to-end: the code delivered by template must actually verify and
        mint a session. A delivery fix that broke verification would be worse
        than the bug.
        """
        self._use_template(settings)
        codes = []

        class Svc:
            def send_template(self, **kw):
                codes.append(str(kw['body_params'][0]))
                return 'wamid.OK'

        self._patch(monkeypatch, Svc())
        phone = '+85298761234'
        _request_code(api, active_plan, phone=phone)

        resp = api.post(
            '/public/coffee-pass/' + str(active_plan.public_token) + '/auth/verify-code/',
            {'phone': phone, 'code': codes[0]}, format='json',
        )
        assert resp.status_code == 200, resp.content

    def test_wrong_code_still_rejected_on_the_template_path(
            self, api, active_plan, monkeypatch, settings):
        """Delivery changes must not weaken brute-force resistance."""
        self._use_template(settings)
        codes = []

        class Svc:
            def send_template(self, **kw):
                codes.append(str(kw['body_params'][0]))
                return 'wamid.OK'

        self._patch(monkeypatch, Svc())
        phone = '+85298769999'
        _request_code(api, active_plan, phone=phone)

        wrong = '000000' if codes[0] != '000000' else '111111'
        resp = api.post(
            '/public/coffee-pass/' + str(active_plan.public_token) + '/auth/verify-code/',
            {'phone': phone, 'code': wrong}, format='json',
        )
        assert resp.status_code >= 400

    def test_misconfigured_template_fails_loudly_not_silently(
            self, api, active_plan, monkeypatch, settings):
        """
        A misconfigured template name must fail loudly on the template path,
        not silently degrade to the text path that cannot reach cold numbers.
        """
        self._use_template(settings, name='  ')

        class Svc:
            def send_template(self, **kw):
                return None

            def send_message(self, to, text):
                return 'wamid.TEXT'

        self._patch(monkeypatch, Svc())
        _request_code(api, active_plan)
        otp = CoffeePassOTP.objects.latest('created_at')
        assert otp.delivery_status == 'failed'
