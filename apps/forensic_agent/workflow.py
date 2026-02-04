from datetime import datetime
from django.utils import timezone
from django.db import transaction

# Import Capabilities
from apps.forensic_domain.contract import ForensicAuditPlan, ForensicVerdict
from apps.forensic_domain.precision import ForensicGateLayer
from apps.forensic_rag.retrieval import ForensicRAG
from apps.forensic_rag.utils import get_embedding
from apps.llm_interface.medgemma_renderer import generate_forensic_report

# Import Persistence & Comms
from apps.forensic_agent.models import AuditTask
from apps.forensic_agent.communication import NotificationService


class ForensicAuditorAgent:
    """
    Agent that governs the audit lifecycle.
    Encapsulates Planning, Retrieval, Gating, and Rendering.
    Now with live 'Thought Trace' logging.
    """

    def __init__(self, case_id: str):
        self.case_id = case_id

    def _log(self, task: AuditTask, step: str, message: str, status: str = "INFO"):
        """
        Appends a structured log entry to the agent trace.
        """
        entry = {
            "timestamp": timezone.now().isoformat(),
            "step": step,
            "message": message,
            "status": status
        }
        # Append to the DB object field
        current_trace = task.agent_trace or []
        current_trace.append(entry)
        task.agent_trace = current_trace
        task.save(update_fields=['agent_trace'])

    def run_audit(
        self,
        claim_data: dict,
        query_text: str,
        specialty: str = "auto",
        patient_age: int = None,
        event_timestamp: str = None,
        scope: str = "clinical" # [NEW] Scope Parameter (System Grade Evolution)
    ) -> AuditTask:
        """
        Executes the full Forensic Pipeline.
        """

        if not event_timestamp:
            event_timestamp = datetime.now().isoformat()

        # Entire forensic action is atomic by design
        with transaction.atomic():

            # 1. INITIALIZE TASK (Persistence)
            task = AuditTask.objects.create(
                case_id=self.case_id,
                claim_payload=claim_data,
                query_intent=query_text,
                status='RUNNING'
            )
            
            self._log(task, "INIT", f"🚀 Forensic Agent Activated. Case: {self.case_id}")

            try:
                # 2. PLAN (Forensic Audit Plan)
                # [UPGRADE] Log includes Scope for auditability
                self._log(task, "PLANNING", f"Intent: '{query_text}' | Scope: {scope.upper()} | Specialty: {specialty}")
                
                plan = ForensicAuditPlan(
                    specialty_context=specialty,
                    patient_age=patient_age,
                    event_timestamp=event_timestamp,
                    active_protocols_only=True,
                    audit_scope=scope # [NEW] Passing scope to the contract
                )

                # 3. RETRIEVE (Forensic RAG)
                self._log(task, "RETRIEVAL", "🔍 Scanning Clinical Corpus (Vector + Keyword)...")
                
                query_vec = get_embedding(query_text)
                rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, query_text)

                # Persist protocol provenance (law applied)
                task.retrieved_protocols = [
                    getattr(r, "protocol_id", None) for r in rules
                ]
                task.save(update_fields=["retrieved_protocols"])
                
                self._log(task, "RETRIEVAL", f"✅ Found {len(rules)} relevant forensic rules.")

                # [LOGIC BRANCH]: No Law Found → HALT
                if not rules:
                    self._log(task, "HALT", "⛔ No applicable clinical protocols found.", "WARNING")
                    return self._finalize_task(
                        task,
                        'HALTED',
                        {
                            "is_valid": False,
                            "reason": "INSUFFICIENT_PROTOCOL",
                            "violations": [
                                {"violation": "No active clinical protocol found for this scenario."}
                            ]
                        }
                    )

                # 4. VALIDATE (Forensic Gate)
                event_count = len(claim_data.get('events', []))
                self._log(task, "REASONING", f"⚖️ Adjudicating {event_count} clinical events against {len(rules)} rules...")
                
                # Deterministic execution — NO LLM
                verdict: ForensicVerdict = ForensicGateLayer.execute_audit(
                    claim_events=claim_data.get('events', []),
                    applicable_rules=rules
                )

                # 5. AGENTIC EXPLANATION (Run LLM regardless of pass/fail)
                # We want the LLM to explain the violations if they exist.
                self._log(task, "RENDERING", "📝 Invoking Forensic LLM for explanation...")
                
                report_json_str = generate_forensic_report(claim_data, verdict)
                
                # 6. FINALIZE STATUS based on verdict validity
                final_status = 'CLEARED' if verdict.is_valid else 'HALTED'
                
                if verdict.is_valid:
                    self._log(task, "VERDICT", "✅ CLEARED: Clinical logic holds.", "SUCCESS")
                else:
                    violation_count = len(verdict.violations)
                    self._log(task, "VERDICT", f"❌ INVALID: {violation_count} Critical Violations detected.", "ERROR")

                return self._finalize_task(
                    task,
                    final_status,
                    verdict,
                    final_report=report_json_str # The LLM report is now always attached
                )

            except Exception as e:
                self._log(task, "CRASH", f"🔥 System Failure: {str(e)}", "CRITICAL")
                # System-level failure (non-forensic)
                task.status = 'ERROR'
                task.final_report = {"system_error": str(e)}
                task.completed_at = timezone.now()
                task.save()
                raise e

    def _finalize_task(self, task, status, verdict_obj, final_report=None):
        """
        Updates state, saves artifacts, and triggers communication loop.
        """
        task.status = status
        task.completed_at = timezone.now()

        # Serialize Verdict Logic
        if isinstance(verdict_obj, ForensicVerdict):
             # Create rich passed rules list logic preserved
            rich_passed_rules = []
            for r in verdict_obj.passed_rules:
                # Assuming r is a ForensicRule model instance
                rich_passed_rules.append({
                    "code": r.rule_code,
                    "protocol": r.protocol.title,
                    "protocol_version": r.protocol.version,
                    "text": r.text_description,
                    "type": r.rule_type
                })

            task.verdict_json = {
                "is_valid": verdict_obj.is_valid,
                "passed_rules": rich_passed_rules,
                "violations": verdict_obj.violations
            }
        else:
            task.verdict_json = verdict_obj

        # Final Report Handling
        if final_report:
            task.final_report = final_report
        else:
            task.final_report = task.verdict_json
        
        self._log(task, "FINISH", f"🏁 Process Complete. Status: {status}")
        task.save()

        # 6. COMMUNICATION TRIGGER (Closed-Loop Agentic Safety)
        NotificationService.send_notification(task)

        return task