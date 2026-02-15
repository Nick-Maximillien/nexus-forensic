from datetime import datetime
from django.utils import timezone

# Core Logic imports (Layer 2)
# These contracts define the structure for audit planning and final verdict results
from apps.forensic_domain.contract import ForensicAuditPlan, ForensicVerdict
from apps.forensic_domain.precision import ForensicGateLayer
from apps.forensic_rag.retrieval import ForensicRAG
from apps.forensic_rag.utils import get_embedding

# Models & Comms
# Handles persistence of audit tasks and external notification triggers
from apps.forensic_agent.models import AuditTask
from apps.forensic_agent.communication import NotificationService

class ForensicIoTAgent:
    """
    Layer 3 Agent: Specialized for high-frequency, low-latency IoT streams.
    This agent bypasses heavy LLM narration to focus purely on the enforcement
    of deterministic logic gates against real-time telemetry.
    """

    def __init__(self, case_id: str):
        """
        Initializes the agent with a specific case identifier for audit tracking.
        """
        self.case_id = case_id

    def run_iot_check(self, sensor_data: dict, scope: str = "facility"):
        """
        Ingests JSON sensor data, retrieves relevant infrastructure rules,
        executes deterministic gates, and triggers alerts on failure.
        """
        
        # 1. Initialization: Create a lightweight AuditTask record for the telemetry event
        # The agent trace provides a step-by-step log for forensic observability
        task = AuditTask.objects.create(
            case_id=self.case_id,
            claim_payload=sensor_data,
            query_intent="IoT Compliance Stream",
            status='RUNNING',
            agent_trace=[{
                "timestamp": datetime.now().isoformat(),
                "step": "INIT",
                "message": "IoT Telemetry Received",
                "status": "INFO"
            }]
        )

        try:
            # 2. Query Construction: Synthesize sensor data into a searchable fingerprint
            # Example result: "Main Grid Power Infrastructure Status ONLINE"
            events = sensor_data.get('events', [])
            event_fingerprint = " ".join([
                f"{e.get('name')} {e.get('type')} {e.get('value')}" 
                for e in events
            ])
            
            # 3. Retrieval: Identify governing infrastructure standards (Layer 1)
            # We use the 'general' specialty context to ensure the RAG engine
            # prioritizes KQMH infrastructure and environmental rules.
            plan = ForensicAuditPlan(
                specialty_context="general", 
                event_timestamp=datetime.now().isoformat(),
                audit_scope=scope 
            )
            
            # Convert fingerprint to vector and perform similarity search against the corpus
            query_vec = get_embedding(event_fingerprint)
            rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, query_text=event_fingerprint)

            # 4. Adjudication: Execute the Deterministic Reasoning Core (Layer 2)
            # Adjudicates the numerical and state values from sensors against retrieved rules
            verdict: ForensicVerdict = ForensicGateLayer.execute_audit(
                claim_events=events,
                applicable_rules=rules
            )

            # 5. Task Finalization: Update status and serialize audit artifacts
            # We prioritize execution speed by generating a structured report without an LLM narrator
            task.status = 'CLEARED' if verdict.is_valid else 'HALTED'
            task.completed_at = timezone.now()
            
            # Create a rich summary of rules that were successfully validated
            rich_passed_rules = [{
                "code": r.rule_code,
                "protocol": r.protocol.title,
                "text": r.text_description,
                "type": r.rule_type
            } for r in verdict.passed_rules]

            # Store the final verdict for dashboard visualization
            # Setting 'mode' to 'iot_stream' triggers specialized frontend rendering
            task.verdict_json = {
                "is_valid": verdict.is_valid,
                "mode": "iot_stream", 
                "passed_rules": rich_passed_rules,
                "violations": verdict.violations
            }
            
            # Populate the final report with deterministic outcomes
            task.final_report = {
                "certification_statement": f"IoT Infrastructure Audit. Status: {task.status}",
                "compliance_matrix": [{"rule_code": r.rule_code, "status": "PASS"} for r in verdict.passed_rules],
                "llm_explanation": "Automated deterministic check of facility sensor array."
            }
            
            task.save()

            # 6. Notification: Alert the compliance officer on infrastructure failure
            # Notifications are only triggered for violations to prevent dashboard noise
            if not verdict.is_valid:
                NotificationService.send_notification(task)

            return task

        except Exception as e:
            # Catch and persist system faults during the telemetry pipeline
            task.status = 'ERROR'
            task.save()
            raise e