import json
import logging
import os
import vertexai
from vertexai.generative_models import GenerativeModel
from apps.forensic_corpus.ingestion.parser import BaseParser 

logger = logging.getLogger(__name__)

# ----------------------------
#  Setup GCP Credentials & Init
# ----------------------------
if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].replace("\\", "/")

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = "us-central1"

try:
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
except Exception as e:
    logger.error(f"Vertex AI init failed in Extractor: {e}")


class ClinicalExtractor:
    """
    The Bridge: Converts Unstructured PDF -> Structured Forensic JSON.
    Maintains precision by strictly prompting for ISO timestamps and exact values.
    """
    
    @staticmethod
    def pdf_to_json(file_path: str) -> dict:
        # 1. High-Fidelity OCR (Reuse your existing Docling Parser)
        try:
            parser = BaseParser() 
            markdown_text = parser.extract_markdown(file_path)
            
            # --- DIAGNOSTIC LOG: SEE WHAT THE PARSER SAW ---
            # This will print the first 2000 chars to your logs. 
            # If this is empty or garbage, Docling is broken.
            logger.info(f"\n🔎 [DOCLING VISION START] File: {file_path}")
            logger.info(f"{markdown_text[:2000]}...") 
            logger.info("🔎 [DOCLING VISION END]\n")
            
        except Exception as e:
            logger.error(f"Docling failed to read file: {e}")
            return {"events": []}

        # 2. The Normalization Prompt (Updated with Administrative Rules)
        prompt = f"""
        You are a Clinical & Forensic Data Normalizer.
        TASK: Convert this medical/compliance document into a structured JSON Timeline.
        
        RULES:
        1. Extract clinical events: Meds, procedures, vitals, assessments.
        2. Extract ADMINISTRATIVE EVIDENCE: Licenses, Policy Statements, Governance Minutes, Compliance Logs.
        3. TIMESTAMP: Use strict ISO 8601 (YYYY-MM-DDTHH:MM:SSZ). Use document date if time is unknown.
        4. NAMES: Use the exact title of the log, section, or artifact found in the text.
        
        OUTPUT SCHEMA:
        {{
            "events": [
                {{ "name": "Event Name", "timestamp": "ISO_String", "value": 1.0, "unit": "mg", "type": "Category", "source": "Quote from text" }}
            ]
        }}

        DOCUMENT CONTENT:
        {markdown_text[:30000]} 
        """

        # 3. Call Vertex AI
        try:
            model = GenerativeModel("gemini-2.5-flash") 
            
            response = model.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"}
            )
            
            # --- DIAGNOSTIC LOG: SEE WHAT THE BRAIN EXTRACTED ---
            logger.info(f"\n🧠 [LLM EXTRACTION RAW]:\n{response.text}\n")
            
            return json.loads(response.text)
            
        except Exception as e:
            logger.error(f"LLM Extraction Failed: {e}")
            return {"events": []}