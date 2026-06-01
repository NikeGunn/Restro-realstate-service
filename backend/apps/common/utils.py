"""
Small shared helpers (promoted verbatim from apps/inventory/views.py so every
new app's audit logging produces identical snapshots/diffs).
"""
from decimal import Decimal


def client_ip(request):
    """Best-effort client IP, honoring X-Forwarded-For (we sit behind Traefik)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def model_to_dict(instance, exclude=('updated_at',)):
    """Lightweight, JSON-safe snapshot of a model instance for audit diffs."""
    data = {}
    for f in instance._meta.fields:
        if f.name in exclude:
            continue
        val = getattr(instance, f.attname, None)
        if hasattr(val, 'isoformat'):
            val = val.isoformat()
        elif isinstance(val, Decimal):
            val = str(val)
        else:
            val = str(val) if val is not None else None
        data[f.name] = val
    return data


def diff(before: dict, after: dict) -> dict:
    """Field-level before/after diff between two model_to_dict snapshots."""
    out = {}
    for k in set(before) | set(after):
        b, a = before.get(k), after.get(k)
        if b != a:
            out[k] = {'before': b, 'after': a}
    return out
