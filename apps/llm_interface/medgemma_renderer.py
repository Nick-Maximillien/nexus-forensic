import os
import logging
import json
import time
import random
from pathlib import Path

# NOTE: We do NOT import vertexai or aiplatform here.
# We import them lazily inside the functions to prevent Server Boot Timeouts
# and Gunicorn Worker Deadlocks (gRPC fork safety).
from apps.forensic_domain.contract import ForensicVerdict

logger = logging.getLogger(__name__)

# ----------------------------
#  Setup GCP Credentials
# ----------------------------
if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].replace("\\", "/")

# ----------------------------
#  Lazy Initialization Singleton
# ----------------------------
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = "us-central1"
MEDGEMMA_ENDPOINT_ID = os.getenv("MEDGEMMA_ENDPOINT_ID", "") 

_VERTEX_INITIALIZED = False
_MEDGEMMA_ENDPOINT = None

def _ensure_vertex_init():
    """
    Lazy loader for Vertex AI connections.
    Matches the robust 'utils.py' pattern.
    """
    global _VERTEX_INITIALIZED
    
    # 1. If already initialized, return True immediately to prevent re-init hangs
    if _VERTEX_INITIALIZED:
        return True
    
    # 2. Otherwise, attempt initialization
    try:
        logger.info(f"🔌 Connecting to Vertex AI (Project: {GCP_PROJECT_ID})...")
        
        # Heavy Imports moved INSIDE (Lazy) to prevent Gunicorn Import Deadlocks
        from google.cloud import aiplatform
        from vertexai import init as vertex_init
        
        # Initialize both SDKs
        aiplatform.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
        vertex_init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
        
        _VERTEX_INITIALIZED = True
        logger.info("✅ Vertex AI Renderer Online.")
        return True
    except Exception as e:
        logger.error(f"Vertex AI Lazy Init failed: {e}")
        return False

def _get_medgemma_endpoint():
    """Lazy loader for the specific Endpoint object."""
    global _MEDGEMMA_ENDPOINT
    
    if not MEDGEMMA_ENDPOINT_ID:
        return None

    if _MEDGEMMA_ENDPOINT is None:
        if _ensure_vertex_init():
            try:
                from google.cloud import aiplatform
                _MEDGEMMA_ENDPOINT = aiplatform.Endpoint(endpoint_name=MEDGEMMA_ENDPOINT_ID)
            except Exception as e:
                logger.warning(f"MedGemma Endpoint unreachable: {e}")
                return None
    
    return _MEDGEMMA_ENDPOINT

def sanitize_prompt(prompt: str) -> str:
    """Sanitize prompts to ensure they pass filters."""
    if len(prompt) > 20000: 
        prompt = prompt[:20000] + "\n\n[...truncated large context...]"
    return prompt

def _clean_json_response(raw_text: str) -> dict:
    """
    Surgical JSON cleaner matching user's robust pattern.
    Strips markdown fences and handles list vs dict.
    """
    try:
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            # Remove first line if it starts with ``` (e.g. ```json)
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line if it starts with ```
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_text = "\n".join(lines).strip()

        parsed_json = json.loads(raw_text)
        
        # If AI returns a list [ {} ], extract the first item
        if isinstance(parsed_json, list):
            if len(parsed_json) > 0:
                return parsed_json[0]
            else:
                return {}
        
        return parsed_json
    except json.JSONDecodeError:
        logger.error(f"JSON Parsing failed for text: {raw_text[:100]}...")
        raise

def generate_forensic_report(claim_data: dict, verdict: ForensicVerdict) -> dict:
    """
    Renders the 'Certified Audit Report' OR 'Non-Compliance Explanation'.
    Uses Robust Retry Pattern for 429/503 errors.
    """
    
    # 1. Construct Data Blocks
    events_block = "\n".join([
        f"- {e.get('timestamp', 'N/A')} {e.get('name', 'Unknown Event')}" 
        for e in claim_data.get('events', [])
    ])
    
    passed_block = "\n".join([
        f"- [PASS] {r.rule_code}: {r.rule_type}" 
        for r in verdict.passed_rules
    ])

    violations_block = "NO VIOLATIONS DETECTED."
    if not verdict.is_valid:
        # [UPGRADE] Inject Scope and Intent tags into the prompt context for the LLM
        violations_block = "\n".join([
            f"- [VIOLATION] [Intent: {', '.join(v.get('rule', {}).get('intent', ['unknown']))}] {v['rule']['code']} ({v['protocol']['title']}): {v['validation_trace']}" 
            for v in verdict.violations
        ])

    # 2. Define Context-Aware System Directive
    audit_outcome = "CLEARED / VALID" if verdict.is_valid else "HALTED / INVALID"
    
    system_directive = f"""
    You are MedGemma, a Forensic Clinical Auditor.
    CURRENT AUDIT STATUS: {audit_outcome}

    INSTRUCTIONS:
    1. Analyze the 'PASSED RULES' and 'VIOLATIONS' against the 'CLINICAL EVENTS'.
    
    2. If STATUS is CLEARED: Generate a certification statement confirming protocol adherence.
    
    3. If STATUS is HALTED: Generate a professional "Non-Compliance Summary" explaining WHY it failed.
       - PRIORITY: Categorize failures by INTENT (e.g., SAFETY vs COMPLIANCE).
       - Focus first on 'safety' or 'quality' violations as they are critical.
       - 'Compliance' or 'Documentation' errors should be noted as administrative.
       - Cite the specific missing artifacts or timeline errors.
       - Do not be vague.
       - Use the exact text from the VIOLATIONS block.
       - Tone: Objective, Legal, Explanatory.
       
    4. OUTPUT FORMAT (Strict JSON):
    {{
        "certification_statement": "A clear 2-3 sentence summary of the audit outcome.",
        "compliance_matrix": [
            {{ "rule_code": "Rule X", "status": "PASS" }},
            {{ "rule_code": "Rule Y", "status": "FAIL" }}
        ],
        "evidence_traces": [
            {{ "event": "Event Name", "timestamp": "ISO Time" }}
        ]
    }}
    """

    full_prompt_text = f"""
    {system_directive}

    --- CLINICAL EVENTS ---
    {events_block}

    --- PASSED PROTOCOLS ---
    {passed_block}

    --- DETECTED VIOLATIONS ---
    {violations_block}
    """

    # --- ATTEMPT 1: MEDGEMMA (Specialized Endpoint) ---
    try:
        endpoint = _get_medgemma_endpoint()
        
        if not endpoint:
            # Not an error if just not configured, just skip to fallback
            raise ValueError("MedGemma ID not configured.")

        gemma_prompt = f"""<start_of_turn>user
        {full_prompt_text}

        Generate the JSON Report.<end_of_turn>
        <start_of_turn>model
        """
        
        logger.info("🔮 Invoking MedGemma Endpoint...")
        response = endpoint.predict(instances=[{
            "inputs": sanitize_prompt(gemma_prompt),
            "parameters": {"temperature": 0.1, "max_output_tokens": 1024, "top_p": 0.95}
        }])
        
        raw_output = response.predictions[0]
        return _clean_json_response(raw_output)

    except Exception as e:
        logger.warning(f"⚠️ MedGemma skipped/failed ({e}). Switching to Gemini 2.5 Flash Fallback.")

        # --- ATTEMPT 2: GEMINI 2.5 FLASH (Serverless Fallback with Retries) ---
        try:
            if _ensure_vertex_init():
                from vertexai.generative_models import GenerativeModel, GenerationConfig, HarmCategory, HarmBlockThreshold
                from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
                
                model = GenerativeModel("gemini-2.5-flash")
                
                config = GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.0 # Deterministic
                )

                safety_settings = {
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
                
                sanitized_prompt = sanitize_prompt(full_prompt_text)
                
                # --- RETRY LOGIC FOR RATE LIMITING ---
                max_retries = 6
                base_delay = 2 

                for attempt in range(max_retries):
                    try:
                        logger.info(f"⚡ Invoking Gemini 2.5 Flash (Attempt {attempt+1})...")
                        response = model.generate_content(
                            sanitized_prompt,
                            generation_config=config,
                            safety_settings=safety_settings
                        )
                        
                        return _clean_json_response(response.text)

                    except (ResourceExhausted, ServiceUnavailable) as api_err:
                        wait_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
                        logger.warning(f"Rate limit hit. Retrying in {wait_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    
                    except Exception as loop_err:
                        logger.error(f"Gemini Attempt {attempt+1} failed: {loop_err}")
                        if attempt == max_retries - 1:
                            raise loop_err # Re-raise if all retries fail

            else:
                raise ValueError("Vertex AI Init returned False.")

        except Exception as final_error:
            logger.error(f" All AI Rendering failed: {final_error}")
            
            # --- ATTEMPT 3: SAFETY NET ---
            return {
                "certification_statement": "Audit Complete. (AI Explanation Unavailable). See violations below.",
                "compliance_matrix": [{"rule_code": r.rule_code, "status": "PASS"} for r in verdict.passed_rules],
                "evidence_traces": [{"event": e.get("name"), "timestamp": e.get("timestamp")} for e in claim_data.get('events', [])],
                "system_note": f"Report generated via hard fallback. Violations found: {len(verdict.violations)}"
            }

def generate_research_summary(query: str, rules: list) -> dict:
    """
    Research Mode: Explains the query strictly using the retrieved rules.
    Returns: { "explanation": "string..." }
    """
    
    # 1. Format the "Truths" for the LLM
    knowledge_base = "\n".join([
        f"SOURCE [{r.rule_code}] ({r.protocol.title}): {r.text_description}" 
        for r in rules
    ])

    system_directive = f"""
    You are MedGemma, a Clinical Research Assistant.
    
    USER QUERY: "{query}"

    MANDATE:
    1. Answer the query using ONLY the provided SOURCES below.
    2. Do NOT use outside medical knowledge. If the answer is not in the sources, say "The provided protocols do not cover this specific query."
    3. CITE your sources. When you state a fact, append the Source ID (e.g., [Tag A-0045]).
    4. Be concise and professional.

    --- APPROVED SOURCES ---
    {knowledge_base}
    """
    
    # Using the same robust retry pattern as Audit, but requesting text output (not JSON)
    try:
        if _ensure_vertex_init():
            from vertexai.generative_models import GenerativeModel, GenerationConfig, HarmCategory, HarmBlockThreshold
            from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
            
            # Use Flash for fast, grounded explanation
            model = GenerativeModel("gemini-2.5-flash")
            
            # Text generation config (Non-JSON)
            config = GenerationConfig(
                temperature=0.1, 
                max_output_tokens=1024
            )

            safety_settings = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            }
            
            sanitized_prompt = sanitize_prompt(system_directive)
            
            max_retries = 4
            base_delay = 2 

            for attempt in range(max_retries):
                try:
                    logger.info(f"⚡ Invoking Research Agent (Attempt {attempt+1})...")
                    response = model.generate_content(
                        sanitized_prompt,
                        generation_config=config,
                        safety_settings=safety_settings
                    )
                    return {"explanation": response.text.strip()}

                except (ResourceExhausted, ServiceUnavailable) as api_err:
                    wait_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
                    time.sleep(wait_time)
                
                except Exception as loop_err:
                    logger.error(f"Research Agent failed: {loop_err}")
                    if attempt == max_retries - 1:
                        raise loop_err
        else:
             logger.warning("Vertex Init returned False in Research Summary.")

    except Exception as e:
        logger.error(f"Research synthesis failed: {e}")
    
    # FALLBACK RETURN - Ensures we never return None
    # This catches failures in Vertex Init or global exceptions
    return {"explanation": "Research synthesis unavailable. Please refer to the raw retrieved facts below."}