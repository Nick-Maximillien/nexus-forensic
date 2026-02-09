import json
import logging
import os
import time
from django.conf import settings
from llama_cpp import Llama
from jsonschema import validate, ValidationError

logger = logging.getLogger(__name__)

# ----------------------------
#  Global Singleton (The Brain)
# ----------------------------
_MODEL = None

# ----------------------------
#  THE CONSTITUTION (Schema Definitions)
# ----------------------------
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

# Strict shapes for the 'logic_config' based on rule_type
# NOW UPDATED TO COVER ALL 10 RULE TYPES
LOGIC_CONFIG_SCHEMAS = {
    # 1. TEMPORAL (Cause < Effect)
    "temporal": {
        "required": ["anchor", "target"],
        "properties": {
            "anchor": {"type": "string"},
            "target": {"type": "string"},
            "max_delay_minutes": {"type": ["number", "null"]}
        }
    },
    # 2. THRESHOLD (Vital Limits)
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
    # 3. EXISTENCE (Must have X)
    "existence": {
        "required": ["required_artifact"],
        "properties": {
            "required_artifact": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}
        }
    },
    # 4. CONTRAINDICATION (No X if Y)
    "contra": {
        "required": ["forbidden_treatment"],
        "properties": {
            "forbidden_treatment": {"type": "string"},
            "trigger_drug": {"type": ["string", "null"]},
            "trigger_condition": {"type": ["string", "null"]}
        }
    },
    # 5. EXCLUSIVE (Cannot have X and Y)
    "exclusive": {
        "required": ["event_1", "event_2"],
        "properties": {
            "event_1": {"type": "string"},
            "event_2": {"type": "string"}
        }
    },
    # 6. MONOTONIC (Time must go forward for X)
    "monotonic": {
        "required": ["event_type"],
        "properties": {
            "event_type": {"type": "string"}
        }
    },
    # 7. CONDITIONAL EXISTENCE (If Assertion X -> Must have Proof Y)
    "conditional_existence": {
        "required": ["trigger_assertion", "required_artifact"],
        "properties": {
            "trigger_assertion": {"type": "string"},
            "required_artifact": {"type": "string"}
        }
    },
    # 8. COUNT SANITY (No more than N occurrences of X)
    "count_sanity": {
        "required": ["event_type", "max_count"],
        "properties": {
            "event_type": {"type": "string"},
            "max_count": {"type": "integer"}
        }
    },
    # 9. DUPLICATE (Data Integrity)
    # The python code executes this globally, so config is usually empty, 
    # but we allow an object to prevent crashes if the LLM adds commentary.
    "duplicate": {
        "type": "object",
        "additionalProperties": True 
    },
    # 10. PROTOCOL VALIDITY (Metadata Check)
    # Relies on protocol.valid_from/until, not JSON config.
    "protocol_validity": {
        "type": "object",
        "additionalProperties": True
    }
}

def _load_cpu_brain():
    """
    Lazy loader that mounts the 8-bit GGUF model into System RAM.
    """
    global _MODEL
    if _MODEL is not None:
        return

    model_name = "medgate_brain_4b_Q8.gguf"
    model_path = os.path.join(settings.BASE_DIR, model_name)
    
    if not os.path.exists(model_path):
        logger.critical(f" GGUF Artifact missing at: {model_path}")
        raise FileNotFoundError(f"MedGate Brain not found. Please place '{model_name}' in the project root.")

    logger.info(f" Mounting MedGate Edge Brain (Q8_0)... Path: {model_path}")
    print(f" [MEDGATE] Loading Local Inference Engine...", flush=True)
    
    try:
        # PERFORMANCE FIX: Hard Cap at 4 Threads
        # Using all cores (os.cpu_count) causes 'Thread Thrashing' on WSL2/Docker,
        # which looks like a system freeze. 4 threads is the optimal safe limit.
        n_threads = min(4, max(1, os.cpu_count() - 1))
        
        _MODEL = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=n_threads, 
            verbose=False,
            use_mlock=False
        )
        logger.info(" MedGate Neural Compiler is Online.")
        print(f" [MEDGATE] Brain Online. (Threads: {n_threads}, Locked: False)", flush=True)
    except Exception as e:
        logger.error(f"Failed to load GGUF model: {e}")
        raise e

def warmup_forensic_brain():
    """
    Triggers model load at startup.
    """
    if _MODEL is None:
        _load_cpu_brain()

def validate_forensic_output(instance):
    """
    The Hard Symbolic Gate.
    Returns True if valid, raises ValidationError if invalid.
    """
    # 1. Check Base Structure
    validate(instance=instance, schema=BASE_SCHEMA)
    
    # 2. Check Logic Specifics
    rule_type = instance.get("rule_type")
    
    # Now validates ALL 10 Types defined in LOGIC_CONFIG_SCHEMAS
    if rule_type in LOGIC_CONFIG_SCHEMAS:
        validate(instance=instance["logic_config"], schema=LOGIC_CONFIG_SCHEMAS[rule_type])
    
    return True

def extract_metadata_only(unit_identifier, text_chunk):
    """
    NEURO-SYMBOLIC COMPILER (EDGE VERSION)
    Text -> LLM -> JSON -> Schema Gate -> Database
    """
    global _MODEL
    
    if _MODEL is None:
        _load_cpu_brain()

    print(f" [COMPILER] Processing: {unit_identifier}...", flush=True)

    # Note: We keep the Alpaca prompt because your adapter was trained on it.
    alpaca_prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.

### Input:
{text_chunk}

### Response:
"""

    try:
        start_time = time.time()
        
        # 1. PROBABILISTIC GENERATION
        output = _MODEL(
            alpaca_prompt,
            max_tokens=512,
            temperature=0.0, # Deterministic
            # SURGICAL FIX: Added <end_of_turn> as MedGemma sometimes emits this instead of ###
            stop=["<|endoftext|>", "###", "<end_of_turn>"],
            echo=False
        )
        
        duration = time.time() - start_time
        response_text = output['choices'][0]['text'].strip()
        
        # 2. SYMBOLIC EXTRACTION
        clean_text = response_text.replace("```json", "").replace("```", "").strip()
        json_start = clean_text.find("{")
        json_end = clean_text.rfind("}")
        
        if json_start == -1 or json_end == -1:
            logger.warning(f"Compiler Error: No JSON found for {unit_identifier}")
            # PERFORMANCE FIX: Return None to skip, don't fallback
            return None 

        json_payload = json.loads(clean_text[json_start : json_end + 1])

        # 3. THE HARD GATE
        validate_forensic_output(json_payload)

        print(f"   ✅ Parsed in {duration:.2f}s", flush=True)
        return json_payload

    except ValidationError as e:
        logger.error(f" Schema Violation for {unit_identifier}: {e.message}")
        print(f"   -> REJECTED by Gate: {e.message}", flush=True)
        # PERFORMANCE FIX: Return None to skip
        return None

    except json.JSONDecodeError as e:
        logger.error(f" Syntax Error for {unit_identifier}: {e}")
        # PERFORMANCE FIX: Return None to skip
        return None
        
    except Exception as e:
        logger.error(f" System Fault: {e}")
        # PERFORMANCE FIX: Return None to skip
        return None

def _get_fallback_schema(summary_text="", reason="Unknown"):
    return {
        "rule_type": "existence",
        "logic_config": {"required_artifact": "MANUAL_REVIEW_REQUIRED"},
        "scope_tags": ["clinical"],
        "intent_tags": ["quality"],
        "summary": f"[COMPILER FAIL] {reason}. Input: {summary_text[:30]}..."
    }