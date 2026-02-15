from datetime import datetime
from django.utils import timezone
from django.db import transaction

# Persistence layer for audit tracking
from apps.forensic_agent.models import AuditTask

# Capabilities for retrieval and synthesis
from apps.forensic_rag.retrieval import ForensicRAG
from apps.forensic_rag.utils import get_embedding
from apps.forensic_domain.contract import ForensicAuditPlan
from apps.llm_interface.medgemma_renderer import generate_research_summary

class ForensicResearchAgent:
    """
    Parallel pipeline for Auditable Research.
    Retrieves immutable truths (Rules) and synthesizes them without
    performing a compliance audit on claim data.
    Provides system-grade visibility into the scope and intent of clinical guidelines.
    """

    def __init__(self, case_id: str):
        """
        Initialize the agent with a specific case identifier for session tracking.
        """
        self.case_id = case_id

    def _log(self, task: AuditTask, step: str, message: str, status: str = "INFO"):
        """
        Appends a structured log entry to the agent trace field for forensic observability.
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
        # Update only the trace field to prevent overwriting other concurrent updates
        task.save(update_fields=['agent_trace'])

    def run_research(self, query_text: str, specialty: str = "auto", scope: str = None) -> dict:
        """
        Executes the Research Pipeline with full observability.
        Accepts scope to allow filtered research (e.g., facility only),
        but defaults to universal search if not specified.
        """
        start_time = timezone.now()

        with transaction.atomic():
            # 1. INITIALIZE TASK
            # Create a database record for this research session
            task = AuditTask.objects.create(
                case_id=self.case_id,
                claim_payload={"mode": "research", "specialty": specialty, "scope": scope},
                query_intent=query_text,
                status='RUNNING'
            )
            
            self._log(task, "INIT", f"Research Agent Activated. Query: '{query_text}'")

            try:
                # 2. PLAN
                # Establish the search parameters and planning context
                scope_log = scope.upper() if scope else "ALL (UNIVERSAL)"
                self._log(task, "PLANNING", f"Setting research context: {specialty} | Scope: {scope_log}")
                
                plan = ForensicAuditPlan(
                    specialty_context=specialty,
                    event_timestamp=datetime.now().isoformat(),
                    active_protocols_only=True,
                    audit_scope=scope 
                )

                # 3. RETRIEVE
                # Search the medical corpus using vector embeddings
                self._log(task, "RETRIEVAL", "Scanning Clinical Corpus for immutable truths...")

                query_vec = get_embedding(query_text)
                rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, query_text)
                
                # Store the protocol IDs associated with retrieved rules for provenance
                task.retrieved_protocols = [
                    getattr(r, "protocol_id", None) for r in rules
                ]
                task.save(update_fields=["retrieved_protocols"])

                # Handle scenarios where no clinical protocols match the query parameters
                if not rules:
                    self._log(task, "HALT", "No clinical protocols found matching query.", "WARNING")
                    
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

                self._log(task, "RETRIEVAL", f"Retrieved {len(rules)} relevant citations.")

                # 4. SYNTHESIZE
                # Use MedGemma to generate a grounded explanation based on the retrieved rules
                self._log(task, "SYNTHESIS", "Invoking MedGemma for grounded explanation...")
                
                research_output = generate_research_summary(query_text, rules) or {}

                # 5. STRUCTURE THE EVIDENCE
                # Compile a structured packet of retrieved clinical facts for the frontend
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
                        "scope": r.scope_tags,   # Deliver full applicable scopes
                        "intent": r.intent_tags, # Deliver intent context
                        "logic": r.logic_config
                    })

                self._log(task, "FINISH", "Research complete.", "SUCCESS")

                # 6. FINALIZE
                # Update task state and store the final synthesized report
                task.status = 'COMPLETED'
                task.completed_at = timezone.now()
                
                task.verdict_json = {
                    "mode": "research",
                    "retrieved_facts": evidence_packet
                }
                
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
                # Catch and log system failures during the agentic workflow
                self._log(task, "CRASH", f"System Failure: {str(e)}", "CRITICAL")
                task.status = 'ERROR'
                task.save()
                raise e