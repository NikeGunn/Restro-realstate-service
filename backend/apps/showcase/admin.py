"""Superuser-only admin to upload and publish showcase videos (Django admin → Showcase videos)."""
from django.contrib import admin
from django.utils.html import format_html

from .models import MAX_VIDEO_BYTES, ShowcaseVideo


@admin.register(ShowcaseVideo)
class ShowcaseVideoAdmin(admin.ModelAdmin):
    list_display = ('preview_thumb', 'title', 'placement', 'is_active', 'sort_order', 'updated_at')
    list_display_links = ('preview_thumb', 'title')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('placement', 'is_active')
    search_fields = ('title', 'caption')
    readonly_fields = ('preview', 'public_link', 'created_at', 'updated_at')
    fieldsets = (
        ('Video', {
            'fields': ('video', 'preview', 'poster'),
            'description': format_html(
                'Upload the final film here. <b>MP4 (H.264, AAC audio)</b>, 1080p, up to '
                '<b>{} MB</b> (about 60-90 seconds at ~5 Mbps). It goes live as soon as it is saved '
                'and active. Brand guide: <code>brand-memory.md</code>.', MAX_VIDEO_BYTES // (1024 * 1024)),
        }),
        ('Where it appears', {'fields': ('title', 'caption', 'placement', 'is_active', 'sort_order', 'public_link')}),
        ('History', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    # Marketing assets are platform-wide: only superusers see or change them.
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_change_permission = has_delete_permission = (
        lambda self, request, obj=None: self.has_module_permission(request))

    @admin.display(description='Preview')
    def preview(self, obj):
        if not obj or not obj.video:
            return 'Save to see the preview.'
        return format_html(
            '<video src="{}" {} controls preload="metadata" playsinline '
            'style="max-width:560px;width:100%;border-radius:12px;background:#14231F"></video>',
            obj.video.url, format_html('poster="{}"', obj.poster.url) if obj.poster else '')

    @admin.display(description='')
    def preview_thumb(self, obj):
        if obj.poster:
            return format_html('<img src="{}" style="width:120px;aspect-ratio:16/9;object-fit:cover;'
                               'border-radius:8px">', obj.poster.url)
        return format_html('<video src="{}#t=1" preload="metadata" muted style="width:120px;aspect-ratio:16/9;'
                           'object-fit:cover;border-radius:8px;background:#14231F"></video>', obj.video.url)

    @admin.display(description='Shown on')
    def public_link(self, obj):
        url = {'landing': 'https://kribaat.com/', 'properties': 'https://kribaat.com/realestate/properties/'}
        if not obj or not obj.placement:
            return '-'
        return format_html('<a href="{0}" target="_blank" rel="noopener">{0}</a>', url[obj.placement])
