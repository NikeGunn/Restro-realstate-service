from django.urls import path
from . import views

urlpatterns = [
    path('config/', views.WidgetConfigView.as_view(), name='widget-config'),
    path('session/', views.WidgetSessionView.as_view(), name='widget-session'),
    path('message/', views.WidgetMessageView.as_view(), name='widget-message'),
    path('conversation/<uuid:conversation_id>/', views.WidgetConversationView.as_view(), name='widget-conversation'),
    path('widget.js', views.WidgetJSView.as_view(), name='widget-js'),
]
