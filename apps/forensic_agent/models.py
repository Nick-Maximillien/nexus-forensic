import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField

class AuditTask(models.Model):
    """
    Represents the lifecycle of a single Forensic Audit/Research Agent execution.
    Tracks the transition from INGESTION -> VALIDATION -> NOTIFICATION.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Processing'),
        ('CLEARED', 'Cleared (Valid)'), 
        ('HALTED', 'Halted (Invalid)'), 
        ('ERROR', 'System Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_id = models.CharField(max_length=100) # External Reference (e.g., "KE-2026-089")
    
    # Inputs
    claim_payload = models.JSONField(help_text="The raw claim data received")
    query_intent = models.TextField(help_text="The clinical query/scenario")
    
    # State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Forensic Outputs (The Truth)
    # We store the deterministic verdict separately from the LLM render
    verdict_json = models.JSONField(null=True, blank=True, help_text="Structured gate findings")
    retrieved_protocols = ArrayField(models.UUIDField(), default=list, blank=True)
    # The "Certified" Artifact
    final_report = models.JSONField(null=True, blank=True, help_text="MedGemma output or Refusal notice")
    
    # --- NEW: AGENTIC AUDIT TRACE ---
    # Stores the step-by-step reasoning log (e.g., "Retrieving rules...", "Executing Gate...")
    agent_trace = models.JSONField(default=list, blank=True, help_text="Execution Log")

    # Communication Log
    notification_sent = models.BooleanField(default=False)
    notification_channel = models.CharField(max_length=255, blank=True) # e.g., "WhatsApp"

    def __str__(self):
        return f"{self.case_id} - {self.status}"