from django.urls import path
from apps.forensic_agent.views import ForensicReasoningView

urlpatterns = [
    # The Single Source of Truth Endpoint
    path('reasoning/', ForensicReasoningView.as_view(), name='forensic-reasoning'),
]