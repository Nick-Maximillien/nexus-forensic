import tempfile
import os
import json
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, JSONParser
from apps.forensic_agent.workflow import ForensicAuditorAgent
from apps.forensic_agent.research import ForensicResearchAgent 
from apps.forensic_agent.extraction import ClinicalExtractor
from apps.forensic_agent.models import AuditTask
from apps.forensic_agent.iot_agent import ForensicIoTAgent 

logger = logging.getLogger(__name__)

class ForensicReasoningView(APIView):
    """
    Primary orchestration entry point for the Nexus Forensic system.
    This view dispatches incoming clinical data or sensor streams to the 
    appropriate agentic pipeline based on the requested mode.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        """
        Processes forensic requests. Supports PDF document ingestion for 
        asynchronous extraction and direct JSON payloads for real-time adjudication.
        """
        # Initialize evidence container with an empty events list to ensure 
        # downstream logic gates do not fail on missing keys.
        claim_data = {"events": []}

        # [BRANCH A] Handle PDF Document Ingestion
        # This branch handles unstructured clinical evidence by routing it 
        # through the MedGemma-powered extraction pipeline.
        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            
            # Persist uploaded bytes to a temporary filesystem location for OCR processing.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            
            try:
                # Invoke the ClinicalExtractor to convert unstructured PDF into 
                # a normalized Forensic JSON schema.
                extracted_json = ClinicalExtractor.pdf_to_json(tmp_path)
                if extracted_json and isinstance(extracted_json, dict):
                    claim_data.update(extracted_json)
                
                # Maintain data integrity by ensuring the events array exists.
                if "events" not in claim_data:
                    claim_data["events"] = []
                    
            except Exception as e:
                logger.error(f"Extraction Pipeline Failed: {str(e)}")
                # Fail-safe: Provide empty evidence set to avoid breaking the reasoning agent.
                claim_data = {"events": [], "error": str(e)}
            finally:
                # Cleanup temporary file to preserve system storage.
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        # [BRANCH B] Handle Structured Evidence (JSON)
        # Used for Research mode or direct integration with Electronic Health Records (EHR).
        else:
            raw_data = request.data.get("claim_data", {})
            if isinstance(raw_data, str):
                try:
                    claim_data = json.loads(raw_data)
                except:
                    claim_data = {"events": []}
            else:
                claim_data = raw_data or {"events": []}
            
            if "events" not in claim_data:
                claim_data["events"] = []

        # Parameter Extraction for Audit Planning
        case_id = request.data.get("case_id", "AUTO-EXTRACTED")
        query = request.data.get("query", "")
        mode = request.data.get("mode", "audit") 
        specialty = request.data.get("specialty", "auto")
        
        # Determine the enforcement scope (clinical, facility, billing, or legal).
        scope = request.data.get("scope", "clinical")
        
        # --- PIPELINE DISPATCHER ---

        # [BRANCH C] IOT COMPLIANCE PIPELINE
        # Processes telemetry streams against infrastructure and environmental rules.
        if mode == "iot_stream":
            agent = ForensicIoTAgent(case_id=case_id)
            # Execute logic gates specifically tailored for sensor data thresholds.
            task = agent.run_iot_check(
                sensor_data=claim_data,
                scope=scope 
            )
            # Return an acknowledgment receipt. Verdicts are reviewed via the dashboard.
            return Response({
                "task_id": task.id,
                "status": "RECEIVED",
                "verdict": "PENDING_AUDIT" 
            })

        # [BRANCH D] CLINICAL RESEARCH PIPELINE
        # Discovery-based mode for exploring the protocol corpus without patient adjudication.
        if mode == "research":
            research_agent = ForensicResearchAgent(case_id=case_id)
            result = research_agent.run_research(
                query_text=query,
                specialty=specialty,
                scope=scope 
            )
            return Response(result)

        # [BRANCH E] FORENSIC AUDIT PIPELINE
        # The primary deterministic adjudication workflow for clinical compliance.
        patient_age = request.data.get("patient_age")
        event_timestamp = request.data.get("event_timestamp")

        # Instantiate the Auditor Agent to govern the reasoning lifecycle.
        agent = ForensicAuditorAgent(case_id=case_id)
        
        # Execute the multi-layered audit (Planning -> Retrieval -> Gating -> Rendering).
        task = agent.run_audit(
            claim_data=claim_data,
            query_text=query,
            specialty=specialty,
            patient_age=patient_age,
            event_timestamp=event_timestamp,
            scope=scope 
        )

        # Final Response Serialization
        return Response({
            "task_id": task.id,
            "case_id": task.case_id,
            "status": task.status,          
            "verdict": "VALID" if task.status == 'CLEARED' else "INVALID",
            "communication_sent": task.notification_sent,
            "audit_result": task.final_report,
            "forensic_evidence": task.verdict_json,
            "agent_trace": task.agent_trace 
        })
    
class AuditTaskListView(APIView):
    """
    Management view for the Remote Forensic Auditor Dashboard.
    Provides a chronological audit trail of all processed events and documents.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        """
        Retrieves a summary of the most recent audit tasks for system-wide monitoring.
        """
        tasks = AuditTask.objects.all().order_by('-started_at')[:20]
        data = []
        
        for t in tasks:
            # Reconstruct the audit state for frontend visualization.
            data.append({
                "id": str(t.id),
                "task_id": str(t.id),
                "case_id": t.case_id,
                "status": t.status,
                "verdict": "VALID" if t.status == 'CLEARED' else "INVALID",
                "created_at": t.started_at,
                "forensic_evidence": t.verdict_json or {},
                "audit_result": t.final_report or {},
                "claim_data": t.claim_payload,
                "agent_trace": t.agent_trace,
                "notification_channel": t.notification_channel
            })
            
        return Response(data)