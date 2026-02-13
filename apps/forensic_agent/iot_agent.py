from datetime import datetime
from django.utils import timezone

# Core Logic imports (Layer 2)
from apps.forensic_domain.contract import ForensicAuditPlan, ForensicVerdict
from apps.forensic_domain.precision import ForensicGateLayer
from apps.forensic_rag.retrieval import ForensicRAG
from apps.forensic_rag.utils import get_embedding

# Models & Comms
from apps.forensic_agent.models import AuditTask
from apps.forensic_agent.communication import NotificationService

class ForensicIoTAgent:
    """
    Layer 3 Agent: Specialized for high-frequency, low-latency IoT streams.
    Focuses purely on Logic Gate enforcement.
    """

    def __init__(self, case_id: str):
        self.case_id = case_id

    def run_iot_check(self, sensor_data: dict, scope: str = "facility"):
        """
        Ingests JSON sensor data -> Retrieves Rules -> Executes Gates -> Alerts.
        """
        # 1. Create a lightweight AuditTask record
        task = AuditTask.objects.create(
            case_id=self.case_id,
            claim_payload=sensor_data,
            query_intent="IoT Compliance Stream",
            status='RUNNING',
            agent_trace=[{
                "timestamp": datetime.now().isoformat(),
                "step": "INIT",
                "message": "📡 IoT Telemetry Received",
                "status": "INFO"
            }]
        )

        try:
            # 2. Construct Query from Sensor Data
            events = sensor_data.get('events', [])
            # Create a searchable string: "Main Grid Power Infrastructure Status ONLINE"
            event_fingerprint = " ".join([
                f"{e.get('name')} {e.get('type')} {e.get('value')}" 
                for e in events
            ])
            
            # 3. Fast Retrieval (Layer 1)
            # [FIX] Changed specialty context to 'general' to match typical KQMH ingestion tags.
            # This ensures the retriever finds infrastructure rules correctly.
            plan = ForensicAuditPlan(
                specialty_context="general", 
                event_timestamp=datetime.now().isoformat(),
                audit_scope=scope 
            )
            
            # Retrieve rules relevant to the sensor data (e.g. Generator, Water rules)
            query_vec = get_embedding(event_fingerprint)
            rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, query_text=event_fingerprint)

            # 4. Deterministic Adjudication (Layer 2)
            verdict: ForensicVerdict = ForensicGateLayer.execute_audit(
                claim_events=events,
                applicable_rules=rules
            )

            # 5. Fast Result (Skip LLM Narrative)
            task.status = 'CLEARED' if verdict.is_valid else 'HALTED'
            task.completed_at = timezone.now()
            
            # Serialize for DB
            rich_passed_rules = [{
                "code": r.rule_code,
                "protocol": r.protocol.title,
                "text": r.text_description,
                "type": r.rule_type
            } for r in verdict.passed_rules]

            # [CRITICAL] Ensure 'mode' is set so Dashboard treats this as IoT data
            task.verdict_json = {
                "is_valid": verdict.is_valid,
                "mode": "iot_stream", 
                "passed_rules": rich_passed_rules,
                "violations": verdict.violations
            }
            
            # Simple manual report for the dashboard
            task.final_report = {
                "certification_statement": f"IoT Infrastructure Audit. Status: {task.status}",
                "compliance_matrix": [{"rule_code": r.rule_code, "status": "PASS"} for r in verdict.passed_rules],
                "llm_explanation": "Automated deterministic check of facility sensor array."
            }
            
            task.save()

            # 6. Alerting (Layer 3)
            # Only alert on failure (HALTED) to avoid spamming the auditor for passing checks
            if not verdict.is_valid:
                NotificationService.send_notification(task)

            return task

        except Exception as e:
            task.status = 'ERROR'
            task.save()
            raise e