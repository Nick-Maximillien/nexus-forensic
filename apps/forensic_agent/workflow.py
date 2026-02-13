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

        # Step 1: Initialize Task outside transaction to ensure it exists if logic fails
        task = AuditTask.objects.create(
            case_id=self.case_id,
            claim_payload=claim_data,
            query_intent=query_text,
            status='RUNNING'
        )
        
        self._log(task, "INIT", f"🚀 Forensic Agent Activated. Case: {self.case_id}")

        try:
            # Entire forensic adjudication is atomic
            with transaction.atomic():

                # 2. PLAN (Forensic Audit Plan)
                self._log(task, "PLANNING", f"Intent: '{query_text}' | Scope: {scope.upper()} | Specialty: {specialty}")
                
                plan = ForensicAuditPlan(
                    specialty_context=specialty,
                    patient_age=patient_age,
                    event_timestamp=event_timestamp,
                    active_protocols_only=True,
                    audit_scope=scope 
                )

                # 3. CONTENT-AWARE RETRIEVAL (Wire 2 Upgrade)
                extracted_events = claim_data.get('events', [])
                event_fingerprint = " ".join([e.get('name', '') for e in extracted_events if e.get('name')])
                enriched_query = f"{query_text} {event_fingerprint}"
                
                self._log(task, "RETRIEVAL", f"🔍 Scanning Clinical Corpus for extracted events: {event_fingerprint[:100]}...")
                
                query_vec = get_embedding(enriched_query)
                rules = ForensicRAG.retrieve_applicable_rules(query_vec, plan, enriched_query)

                # Persist protocol provenance
                task.retrieved_protocols = [
                    getattr(r, "protocol_id", None) for r in rules
                ]
                # No save here, we do it in finalize inside the transaction
                
                self._log(task, "RETRIEVAL", f"✅ Found {len(rules)} relevant forensic rules.")

                # [LOGIC BRANCH]: No Law Found → HALT
                if not rules:
                    self._log(task, "HALT", "⛔ No applicable clinical protocols found.", "WARNING")
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
                    # 4. VALIDATE (Forensic Gate)
                    event_count = len(extracted_events)

                    has_identity = any([
                        claim_data.get('patient'),
                        claim_data.get('patient_name'),
                        claim_data.get('medical_record_number'),
                        claim_data.get('mrn'),
                        'patient' in str(claim_data).lower()[:2000], 
                        'mrn' in str(claim_data).lower()[:2000]
                    ])

                    is_medical_content = has_identity or (event_count > 3)

                    if scope == "clinical" and not is_medical_content:
                        self._log(task, "HALT", "⛔ Non-Medical Content Detected. (Missing Patient Identity or Clinical Density).", "ERROR")
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
                             self._log(task, "WARNING", "⚠️ Zero events extracted from claim. Audit may default to Missing Evidence.", "WARNING")

                        self._log(task, "REASONING", f"⚖️ Adjudicating {event_count} clinical events against {len(rules)} rules...")
                        
                        verdict: ForensicVerdict = ForensicGateLayer.execute_audit(
                            claim_events=extracted_events,
                            applicable_rules=rules
                        )

                        # 5. AGENTIC EXPLANATION
                        self._log(task, "RENDERING", "📝 Invoking Forensic LLM for explanation...")
                        report_json_str = generate_forensic_report(claim_data, verdict)
                        
                        final_status = 'CLEARED' if verdict.is_valid else 'HALTED'
                        
                        if verdict.is_valid:
                            self._log(task, "VERDICT", "✅ CLEARED: Clinical logic holds.", "SUCCESS")
                        else:
                            violation_count = len(verdict.violations)
                            self._log(task, "VERDICT", f"❌ INVALID: {violation_count} Critical Violations detected.", "ERROR")

                        task = self._finalize_task(
                            task,
                            final_status,
                            verdict,
                            final_report=report_json_str 
                        )

            # 6. COMMUNICATION TRIGGER (OUTSIDE Transaction)
            # This prevents network timeouts from bricking the database or hanging the worker.
            NotificationService.send_notification(task)
            return task

        except Exception as e:
            self._log(task, "CRASH", f"🔥 System Failure: {str(e)}", "CRITICAL")
            task.status = 'ERROR'
            task.final_report = {"system_error": str(e)}
            task.completed_at = timezone.now()
            task.save()
            raise e

    def _finalize_task(self, task, status, verdict_obj, final_report=None):
        """
        Updates state and serializes artifacts. 
        Note: This is called within the atomic block of run_audit.
        """
        task.status = status
        task.completed_at = timezone.now()

        # Serialize Verdict Logic
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

        # Final Report Handling
        if final_report:
            task.final_report = final_report
        else:
            task.final_report = task.verdict_json
        
        self._log(task, "FINISH", f"🏁 Process Complete. Status: {status}")
        task.save()
        return task