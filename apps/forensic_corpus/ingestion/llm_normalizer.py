import json
import os
import logging
import time
import random
from pathlib import Path
from vertexai import init as vertex_init
from vertexai.generative_models import GenerativeModel, GenerationConfig, HarmCategory, HarmBlockThreshold
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

logger = logging.getLogger(__name__)

# ----------------------------
#  Setup GCP Credentials (Render-friendly)
# ----------------------------

if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].replace("\\", "/")

# ----------------------------
#  Vertex AI Initialization
# ----------------------------
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = "us-central1"

try:
    vertex_init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
except Exception as e:
    logger.error(f"Vertex AI init failed: {e}")

# ----------------------------
#  Model & Config
# ----------------------------
# Using 2.5 Flash for fast, cheap logic extraction
model = GenerativeModel("gemini-2.5-flash") 

safety_settings = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

def sanitize_prompt(prompt: str) -> str:
    """Sanitize long prompts to reduce model blocking and improve JSON parsing."""
    if len(prompt) > 7000:
        prompt = prompt[:7000] + "\n\n[...truncated large data...]"
    return prompt

def extract_metadata_only(unit_identifier, text_chunk):
    """
    Uses LLM to extract Forensic Logic (Rule Type + Config) AND Context (Scope + Intent).
    Updated for the Kenyan Pivot: Includes KEPH Facility Level Tagging.
    Returns:
        dict: {
            "rule_type": str,       # 'temporal', 'threshold', 'monotonic', etc.
            "logic_config": dict,   # Structured params for the Django Gate
            "scope_tags": list,     # ['clinical', 'facility', 'billing']
            "intent_tags": list,    # ['safety', 'quality', 'compliance']
            "applicable_facility_levels": list, # ['level_1', ..., 'level_6']
            "summary": str          # Short human-readable summary
        }
    """
    
    # [VISIBILITY] Force print to console so the user knows it's working
    print(f" [LLM] Extracting Kenyan logic for: {unit_identifier}", flush=True)

    # ---------------------------------------------------------
    #  THE CLINICAL LOGIC PROMPT (KENYAN PIVOT MERGED)
    # ---------------------------------------------------------
    raw_prompt = f"""
    You are a Clinical Logic Parser specializing in the Kenyan Essential Package for Health (KEPH).
    Analyze the medical protocol text identified as "{unit_identifier}" within the context of MoH guidelines.

    ---------------------------------------------------------
    TASK 1: FORENSIC LOGIC EXTRACTION (The Precision Gate)
    ---------------------------------------------------------
    Convert the natural language rule into a STRUCTURED JSON configuration that code can execute.
    Recognize Kenyan specifics like MCH Handbook constraints (e.g. 8 ANC visits) and KEML drug administration.
    You MUST classify the rule into one of these 10 Types:

    1. TEMPORAL (Time sequence rules)
       Example: "ECG must be performed within 10 minutes of arrival."
       JSON: {{ "rule_type": "temporal", "logic_config": {{ "anchor": "arrival", "target": "ECG", "max_delay_minutes": 10 }} }}

    2. THRESHOLD (Vital sign or Lab limits)
       Example: "Administer Oxygen if Saturation is below 90%."
       JSON: {{ "rule_type": "threshold", "logic_config": {{ "target_vital": "Oxygen Saturation", "min_value": 90, "operator": "<" }} }}

    3. EXISTENCE (Required evidence/action)
       Example: "A neurological assessment is required."
       JSON: {{ "rule_type": "existence", "logic_config": {{ "required_artifact": "neurological assessment" }} }}

    4. CONTRA (Contraindications)
       Example: "Do not administer Nitrates if patient took Sildenafil."
       JSON: {{ "rule_type": "contra", "logic_config": {{ "forbidden_treatment": "Nitrates", "trigger_drug": "Sildenafil" }} }}

    5. EXCLUSIVE (Mutually Exclusive Events)
       Example: "Conscious sedation and General Anesthesia cannot be billed same day."
       JSON: {{ "rule_type": "exclusive", "logic_config": {{ "event_1": "Conscious sedation", "event_2": "General Anesthesia" }} }}
    
    6. DUPLICATE (Data Integrity)
       Example: "Verify no duplicate billing codes."
       JSON: {{ "rule_type": "duplicate", "logic_config": {{}} }}

    7. CONDITIONAL EXISTENCE (Assertion -> Proof)
       Example: "If chest pain is reported, an ECG strip must exist."
       JSON: {{ "rule_type": "conditional_existence", "logic_config": {{ "trigger_assertion": "chest pain", "required_artifact": "ECG strip" }} }}
       
    8. PROTOCOL VALIDITY (Metadata)
       Example: "This standard is valid for events in 2024 only."
       JSON: {{ "rule_type": "protocol_validity", "logic_config": {{}} }}
       
    9. COUNT SANITY (Outlier Detection)
       Example: "Minimum 8 ANC visits required during pregnancy."
       JSON: {{ "rule_type": "count_sanity", "logic_config": {{ "event_type": "ANC Visit", "min_count": 8 }} }}

    10. MONOTONIC (Timeline Stability)
       Example: "Vital signs must be recorded in chronological order."
       JSON: {{ "rule_type": "monotonic", "logic_config": {{ "event_type": "vitals" }} }}

    ---------------------------------------------------------
    TASK 2: FACILITY LEVEL TAGGING (Kenyan Context)
    ---------------------------------------------------------
    Identify the applicable facility level(s) based on the Kenyan MoH hierarchy:
    - "level_1": Community (CHVs)
    - "level_2": Dispensaries
    - "level_3": Health Centres
    - "level_4": Sub-County Hospitals
    - "level_5": County Referral Hospitals
    - "level_6": National Referral (KNH/MTRH)

    ---------------------------------------------------------
    TASK 3: SCOPE CLASSIFICATION (Context)
    ---------------------------------------------------------
    Determine WHERE this rule applies (Select all that apply):
    - "clinical": Direct patient care (meds, diagnosis, procedures, vitals).
    - "facility": Operations, equipment maintenance, staffing licensure, building safety, policies.
    - "billing": Coding or billing specific.
    - "legal": Regulatory/Court order requirements.

    ---------------------------------------------------------
    TASK 4: INTENT CLASSIFICATION (Purpose)
    ---------------------------------------------------------
    Determine WHY this rule exists (Select all that apply):
    - "safety": Patient safety (e.g., prevent harm).
    - "quality": Standard of care / Outcomes.
    - "compliance": Regulatory paperwork (e.g., logs, signatures).
    - "integrity": Data accuracy or fraud prevention.

    ---------------------------------------------------------
    INPUT TEXT:
    {text_chunk[:2000]}

    OUTPUT FORMAT (Strict JSON):
    {{
        "rule_type": "...",
        "logic_config": {{...}},
        "scope_tags": ["clinical"], 
        "intent_tags": ["safety"],
        "applicable_facility_levels": ["level_2", "level_3"],
        "summary": "Short 1-sentence summary"
    }}
    """
    
    final_prompt = sanitize_prompt(raw_prompt)

    generation_config = GenerationConfig(
        response_mime_type="application/json",
        temperature=0.0 # Strict Determinism required for Logic
    )

    # --- RETRY LOGIC FOR RATE LIMITING ---
    max_retries = 6
    base_delay = 2 

    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                final_prompt, 
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # SURGICAL FIX: Strip markdown before parsing to prevent crash
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            # -------------------------------------------------------------
            #  FIX APPLIED: Handle List vs Object responses
            # -------------------------------------------------------------
            parsed_json = json.loads(raw_text)
            
            # If AI returns a list [ {} ], extract the first item
            if isinstance(parsed_json, list):
                if len(parsed_json) > 0:
                    parsed_json = parsed_json[0]
                else:
                    raise ValueError("Empty List returned")
            
            # Ensure the facility levels key exists for the Kenyan Pivot
            if "applicable_facility_levels" not in parsed_json:
                parsed_json["applicable_facility_levels"] = ["level_2"]

            return parsed_json

        except (ResourceExhausted, ServiceUnavailable) as e:
            wait_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
            # [VISIBILITY] Force print so user sees the rate limit happening
            print(f" [LLM] ⚠️ Rate Limit hit for {unit_identifier}. Retrying in {wait_time:.2f}s...", flush=True)
            logger.warning(f"Rate limit hit for {unit_identifier}. Retrying in {wait_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)

        except Exception as e:
            # [VISIBILITY] Force print so user sees the error
            print(f" [LLM] ❌ Logic extraction failed: {e}", flush=True)
            logger.error(f"Logic extraction failed (Non-Retryable): {e}")
            break 
    
    # Fallback default if AI fails (Safe Default: Just check existence)
    return {
        "rule_type": "existence",
        "logic_config": {"required_artifact": "unknown_requirement"},
        "scope_tags": ["clinical"],
        "intent_tags": ["quality"],
        "applicable_facility_levels": ["level_2"],
        "summary": "Auto-extraction failed"
    }