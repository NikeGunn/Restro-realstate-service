"""Phase 5 — prompt builder: required-field enforcement, brand injection, seed coverage."""
import pytest

from apps.content_studio.models import ContentUseCase
from apps.content_studio.services import prompt_builder

pytestmark = pytest.mark.django_db


def test_builds_prompt_with_inputs(use_case, brand_kit):
    prompt, negative = prompt_builder.build_prompt(
        use_case, {'offer_title': '50% Off', 'discount_value': '50%', 'hero_dish': 'Ramen'},
        brand_kit,
    )
    assert '50% Off' in prompt
    assert '50%' in prompt
    assert 'Ramen' in prompt
    assert negative  # template has a negative prompt


def test_brand_values_injected(use_case, brand_kit):
    prompt, _ = prompt_builder.build_prompt(
        use_case, {'offer_title': 'X', 'discount_value': 'Y'}, brand_kit,
    )
    assert 'Bargachi' in prompt           # restaurant name
    assert '#E11D48' in prompt            # brand color
    assert 'Book now' in prompt           # CTA
    assert 'Traditional Chinese' in prompt  # zh-TW language steering


def test_missing_required_raises(use_case, brand_kit):
    with pytest.raises(ValueError) as exc:
        prompt_builder.build_prompt(use_case, {'offer_title': 'only title'}, brand_kit)
    assert 'Discount' in str(exc.value)   # label of the missing field


def test_no_brand_kit_still_builds(use_case):
    prompt, _ = prompt_builder.build_prompt(
        use_case, {'offer_title': 'A', 'discount_value': 'B'}, None,
    )
    assert 'A' in prompt and 'B' in prompt


def test_unknown_placeholders_do_not_leak(use_case, brand_kit):
    prompt, _ = prompt_builder.build_prompt(
        use_case, {'offer_title': 'A', 'discount_value': 'B'}, brand_kit,
    )
    assert '{{' not in prompt and '}}' not in prompt


def test_no_template_raises():
    uc = ContentUseCase.objects.create(
        use_case_key='no_template', display_name='No Template',
        required_fields=[], optional_fields=[], supported_formats=['square'],
    )
    with pytest.raises(ValueError):
        prompt_builder.build_prompt(uc, {}, None)


def test_all_seeded_use_cases_produce_nonempty_prompts(django_db_blocker):
    """Exercise the real seeded 12 use cases via the data migration's output."""
    # The seed data migration runs as part of test DB setup, so the 12 rows exist.
    seeded = ContentUseCase.objects.exclude(use_case_key__in=['no_template'])
    checked = 0
    for uc in seeded.select_related('prompt_template'):
        if not hasattr(uc, 'prompt_template'):
            continue
        # Fill required fields with placeholder values.
        payload = {}
        for f in uc.required_fields:
            payload[f['key']] = True if f.get('type') == 'checkbox' else 'Sample'
        prompt, _ = prompt_builder.build_prompt(uc, payload, None)
        assert prompt.strip(), f'{uc.use_case_key} produced an empty prompt'
        checked += 1
    assert checked >= 12  # all seeded use cases covered
