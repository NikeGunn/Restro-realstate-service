from django.urls import path

from .views import AgentPlaybookView

urlpatterns = [
    path('playbook/', AgentPlaybookView.as_view(), name='agent-playbook'),
]
