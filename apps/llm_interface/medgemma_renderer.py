import json
import logging
import os
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from django.conf import settings
from apps.forensic_domain.contract import ForensicVerdict

# Logging configuration for audit traceability
logger = logging.getLogger(__name__)


# GCP Infrastructure Configuration

if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].replace("\\", "/")

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
GCP_ENDPOINT_ID = os.getenv("GCP_MEDGEMMA_ENDPOINT_ID")

# [TOGGLE] Master Switch: Set True for local/Kaggle, False for GCP Vertex AI
OFFLINE_EDGE = getattr(settings, 'OFFLINE_EDGE', True)

# [CONFIG] Local Development Endpoint (Ngrok tunnel to Kaggle)
MEDGEMMA_LOCAL_URL = "https://tinselly-winged-kandi.ngrok-free.dev/medgemma"

_VERTEX_INITIALIZED = False

def _ensure_vertex_init():
    """
    Lazy initialization for Vertex AI to ensure gRPC safety in 
    multiprocess environments (Gunicorn/Celery).
    """
    global _VERTEX_INITIALIZED
    if _VERTEX_INITIALIZED:
        return True
    
    try:
        from google.cloud import aiplatform
        aiplatform.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
        _VERTEX_INITIALIZED = True
        return True
    except Exception as e:
        logger.error(f"Vertex AI initialization failed: {str(e)}")
        return False


# Utility Functions

def sanitize_prompt(prompt: str) -> str:
    """
    Prevents context overflow by truncating prompts to 20k characters.
    """
    if len(prompt) > 20000: 
        prompt = prompt[:20000] + "\n\n[TRUNCATED]"
    return prompt

def _clean_json_response(raw_text: str) -> dict:
    """
    Surgical extraction of JSON from LLM output. 
    Handles markdown blocks and trailing text to ensure 
    system stability.
    """
    try:
        raw_text = raw_text.strip()
        # Remove Markdown formatting
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        
        # Locate the JSON object boundaries
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw_text[start:end+1])
        
        return json.loads(raw_text)
    except Exception as e:
        logger.error(f"Failed to parse JSON from MedGemma: {str(e)}")
        raise

def _create_robust_session():
    """
    Network resilience layer for local Ngrok tunnels.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
    return session

# ------------------------------------------------
# MedGemma Narrative Engine (Inference Dispatcher)
# ------------------------------------------------

def _medgemma_narrator(prompt: str, max_tokens: int = 1024) -> str:
    """
    The Unified Narrator.
    Routes generation requests to the appropriate MedGemma backend.
    """
    if OFFLINE_EDGE:
        # Local/Kaggle Branch via Ngrok
        headers = {
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true"
        }
        payload = {
            "prompt": prompt,
            "temperature": 0.1, 
            "max_new_tokens": max_tokens
        }
        try:
            with _create_robust_session() as session:
                response = session.post(MEDGEMMA_LOCAL_URL, json=payload, headers=headers, timeout=120)
                if response.status_code == 200:
                    return response.json().get("response", "")
        except Exception as e:
            logger.error(f"Local MedGemma failed: {e}")
            return None
    else:
        # Cloud Branch via Vertex AI Endpoint
        if not _ensure_vertex_init():
            return None
        
        try:
            from google.cloud import aiplatform
            endpoint = aiplatform.Endpoint(GCP_ENDPOINT_ID)
            
            # Formatting prompt for the open-weights model deployment
            instances = [{"content": prompt}]
            parameters = {
                "temperature": 0.1,
                "max_output_tokens": max_tokens,
                "top_p": 0.9
            }
            
            response = endpoint.predict(instances=instances, parameters=parameters)
            prediction = response.predictions[0]
            # Standard Vertex AI response handling
            if isinstance(prediction, dict):
                return prediction.get('content', '')
            return str(prediction)
        except Exception as e:
            logger.error(f"Cloud MedGemma failed: {e}")
            return None


# Primary Interface Functions


def generate_forensic_report(claim_data: dict, verdict: ForensicVerdict) -> dict:
    """
    NARRATIVE COMPONENT: Translates deterministic verdicts into 
    professional medical-legal reports.
    
    This function uses MedGemma to explain the "Reasoning Trace" 
    generated by the Python logic gates.
    """
    # Build Evidence Context
    events_str = "\n".join([f"- {e.get('name')}" for e in claim_data.get('events', [])])
    passed_str = "\n".join([f"- {r.rule_code}" for r in verdict.passed_rules])
    
    violations_str = "NONE"
    if not verdict.is_valid:
        violations_str = "\n".join([f"- {v['rule']['code']}: {v['validation_trace']}" for v in verdict.violations])

    # Construct the instruction for the Narrator
    system_directive = f"""
    You are MedGemma, a Forensic Clinical Narrator.
    Your task is to summarize a deterministic audit outcome.
    
    AUDIT RESULT: {"VALID" if verdict.is_valid else "INVALID"}
    
    INSTRUCTIONS:
    1. If VALID: Write a professional certification of compliance.
    2. If INVALID: Explain the violations based strictly on the provided traces.
    3. Categorize by Intent: Safety, Quality, or Administrative.
    4. Output strictly as JSON.
    """

    prompt = f"{system_directive}\n\nEVENTS:\n{events_str}\n\nVIOLATIONS:\n{violations_str}\n\nRESPONSE JSON:"
    
    raw_res = _medgemma_narrator(sanitize_prompt(prompt))
    
    if raw_res:
        try:
            return _clean_json_response(raw_res)
        except:
            pass

    # Hard Fallback in case of total model failure
    return {
        "certification_statement": "Audit complete. Narrative generation failed.",
        "compliance_matrix": [],
        "evidence_traces": []
    }

def generate_research_summary(query: str, rules: list) -> dict:
    """
    RESEARCH COMPONENT: Performs RAG (Retrieval-Augmented Generation) 
    using MedGemma to answer clinical queries based on the Ground Truth corpus.
    """
    knowledge_base = "\n".join([f"[{r.rule_code}]: {r.text_description}" for r in rules])

    prompt = f"""
    You are MedGemma, a Clinical Protocol Specialist.
    Query: {query}
    
    MANDATE: Use ONLY the sources below. Cite every claim with [Rule Code].
    If the answer is missing, state that protocols do not cover the query.
    
    SOURCES:
    {knowledge_base}
    
    SUMMARY:
    """
    
    raw_res = _medgemma_narrator(sanitize_prompt(prompt), max_tokens=2048)
    
    if raw_res:
        return {"explanation": raw_res.strip()}
    
    return {"explanation": "Synthesis currently unavailable. Review raw sources below."}