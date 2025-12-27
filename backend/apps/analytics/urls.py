"""
Analytics URL patterns.
"""
from django.urls import path
from .views import (
    AnalyticsOverviewView,
    AnalyticsByChannelView,
    AnalyticsByLocationView,
    AnalyticsDailyView,
)

urlpatterns = [
    path('overview/', AnalyticsOverviewView.as_view(), name='analytics-overview'),
    path('by-channel/', AnalyticsByChannelView.as_view(), name='analytics-by-channel'),
    path('by-location/', AnalyticsByLocationView.as_view(), name='analytics-by-location'),
    path('daily/', AnalyticsDailyView.as_view(), name='analytics-daily'),
]
