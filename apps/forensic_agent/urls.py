from django.urls import path
from apps.forensic_agent.views import ForensicReasoningView, AuditTaskListView

urlpatterns = [
    # The Single Source of Truth Endpoint
    path('reasoning/', ForensicReasoningView.as_view(), name='forensic-reasoning'),
    path('tasks/', AuditTaskListView.as_view(), name='audit_task_list'),
]