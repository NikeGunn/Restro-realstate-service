"""
Authentication URL patterns.
"""
from django.urls import path

from .views import (
    RegisterView,
    CurrentUserView,
    LogoutView,
    LoginView,
    TokenRefreshNoSessionView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('refresh/', TokenRefreshNoSessionView.as_view(), name='auth-refresh'),
    path('me/', CurrentUserView.as_view(), name='auth-me'),
]
