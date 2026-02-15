from datetime import datetime
from django.utils import timezone
from django.db import transaction

# Import internal modules for forensic logic, retrieval, and report generation
from apps.forensic_domain.contract import ForensicAuditPlan, ForensicVerdict
from apps.forensic_domain.precision import ForensicGateLayer
from apps.forensic_rag.retrieval import ForensicRAG
from apps.forensic_rag.utils import get_embedding
from apps.llm_interface.medgemma_renderer import generate_forensic_report

# Import persistence and communication services
from apps.forensic_agent.models import AuditTask
from apps.forensic_agent.communication import NotificationService


class ForensicAuditorAgent:
    """
    Orchestrates the lifecycle of a forensic medical audit or research.
    Manages the transitions between planning, protocol retrieval, 
    deterministic logic gating, and natural language report generation.
    """

    def __init__(self, case_id: str):
        """
        Initializes the agent with a specific case identifier.
        """
        self.case_id = case_id

    def _log(self, task: AuditTask, step: str, message: str, status: str = "INFO"):
        """
        Records an execution step in the agent's thought trace for auditability.
        Updates the agent_trace JSON field in the database.
        """
        entry = {
            "timestamp": timezone.now().isoformat(),
            "step": step,
            "message": message,
            "status": status
        }
        # Retrieve and update the current trace from the task record
        current_trace = task.agent_trace or []
        current_trace.append(entry)
        task.agent_trace = current_trace
        # Perform a partial save to ensure log persistence
        task.save(update_fields=['agent_trace'])

    def run_audit(
        self,
        claim_data: dict,
        query_text: str,
        specialty: str = "auto",
        patient_age: int = None,
        event_timestamp: str = None,
        scope: str = "clinical"
    ) -> AuditTask:
        """
        Executes the full forensic audit pipeline from ingestion to final verdict.
        
        Steps:
        1. Initialization and Task creation.
        2. Audit Planning (context setting).
        3. RAG-based protocol retrieval.
        4. Medical density and identity validation.
        5. Deterministic logic gate execution.
        6. Agentic report generation.
        """

        if not event_timestamp:
            event_timestamp = datetime.now().isoformat()

        # Step 1: Create the persistence record for the audit task
        task = AuditTask.objects.create(
            case_id=self.case_id,
            claim_payload=claim_data,
            query_intent=query_text,
            status='RUNNING'
        )
        
        self._log(task, "INIT", f"Forensic Agent Activated. Case: {self.case_id}")

        try:
            # Encapsulate the audit logic in a transaction to ensure data consistency
            with transaction.atomic():

                # Step 2: Establish the Forensic Audit Plan (Scope and Context)
                self._log(task, "PLANNING", f"Intent: '{query_text}' | Scope: {scope.upper()} | Specialty: {specialty}")
                
                plan = ForensicAuditPlan(
                    specialty_context=specialty,
                    patient_age=patient_age,
                    event_timestamp=event_timestamp,
                    active_protocols_only=True,
                    audit_scope=scope 
                )

                # Step 3: Retrieve applicable protocols via Content-Aware Retrieval (RAG)
                extracted_events = claim_data.get('events', [])
                event_fingerprint = " ".join([e.get('name', '') for e in extracted_events if e.get('name')])
                enriched_query = f"{query_text} {event_fingerprint}"
                
                self._log(task, "RETRIEVAL", f"Scanning Clinical Corpus for extracted events: {event_fingerprint[:100]}...")
                
                query_vec = get_embedding(enriched_query)
                rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, enriched_query)

                # Store the IDs of retrieved protocols for transparency
                task.retrieved_protocols = [
                    getattr(r, "protocol_id", None) for r in rules
                ]
                
                self._log(task, "RETRIEVAL", f"Found {len(rules)} relevant forensic rules.")

                # Halt if no governing protocols are found in the knowledge base
                if not rules:
                    self._log(task, "HALT", "No applicable clinical protocols found.", "WARNING")
                    task = self._finalize_task(
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
                else:
                    # Step 4: Validate document density and medical identity
                    event_count = len(extracted_events)

                    has_identity = any([
                        claim_data.get('patient'),
                        claim_data.get('patient_name'),
                        claim_data.get('medical_record_number'),
                        claim_data.get('mrn'),
                        'patient' in str(claim_data).lower()[:2000], 
                        'mrn' in str(claim_data).lower()[:2000]
                    ])

                    # Basic heuristic to ensure the document is a valid medical record
                    is_medical_content = has_identity or (event_count > 3)

                    if scope == "clinical" and not is_medical_content:
                        self._log(task, "HALT", "Non-Medical Content Detected. (Missing Patient Identity or Clinical Density).", "ERROR")
                        task = self._finalize_task(
                            task,
                            'HALTED',
                            {
                                "is_valid": False,
                                "reason": "NON_MEDICAL_DOCUMENT",
                                "violations": [
                                    {
                                        "violation": "Audit failed: Document lacks essential medical context (MRN/Identity) or clinical data density required for adjudication."
                                    }
                                ]
                            }
                        )
                    else:
                        if event_count == 0:
                             self._log(task, "WARNING", "Zero events extracted from claim. Audit may default to Missing Evidence.", "WARNING")

                        # Step 5: Execute Deterministic Adjudication (Forensic Gate Layer)
                        self._log(task, "REASONING", f"Adjudicating {event_count} clinical events against {len(rules)} rules...")
                        
                        verdict: ForensicVerdict = ForensicGateLayer.execute_audit(
                            claim_events=extracted_events,
                            applicable_rules=rules
                        )

                        # Step 6: Generate Agentic Explanation via MedGemma
                        self._log(task, "RENDERING", "Invoking Medgemma for explanation...")
                        report_json_str = generate_forensic_report(claim_data, verdict)
                        
                        final_status = 'CLEARED' if verdict.is_valid else 'HALTED'
                        
                        if verdict.is_valid:
                            self._log(task, "VERDICT", "CLEARED: Clinical logic holds.", "SUCCESS")
                        else:
                            violation_count = len(verdict.violations)
                            self._log(task, "VERDICT", f"INVALID: {violation_count} Critical Violations detected.", "ERROR")

                        # Update task status and persist results
                        task = self._finalize_task(
                            task,
                            final_status,
                            verdict,
                            final_report=report_json_str 
                        )

            # Step 7: Post-Audit Communication
            # Triggered outside the transaction to prevent external network delays from affecting DB integrity
            NotificationService.send_notification(task)
            return task

        except Exception as e:
            # Log system crashes and mark task as failed
            self._log(task, "CRASH", f"System Failure: {str(e)}", "CRITICAL")
            task.status = 'ERROR'
            task.final_report = {"system_error": str(e)}
            task.completed_at = timezone.now()
            task.save()
            raise e

    def _finalize_task(self, task, status, verdict_obj, final_report=None):
        """
        Serializes audit artifacts and updates the final task state.
        Ensures passed rules and violations are stored in a queryable JSON format.
        """
        task.status = status
        task.completed_at = timezone.now()

        # Serialize protocol details and rule logic for the final verdict
        if isinstance(verdict_obj, ForensicVerdict):
            rich_passed_rules = []
            for r in verdict_obj.passed_rules:
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

        # Assign the final narrative report if provided
        if final_report:
            task.final_report = final_report
        else:
            task.final_report = task.verdict_json
        
        self._log(task, "FINISH", f"Process Complete. Status: {status}")
        task.save()
        return task