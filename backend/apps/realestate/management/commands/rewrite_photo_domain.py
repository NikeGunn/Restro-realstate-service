"""
Point stored listing photo URLs at a new public domain (objects are not moved).

    python manage.py rewrite_photo_domain --from pub-296eb79cd8404023a4b91caa9c0e6bd0.r2.dev \
        --to media.kribaat.com [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.realestate.models import PropertyListing


class Command(BaseCommand):
    help = 'Rewrite listing photo URLs from one public domain to another.'

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='old', required=True)
        parser.add_argument('--to', dest='new', required=True)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, old, new, dry_run, **_):
        old_prefix, new_prefix = f'https://{old.strip("/")}/', f'https://{new.strip("/")}/'
        changed = urls = 0
        with transaction.atomic():
            for listing in PropertyListing.objects.select_for_update().exclude(images=[]):
                images = list(listing.images or [])
                rewritten = [u.replace(old_prefix, new_prefix, 1) if isinstance(u, str) and u.startswith(old_prefix)
                             else u for u in images]
                if rewritten != images:
                    changed += 1
                    urls += sum(a != b for a, b in zip(images, rewritten))
                    if not dry_run:
                        listing.images = rewritten
                        listing.save(update_fields=['images', 'updated_at'])
            if dry_run:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(
            f"{'Would rewrite' if dry_run else 'Rewrote'} {urls} photo URL(s) on {changed} listing(s): "
            f"{old_prefix} -> {new_prefix}"))
