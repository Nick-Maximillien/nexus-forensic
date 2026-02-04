from datetime import datetime
from django.utils import timezone
from django.db import transaction

# Persistence
from apps.forensic_agent.models import AuditTask

# Capabilities
from apps.forensic_rag.retrieval import ForensicRAG
from apps.forensic_rag.utils import get_embedding
from apps.forensic_domain.contract import ForensicAuditPlan
from apps.llm_interface.medgemma_renderer import generate_research_summary

class ForensicResearchAgent:
    """
    Parallel pipeline for 'Auditable Research'.
    Retrieves immutable truths (Rules) and synthesizes them without
    performing a compliance audit on claim data.
    Now upgraded to support System Grade Scope and Intent visibility.
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
        current_trace = task.agent_trace or []
        current_trace.append(entry)
        task.agent_trace = current_trace
        task.save(update_fields=['agent_trace'])

    def run_research(self, query_text: str, specialty: str = "auto", scope: str = None) -> dict:
        """
        Executes the Research Pipeline with Full Observability.
        [UPGRADE] Accepts 'scope' to allow filtered research (e.g., "facility only"),
        but defaults to None (Universal Search) if not specified.
        """
        start_time = timezone.now()

        with transaction.atomic():
            # 1. INITIALIZE TASK
            task = AuditTask.objects.create(
                case_id=self.case_id,
                claim_payload={"mode": "research", "specialty": specialty, "scope": scope},
                query_intent=query_text,
                status='RUNNING'
            )
            
            self._log(task, "INIT", f"🧪 Research Agent Activated. Query: '{query_text}'")

            try:
                # 2. PLAN
                scope_log = scope.upper() if scope else "ALL (UNIVERSAL)"
                self._log(task, "PLANNING", f"Setting research context: {specialty} | Scope: {scope_log}")
                
                plan = ForensicAuditPlan(
                    specialty_context=specialty,
                    event_timestamp=datetime.now().isoformat(),
                    active_protocols_only=True,
                    audit_scope=scope # [UPGRADE] Pass scope (or None for broad search)
                )

                # 3. RETRIEVE
                self._log(task, "RETRIEVAL", "🔍 Scanning Clinical Corpus for immutable truths...")

                query_vec = get_embedding(query_text)
                rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, query_text)
                
                task.retrieved_protocols = [
                    getattr(r, "protocol_id", None) for r in rules
                ]
                task.save(update_fields=["retrieved_protocols"])

                if not rules:
                    self._log(task, "HALT", "⛔ No clinical protocols found matching query.", "WARNING")
                    
                    task.status = 'HALTED'
                    task.final_report = {
                        "llm_explanation": "No clinical protocols found matching your query."
                    }
                    task.completed_at = timezone.now()
                    task.save()
                    
                    return {
                        "task_id": str(task.id),
                        "status": "HALTED",
                        "verdict": "UNKNOWN",
                        "audit_result": task.final_report, 
                        "forensic_evidence": { "retrieved_facts": [] }, 
                        "agent_trace": task.agent_trace
                    }

                self._log(task, "RETRIEVAL", f"✅ Retrieved {len(rules)} relevant citations.")

                # 4. SYNTHESIZE
                self._log(task, "SYNTHESIS", "📝 Invoking MedGemma for grounded explanation...")
                
                # [FIX] Safety check added here
                research_output = generate_research_summary(query_text, rules) or {}

                # 5. STRUCTURE THE EVIDENCE
                # [UPGRADE] Inject Scope and Intent tags into the evidence packet
                evidence_packet = []
                for r in rules:
                    evidence_packet.append({
                        "rule_code": r.rule_code,
                        "protocol": {
                            "title": r.protocol.title,
                            "version": r.protocol.version,
                            "issuing_body": r.protocol.issuing_body
                        },
                        "text": r.text_description,
                        "type": r.rule_type,
                        "scope": r.scope_tags,   # [NEW] Deliver full applicable scopes
                        "intent": r.intent_tags, # [NEW] Deliver intent context
                        "logic": r.logic_config
                    })

                self._log(task, "FINISH", "🏁 Research complete.", "SUCCESS")

                # 6. FINALIZE
                task.status = 'COMPLETED'
                task.completed_at = timezone.now()
                
                task.verdict_json = {
                    "mode": "research",
                    "retrieved_facts": evidence_packet
                }
                
                # [FIX] Safe access using .get() now works because research_output is guaranteed dict
                task.final_report = {
                    "llm_explanation": research_output.get("explanation", "Analysis unavailable.")
                }
                
                task.save()

                return {
                    "task_id": str(task.id),
                    "status": "COMPLETED",
                    "verdict": "VALID", 
                    "audit_result": task.final_report, 
                    "forensic_evidence": task.verdict_json,
                    "agent_trace": task.agent_trace
                }

            except Exception as e:
                self._log(task, "CRASH", f" System Failure: {str(e)}", "CRITICAL")
                task.status = 'ERROR'
                task.save()
                raise e