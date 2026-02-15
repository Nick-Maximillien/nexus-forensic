import json
import logging
import os
import time
from django.conf import settings
from llama_cpp import Llama
from jsonschema import validate, ValidationError
from apps.forensic_corpus.ingestion.parser import BaseParser 

# Lazy load Google Cloud AI Platform to prevent Gunicorn worker blocks
try:
    from google.cloud import aiplatform
except ImportError:
    aiplatform = None

logger = logging.getLogger(__name__)

# ----------------------------------------------
# Global Singleton (The Neural Extraction Brain)
# ----------------------------------------------
_LOCAL_MODEL = None

# -----------------------------------
# THE CONSTITUTION: Extraction Schema
# -----------------------------------
# Enforces strict determinism for the clinical timeline.
# MedGemma must output this exact shape or it is rejected by the gate.
EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "timestamp", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "value": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "type": {"type": "string"},
                    "source": {"type": "string"}
                }
            }
        }
    }
}

# ---------------------------------
# Local Inference Management (Edge)
# ---------------------------------
def _load_local_cpu_brain():
    """
    Lazy loader for local GGUF inference.
    Optimized for high-memory environments with thread-throttling 
    to prevent system-wide freezes during PDF processing.
    """
    global _LOCAL_MODEL
    if _LOCAL_MODEL is not None:
        return

    model_name = "medgate_brain_4b_Q8.gguf"
    model_path = os.path.join(settings.BASE_DIR, model_name)
    
    if not os.path.exists(model_path):
        logger.critical(f"GGUF Artifact missing for extraction: {model_path}")
        raise FileNotFoundError(f"Local model not found: {model_name}")

    try:
        # Performance lock: 4 threads is the stability sweet spot for WSL2/Docker
        n_threads = min(4, max(1, os.cpu_count() - 1))
        
        _LOCAL_MODEL = Llama(
            model_path=model_path,
            n_ctx=4096, # Increased context for larger document chunks
            n_threads=n_threads, 
            verbose=False,
            use_mlock=False
        )
        logger.info("MedGate Local Extraction Engine initialized.")
    except Exception as e:
        logger.error(f"Critical failure loading local extractor GGUF: {e}")
        raise e

# -------------------------------------------
# Cloud Inference Management (GCP Vertex AI)
# -------------------------------------------
def _call_google_cloud_medgemma(prompt):
    """
    Dispatches extraction request to the fine-tuned MedGemma endpoint on GCP.
    Leverages Google's infrastructure for high-throughput document processing.
    """
    if not aiplatform:
        raise ImportError("google-cloud-aiplatform not installed.")

    aiplatform.init(
        project=settings.GCP_PROJECT_ID, 
        location=settings.GCP_LOCATION
    )
    endpoint = aiplatform.Endpoint(settings.GCP_MEDGEMMA_ENDPOINT_ID)

    instances = [{"content": prompt}]
    parameters = {
        "temperature": 0.0,
        "max_output_tokens": 2048,
        "top_p": 0.1,
        "top_k": 1
    }

    response = endpoint.predict(instances=instances, parameters=parameters)
    prediction = response.predictions[0]
    if isinstance(prediction, dict):
        return prediction.get('content', '')
    return str(prediction)

# ------------------------
# Clinical Extractor Layer
# ------------------------
class ClinicalExtractor:
    """
    The Extraction Bridge: Converts Unstructured PDF -> Structured Forensic JSON.
    Uses a dual-inference strategy (Edge vs Cloud) governed by settings.OFFLINE_EDGE.
    """
    
    @staticmethod
    def pdf_to_json(file_path: str) -> dict:
        """
        Main execution pipeline for document forensic extraction.
        """
        # 1. High-Fidelity Layout Analysis (Docling)
        try:
            parser = BaseParser() 
            markdown_text = parser.extract_markdown(file_path)
            
            logger.info(f"Document Analysis Start: {file_path}")
            logger.info(f"Layout Snapshot: {markdown_text[:500]}...") 
            
        except Exception as e:
            logger.error(f"Layout Analysis Failed: {e}")
            return {"events": []}

        # 2. Instruction-Tuned Prompt (Alpaca Format)
        # We use the exact training format of the fine-tuned MedGemma model.
        alpaca_prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Clinical Data Normalizer. Extract every clinical event and administrative artifact from the input text and convert it into a structured JSON timeline.
RULES:
1. Use strict ISO 8601 timestamps (YYYY-MM-DDTHH:MM:SSZ).
2. Extract medications, procedures, vitals, and facility licenses.
3. Use the exact text from the document for the "source" field.

### Input:
{markdown_text[:15000]}

### Response:
"""

        # 3. Neural Inference (Edge vs Cloud Toggle)
        try:
            start_time = time.time()
            
            if getattr(settings, 'OFFLINE_EDGE', True):
                # Local GGUF Path
                if _LOCAL_MODEL is None:
                    _load_local_cpu_brain()
                
                output = _LOCAL_MODEL(
                    alpaca_prompt,
                    max_tokens=2048,
                    temperature=0.0,
                    stop=["<|endoftext|>", "###", "<end_of_turn>"],
                    echo=False
                )
                response_text = output['choices'][0]['text'].strip()
            else:
                # GCP Cloud Path
                response_text = _call_google_cloud_medgemma(alpaca_prompt)

            # 4. Symbolic Cleanup & Parsing
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            json_start = clean_text.find("{")
            json_end = clean_text.rfind("}")
            
            if json_start == -1 or json_end == -1:
                logger.error("Neural Parser Error: No JSON boundaries detected in response.")
                return {"events": []}

            json_payload = json.loads(clean_text[json_start : json_end + 1])

            # 5. The Hard Gate (Validation)
            # Ensures extracted data is safe for the Forensic Adjudication Layer.
            validate(instance=json_payload, schema=EXTRACTION_SCHEMA)

            duration = time.time() - start_time
            logger.info(f"Extraction Successful: {len(json_payload.get('events', []))} events in {duration:.2f}s")
            
            return json_payload
            
        except Exception as e:
            logger.error(f"Neural Extraction Pipeline Failed: {str(e)}")
            return {"events": []}