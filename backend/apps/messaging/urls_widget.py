"""
Widget URL patterns.
Includes multilingual language selection endpoint.
"""
from django.urls import path
from .views_widget import (
    WidgetInitView,
    WidgetMessageView,
    WidgetHistoryView,
    WidgetLocationSelectView,
    WidgetLanguageSelectView,
)

urlpatterns = [
    path('init/', WidgetInitView.as_view(), name='widget-init'),
    path('message/', WidgetMessageView.as_view(), name='widget-message'),
    path('history/', WidgetHistoryView.as_view(), name='widget-history'),
    path('location/', WidgetLocationSelectView.as_view(), name='widget-location'),
    path('language/', WidgetLanguageSelectView.as_view(), name='widget-language'),
]
