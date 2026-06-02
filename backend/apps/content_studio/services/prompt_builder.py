"""
Prompt builder — turns a structured use-case form + brand kit into a
production-grade image prompt. NO OpenAI call here (pure, unit-testable).

Design rules:
- Prompts live in `ContentPromptTemplate` rows (the repo's "no inline prompts"
  rule), never hardcoded. This module only *merges* inputs into a template.
- Missing a required field → ValueError (the view validates first, but the
  builder is the last line of defence so a Celery retry can't silently skip it).
- The brand kit is woven in as an explicit, ordered context block so the model
  reliably honours restaurant name, colours, CTA, and language (zh-TW default).
- `{{placeholders}}` are substituted from input_payload first, then brand-kit
  fallbacks. Unknown placeholders collapse to empty (never leak "{{x}}").
"""
import re
from typing import Tuple

PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# Human-readable language steering appended so the model renders on-image text
# in the brand's language. zh-TW (Traditional) is the HK-first default.
_LANGUAGE_LABEL = {
    'zh-TW': 'Traditional Chinese (zh-HK / Hong Kong style)',
    'zh-CN': 'Simplified Chinese',
    'en': 'English',
}


def _coerce_payload(input_payload: dict, brand_kit) -> dict:
    """Build the substitution map: input fields win, brand-kit values are fallback."""
    data = {}
    if brand_kit is not None:
        data.update({
            'restaurant_name': brand_kit.restaurant_name or '',
            'default_cta': brand_kit.default_cta or '',
            'phone': brand_kit.phone or '',
            'whatsapp': brand_kit.whatsapp or '',
            'address': brand_kit.address or '',
            'website_url': brand_kit.website_url or '',
        })
    # Input payload overrides brand-kit fallbacks (and adds use-case fields).
    for k, v in (input_payload or {}).items():
        if isinstance(v, (list, dict)):
            continue  # structural fields (e.g. checkboxes) aren't text placeholders
        data[k] = '' if v is None else str(v)
    return data


def _substitute(template: str, data: dict) -> str:
    def repl(m):
        return data.get(m.group(1), '').strip()
    # Substitute, then collapse the whitespace left by emptied placeholders.
    out = PLACEHOLDER_RE.sub(repl, template or '')
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


def _brand_context_block(brand_kit) -> str:
    """An explicit, authoritative brand channel kept SEPARATE from the art-direction
    body (so brand rules don't 'fight' inside one block — the Higgsfield principle).
    Uses direct affirmative directives, not narrative."""
    if brand_kit is None:
        return ''
    lines = []
    if brand_kit.restaurant_name:
        lines.append(f'Brand: {brand_kit.restaurant_name}.')
    colors = [c for c in (brand_kit.brand_colors or []) if c]
    if colors:
        lines.append(f'Palette: use {", ".join(colors)} as the dominant accent colors.')
    if brand_kit.default_cta:
        lines.append(f'Render this call-to-action prominently: "{brand_kit.default_cta}".')
    style = brand_kit.style_preferences or {}
    if isinstance(style, dict) and style.get('mood'):
        lines.append(f'Mood: {style["mood"]}.')
    if isinstance(style, dict) and style.get('style'):
        lines.append(f'Art direction: {style["style"]}.')
    lang = _LANGUAGE_LABEL.get(brand_kit.preferred_language, brand_kit.preferred_language)
    lines.append(f'Render ALL on-image text in {lang}, spelled correctly with clean kerning.')
    if brand_kit.watermark_preference == 'logo' and brand_kit.logo:
        lines.append('Reserve a clean corner for the logo (composited in post).')
    elif brand_kit.watermark_preference == 'text' and brand_kit.restaurant_name:
        lines.append(f'Include a small, tasteful "{brand_kit.restaurant_name}" wordmark.')
    return '\n'.join(lines)


def _missing_required(use_case, input_payload: dict) -> list:
    payload = input_payload or {}
    missing = []
    for field in (use_case.required_fields or []):
        key = field.get('key')
        if not key:
            continue
        val = payload.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field.get('label') or key)
    return missing


def build_prompt(use_case, input_payload: dict, brand_kit) -> Tuple[str, str]:
    """
    Merge use-case inputs + brand kit into the template's prompt.

    Returns (prompt, negative_prompt). Raises ValueError if a required field is
    missing. Does NOT call any provider.
    """
    template = getattr(use_case, 'prompt_template', None)
    if template is None:
        raise ValueError(
            f'Use case "{use_case.use_case_key}" has no prompt template configured.'
        )

    missing = _missing_required(use_case, input_payload)
    if missing:
        raise ValueError(f'Missing required field(s): {", ".join(missing)}')

    data = _coerce_payload(input_payload, brand_kit)
    body = _substitute(template.prompt_template, data)

    # Assemble the final prompt: art-direction body + an explicit brand block.
    brand_block = _brand_context_block(brand_kit)
    parts = [body]
    if brand_block:
        parts.append('BRAND CONTEXT (honour exactly):\n' + brand_block)
    prompt = '\n\n'.join(p for p in parts if p).strip()

    negative = _substitute(template.negative_prompt, data) if template.negative_prompt else ''
    return prompt, negative
