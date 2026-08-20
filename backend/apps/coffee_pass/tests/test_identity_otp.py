"""
OTP + public session security tests.

The public flow is the platform's only unauthenticated write surface, so these
tests are adversarial: brute force, replay, enumeration, tampering, cross-tenant
session reuse. Each maps to a concrete attack, not just a code path.
"""
from django.core import signing
from django.utils import timezone
import pytest

from apps.coffee_pass.models import CoffeePassOTP
from apps.coffee_pass.services import identity_service


@pytest.mark.django_db
class TestOTPStorage:
    def test_raw_code_is_never_stored(self, org):
        """
        A database leak must not yield working codes.

        We assert the raw code appears in NO column of the row.
        """
        otp, code = identity_service.request_code(
            organization=org, phone='+85251234567')

        assert otp.code_hash != code
        assert len(otp.code_hash) == 64  # sha256 hex
        row = CoffeePassOTP.objects.filter(pk=otp.pk).values().first()
        assert code not in str(row)

    def test_hash_is_peppered_with_secret_key(self, org, settings):
        """
        A plain sha256 of a 6-digit code is rainbow-table-able in milliseconds.

        Changing SECRET_KEY must change the hash, proving the pepper is applied.
        """
        first = identity_service.hash_code('123456')
        settings.SECRET_KEY = 'a-completely-different-secret-key'
        assert identity_service.hash_code('123456') != first

    def test_code_is_six_digits_from_secrets_module(self):
        codes = {identity_service.generate_code() for _ in range(50)}
        assert all(len(c) == 6 and c.isdigit() for c in codes)
        # Sanity: not a constant.
        assert len(codes) > 1

    def test_requesting_again_invalidates_the_previous_code(self, org):
        """
        An attacker who saw an older SMS must not be able to use it after the
        customer requests a fresh one.
        """
        first_otp, first_code = identity_service.request_code(
            organization=org, phone='+85251234567')
        identity_service.request_code(organization=org, phone='+85251234567')

        first_otp.refresh_from_db()
        assert first_otp.consumed_at is not None
        with pytest.raises(identity_service.OTPError):
            identity_service.verify_code(
                organization=org, phone='+85251234567', code=first_code)


@pytest.mark.django_db
class TestOTPVerification:
    def test_happy_path_resolves_a_crm_customer(self, org):
        _, code = identity_service.request_code(
            organization=org, phone='+852 5123 4567')
        customer = identity_service.verify_code(
            organization=org, phone='+852 5123 4567', code=code)

        assert customer.organization_id == org.id
        # Identity goes through the EXISTING CRM service -> E.164 normalized.
        assert customer.phone == '+85251234567'

    def test_phone_normalization_means_formatting_does_not_matter(self, org):
        """A customer typing spaces or a local format must still verify."""
        _, code = identity_service.request_code(organization=org, phone='51234567')
        customer = identity_service.verify_code(
            organization=org, phone='+852 5123-4567', code=code)
        assert customer.phone == '+85251234567'

    def test_wrong_code_rejected(self, org):
        identity_service.request_code(organization=org, phone='+85251234567')
        with pytest.raises(identity_service.OTPError):
            identity_service.verify_code(
                organization=org, phone='+85251234567', code='000000')

    def test_expired_code_rejected(self, org):
        otp, code = identity_service.request_code(
            organization=org, phone='+85251234567')
        otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        otp.save(update_fields=['expires_at'])

        with pytest.raises(identity_service.OTPError):
            identity_service.verify_code(
                organization=org, phone='+85251234567', code=code)

    def test_code_is_single_use(self, org):
        """Replaying a verified code must not mint a second session."""
        _, code = identity_service.request_code(
            organization=org, phone='+85251234567')
        identity_service.verify_code(
            organization=org, phone='+85251234567', code=code)

        with pytest.raises(identity_service.OTPError):
            identity_service.verify_code(
                organization=org, phone='+85251234567', code=code)

    def test_brute_force_burns_the_code(self, org, settings):
        """
        A 6-digit code has 1e6 possibilities — trivially brute-forced without a
        ceiling. After MAX_ATTEMPTS the code dies, even if the NEXT guess is right.
        """
        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS, 'OTP_MAX_ATTEMPTS': 3,
        }
        otp, code = identity_service.request_code(
            organization=org, phone='+85251234567')

        for _ in range(3):
            with pytest.raises(identity_service.OTPError):
                identity_service.verify_code(
                    organization=org, phone='+85251234567', code='999999')

        otp.refresh_from_db()
        assert otp.consumed_at is not None  # burned
        with pytest.raises(identity_service.OTPError):
            identity_service.verify_code(
                organization=org, phone='+85251234567', code=code)

    def test_code_from_another_org_does_not_verify(self, org, org_b):
        """Tenant isolation: an OTP is scoped to the org that issued it."""
        _, code = identity_service.request_code(
            organization=org, phone='+85251234567')
        with pytest.raises(identity_service.OTPError):
            identity_service.verify_code(
                organization=org_b, phone='+85251234567', code=code)


@pytest.mark.django_db
class TestRateLimiting:
    def test_per_phone_send_limit(self, org, settings):
        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS, 'OTP_MAX_SENDS_PER_PHONE': 3,
        }
        for _ in range(3):
            identity_service.request_code(organization=org, phone='+85251234567')

        with pytest.raises(identity_service.OTPError) as exc:
            identity_service.request_code(organization=org, phone='+85251234567')
        assert exc.value.reason == 'rate_limited'

    def test_different_phones_are_independent(self, org, settings):
        """One customer hitting the wall must not lock out everyone else."""
        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS, 'OTP_MAX_SENDS_PER_PHONE': 2,
        }
        for _ in range(2):
            identity_service.request_code(organization=org, phone='+85251234567')
        # A different number still works.
        otp, _ = identity_service.request_code(organization=org, phone='+85251111111')
        assert otp.pk is not None

    def test_invalid_phone_raises_before_any_row_is_written(self, org):
        with pytest.raises(identity_service.OTPError):
            identity_service.request_code(organization=org, phone='')
        assert CoffeePassOTP.objects.count() == 0


@pytest.mark.django_db
class TestPublicSession:
    def test_session_round_trips_to_the_same_customer(self, org, customer):
        token = identity_service.issue_session(customer)
        assert identity_service.resolve_session(token).id == customer.id

    def test_tampered_session_is_rejected(self, customer):
        """Flipping any character must invalidate the signature."""
        token = identity_service.issue_session(customer)
        assert identity_service.resolve_session(token[:-3] + 'xyz') is None

    def test_expired_session_is_rejected(self, customer, settings):
        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS, 'SESSION_TTL_SECONDS': 0,
        }
        token = identity_service.issue_session(customer)
        import time
        time.sleep(1.1)
        assert identity_service.resolve_session(token) is None

    def test_session_carries_no_pii(self, customer):
        """
        The token must contain ids only. A leaked URL/log line should not expose
        a phone number or a name.
        """
        token = identity_service.issue_session(customer)
        payload = signing.loads(token, salt=identity_service.SESSION_SALT)
        assert set(payload.keys()) == {'cid', 'oid'}
        assert customer.phone not in token
        assert customer.name not in token

    def test_token_from_another_salt_is_rejected(self, customer):
        """
        A signed token minted elsewhere in the platform must not work here.

        The namespaced salt is what prevents cross-feature token replay.
        """
        foreign = signing.dumps(
            {'cid': str(customer.id), 'oid': str(customer.organization_id)},
            salt='some.other.feature',
        )
        assert identity_service.resolve_session(foreign) is None

    def test_inactive_customer_session_stops_working(self, customer):
        """Blocking a customer must invalidate sessions already in the wild."""
        token = identity_service.issue_session(customer)
        customer.is_active = False
        customer.save(update_fields=['is_active'])
        assert identity_service.resolve_session(token) is None

    def test_empty_and_garbage_tokens_return_none(self):
        for value in ('', None, 'garbage', 'a.b.c'):
            assert identity_service.resolve_session(value) is None
