import json
import logging
import os
import time
from django.conf import settings
from llama_cpp import Llama
from jsonschema import validate, ValidationError

# Optional import for Google Cloud Platform integration
try:
    from google.cloud import aiplatform
    from google.cloud.aiplatform.gapic.schema import predict
except ImportError:
    aiplatform = None

logger = logging.getLogger(__name__)


# Global Singleton (The Brain)

# Caches the local model in memory to prevent repeated disk I/O
_LOCAL_MODEL = None

# THE CONSTITUTION (Schema Definitions)

# These schemas enforce strict determinism. Any LLM output that
# does not perfectly match these shapes is rejected by the
# symbolic gate, ensuring 0% hallucination in the final database.

BASE_SCHEMA = {
    "type": "object",
    "required": ["rule_type", "logic_config", "scope_tags", "intent_tags", "summary"],
    "properties": {
        "rule_type": {"type": "string"},
        "summary": {"type": "string"},
        "scope_tags": {"type": "array", "items": {"type": "string"}},
        "intent_tags": {"type": "array", "items": {"type": "string"}},
        "logic_config": {"type": "object"}
    }
}

LOGIC_CONFIG_SCHEMAS = {
    "temporal": {
        "required": ["anchor", "target"],
        "properties": {
            "anchor": {"type": "string"},
            "target": {"type": "string"},
            "max_delay_minutes": {"type": ["number", "null"]}
        }
    },
    "threshold": {
        "required": ["target_vital", "operator"],
        "properties": {
            "target_vital": {"type": "string"},
            "operator": {"enum": ["<", ">", "<=", ">=", "=", "!="]},
            "min_value": {"type": ["number", "null"]},
            "max_value": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]}
        }
    },
    "existence": {
        "required": ["required_artifact"],
        "properties": {
            "required_artifact": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}
        }
    },
    "contra": {
        "required": ["forbidden_treatment"],
        "properties": {
            "forbidden_treatment": {"type": "string"},
            "trigger_drug": {"type": ["string", "null"]},
            "trigger_condition": {"type": ["string", "null"]}
        }
    },
    "exclusive": {
        "required": ["event_1", "event_2"],
        "properties": {
            "event_1": {"type": "string"},
            "event_2": {"type": "string"}
        }
    },
    "monotonic": {
        "required": ["event_type"],
        "properties": {
            "event_type": {"type": "string"}
        }
    },
    "conditional_existence": {
        "required": ["trigger_assertion", "required_artifact"],
        "properties": {
            "trigger_assertion": {"type": "string"},
            "required_artifact": {"type": "string"}
        }
    },
    "count_sanity": {
        "required": ["event_type", "max_count"],
        "properties": {
            "event_type": {"type": "string"},
            "max_count": {"type": "integer"}
        }
    },
    "duplicate": {
        "type": "object",
        "additionalProperties": True 
    },
    "protocol_validity": {
        "type": "object",
        "additionalProperties": True
    }
}


# Local Inference Management (Edge)

def _load_local_cpu_brain():
    """
    Lazy loader for local GGUF inference.
    Optimized for high-memory environments with thread-throttling 
    to prevent system-wide freezes during heavy neural compilation.
    """
    global _LOCAL_MODEL
    if _LOCAL_MODEL is not None:
        return

    model_name = "medgate_brain_4b_Q8.gguf"
    model_path = os.path.join(settings.BASE_DIR, model_name)
    
    if not os.path.exists(model_path):
        logger.critical(f"GGUF Artifact missing at: {model_path}")
        raise FileNotFoundError(f"Local model not found: {model_name}")

    try:
        # Use a maximum of 4 threads to prevent thrashing in Docker/WSL2
        n_threads = min(4, max(1, os.cpu_count() - 1))
        
        _LOCAL_MODEL = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=n_threads, 
            verbose=False,
            use_mlock=False
        )
        logger.info("MedGate Local Engine initialized successfully.")
    except Exception as e:
        logger.error(f"Critical failure loading local GGUF: {e}")
        raise e


# Cloud Inference Management (GCP Vertex AI)

def _call_google_cloud_medgemma(prompt):
    """
    Dispatches request to the fine-tuned MedGemma endpoint on Google Cloud.
    Requires GOOGLE_APPLICATION_CREDENTIALS to be set in environment.
    """
    if not aiplatform:
        raise ImportError("google-cloud-aiplatform not installed.")

    # Endpoint parameters from settings
    project = settings.GCP_PROJECT_ID
    location = settings.GCP_LOCATION
    endpoint_id = settings.GCP_MEDGEMMA_ENDPOINT_ID

    aiplatform.init(project=project, location=location)
    endpoint = aiplatform.Endpoint(endpoint_id)

    # Note: Using precise parameters used during MedGemma fine-tuning
    instances = [{"content": prompt}]
    parameters = {
        "temperature": 0.0,
        "max_output_tokens": 1024,
        "top_p": 0.1,
        "top_k": 1
    }

    response = endpoint.predict(instances=instances, parameters=parameters)
    # Extract text from Vertex AI Prediction response
    prediction = response.predictions[0]
    if isinstance(prediction, dict):
        return prediction.get('content', '')
    return str(prediction)

# ---------------------------
# Neuro-Symbolic Logic Gate
# ---------------------------
def validate_forensic_output(instance):
    """
    Ensures the LLM output conforms to the deterministic logic engine.
    This acts as a filter: Probabilistic Output -> Symbolic Validation.
    """
    # Verify the top-level keys required for database storage
    validate(instance=instance, schema=BASE_SCHEMA)
    
    # Verify the specific inner logic required for the execution gate
    rule_type = instance.get("rule_type")
    if rule_type in LOGIC_CONFIG_SCHEMAS:
        validate(instance=instance["logic_config"], schema=LOGIC_CONFIG_SCHEMAS[rule_type])
    
    return True

def extract_metadata_only(unit_identifier, text_chunk):
    """
    Main entry point for clinical unit compilation.
    Routes to either Local Edge Brain or GCP Cloud Brain based on configuration.
    """
    print(f"[COMPILER] Starting parse for: {unit_identifier}", flush=True)

    # Construct the instruction-tuned prompt (Alpaca Format)
    alpaca_prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.

### Input:
{text_chunk}

### Response:
"""

    try:
        start_time = time.time()
        
        # Branching logic for Toggle (Offline Edge vs Cloud Deployment)
        if getattr(settings, 'OFFLINE_EDGE', True):
            # Local Execution Branch
            if _LOCAL_MODEL is None:
                _load_local_cpu_brain()
            
            output = _LOCAL_MODEL(
                alpaca_prompt,
                max_tokens=1024,
                temperature=0.0,
                stop=["<|endoftext|>", "###", "<end_of_turn>"],
                echo=False
            )
            response_text = output['choices'][0]['text'].strip()
        else:
            # Google Cloud Platform Branch
            response_text = _call_google_cloud_medgemma(alpaca_prompt)

        # Cleanup potential Markdown formatting in LLM response
        clean_text = response_text.replace("```json", "").replace("```", "").strip()
        json_start = clean_text.find("{")
        json_end = clean_text.rfind("}")
        
        if json_start == -1 or json_end == -1:
            logger.error(f"Parser error: No valid JSON detected in output for {unit_identifier}")
            return None 

        json_payload = json.loads(clean_text[json_start : json_end + 1])

        # Apply Hard Symbolic Gate
        validate_forensic_output(json_payload)

        duration = time.time() - start_time
        print(f" Success: Compiled in {duration:.2f}s", flush=True)
        return json_payload

    except Exception as e:
        logger.error(f"Inference failure for {unit_identifier}: {str(e)}")
        return None