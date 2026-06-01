"""Lucky Draw authenticated URL routing (Phase 2) — /api/v1/lucky_draw/."""
from rest_framework.routers import DefaultRouter

from .views import (
    LuckyDrawCampaignViewSet, LuckyDrawPrizeViewSet, LuckyDrawEntryViewSet,
)

router = DefaultRouter()
router.register('campaigns', LuckyDrawCampaignViewSet, basename='lucky-draw-campaign')
router.register('prizes', LuckyDrawPrizeViewSet, basename='lucky-draw-prize')
router.register('entries', LuckyDrawEntryViewSet, basename='lucky-draw-entry')

urlpatterns = router.urls
