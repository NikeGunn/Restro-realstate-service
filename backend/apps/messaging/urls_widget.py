"""
Widget URL patterns.
"""
from django.urls import path
from .views_widget import (
    WidgetInitView,
    WidgetMessageView,
    WidgetHistoryView,
    WidgetLocationSelectView,
)

urlpatterns = [
    path('init/', WidgetInitView.as_view(), name='widget-init'),
    path('message/', WidgetMessageView.as_view(), name='widget-message'),
    path('history/', WidgetHistoryView.as_view(), name='widget-history'),
    path('location/', WidgetLocationSelectView.as_view(), name='widget-location'),
]
