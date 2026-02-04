import tempfile
import os
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, JSONParser
from apps.forensic_agent.workflow import ForensicAuditorAgent
from apps.forensic_agent.research import ForensicResearchAgent 
from apps.forensic_agent.extraction import ClinicalExtractor

class ForensicReasoningView(APIView):
    """
    API Trigger for the Forensic Auditor Agent.
    Handles both Direct JSON claims and PDF Document uploads.
    Supports modes: 'audit' (default) and 'research'.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        claim_data = {}

        # [BRANCH A] Handle PDF Upload
        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            
            try:
                # RUN THE EXTRACTOR
                claim_data = ClinicalExtractor.pdf_to_json(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        # [BRANCH B] Handle Legacy JSON (Research Mode / Direct API)
        else:
            raw_data = request.data.get("claim_data", {})
            if isinstance(raw_data, str):
                try:
                    claim_data = json.loads(raw_data)
                except:
                    claim_data = {}
            else:
                claim_data = raw_data or {}

        # 1. Extract Inputs
        case_id = request.data.get("case_id", "AUTO-EXTRACTED")
        query = request.data.get("query", "")
        mode = request.data.get("mode", "audit") 
        
        # Context parameters (Default to 'auto')
        specialty = request.data.get("specialty", "auto")
        
        # [NEW] Extract Scope (Default to 'clinical' for patient safety)
        # This prevents facility-level rules from bricking patient audits.
        scope = request.data.get("scope", "clinical")
        
        # --- PIPELINE SWITCH ---
        if mode == "research":
            # [BRANCH C] Research Pipeline (No Audit/Gating)
            research_agent = ForensicResearchAgent(case_id=case_id)
            result = research_agent.run_research(
                query_text=query,
                specialty=specialty
            )
            return Response(result)

        # --- AUDIT PIPELINE (Original) ---
        patient_age = request.data.get("patient_age")
        event_timestamp = request.data.get("event_timestamp")

        # 2. Instantiate the Auditor Agent 
        agent = ForensicAuditorAgent(case_id=case_id)
        
        # 3. Execute Workflow with SCOPE
        task = agent.run_audit(
            claim_data=claim_data,
            query_text=query,
            specialty=specialty,
            patient_age=patient_age,
            event_timestamp=event_timestamp,
            scope=scope #  Passing the scope constraint
        )

        # 4. Response
        return Response({
            "task_id": task.id,
            "case_id": task.case_id,
            "status": task.status,          
            "verdict": "VALID" if task.status == 'CLEARED' else "INVALID",
            "communication_sent": task.notification_sent,
            
            # THE AI NARRATIVE (Subject to failure/fallback)
            "audit_result": task.final_report,
            
            # --- THE CORE EVIDENCE (Deterministic Source of Truth) ---
            # This contains the raw Passed Rules and Violations directly from the Gate.
            "forensic_evidence": task.verdict_json,
            
            # The Agent Logs
            "agent_trace": task.agent_trace 
        })