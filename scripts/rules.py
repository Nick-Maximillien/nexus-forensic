# =========================================================
# MEDGATE FACTORY: THE GPU KNOWLEDGE COMPILER (v2.5)
# =========================================================
# MISSION: 
# 1. Parse clinical/forensic guidelines (PDF) into structured blocks.
# 2. Compile blocks into logic-gate JSON using MedGemma-4B + Adapter.
# 3. Enforce the Constitution (10-Type Logic Schema).
# 4. Export the validated Knowledge Graph.
# =========================================================

import os
import sys
import json
import re
import logging
import time
import hashlib
import torch
import subprocess
from io import BytesIO

# --- VISIBILITY LOGGING SETUP ---
logging.basicConfig(
    level=logging.DEBUG,  # increased to debug for full trace
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MedGateCompiler")

# --- 1. INSTALLATIONS ---
logger.info("SYSTEM: STARTING DEPENDENCY INSTALLATION...")
os.system("apt-get update && apt-get install -y libgl1-mesa-glx > /dev/null")
os.system("pip install -q --no-cache-dir docling docling-core transformers peft bitsandbytes accelerate jsonschema pypdfium2")

import jsonschema
from jsonschema import validate, ValidationError
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# Docling Imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# --- 2. CONFIGURATION & AUTH ---
PDF_INPUT_DIR = "/kaggle/input/medgate-compiler-pdf/"
PDF_PATH = os.path.join(PDF_INPUT_DIR, "doc.pdf")

ADAPTER_PATH = "/kaggle/input/medgate-forensic-adapter-v2/medgate_forensic_adapter_v2"
BASE_MODEL = "google/medgemma-1.5-4b-it"

from kaggle_secrets import UserSecretsClient
from huggingface_hub import login

logger.info("AUTH: AUTHENTICATING WITH HUGGING FACE...")
try:
    user_secrets = UserSecretsClient()
    hf_token = user_secrets.get_secret("HF_TOKEN")
    login(token=hf_token)
    logger.info("AUTH: AUTHENTICATION SUCCESSFUL.")
except Exception as e:
    logger.warning(f"AUTH: HF_TOKEN NOT FOUND. ERROR: {e}")

# --- 3. THE CONSTITUTION (SCHEMA DEFINITIONS) ---
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
            "required_artifact": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ]
            }
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
        "properties": {"event_type": {"type": "string"}}
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
    "duplicate": {"type": "object", "additionalProperties": True},
    "protocol_validity": {"type": "object", "additionalProperties": True}
}

def validate_forensic_output(instance):
    validate(instance=instance, schema=BASE_SCHEMA)
    rule_type = instance.get("rule_type")
    if rule_type in LOGIC_CONFIG_SCHEMAS:
        validate(instance=instance["logic_config"], schema=LOGIC_CONFIG_SCHEMAS[rule_type])
    return True

# --- 4. MOCK DATA MODEL ---
class ForensicRule:
    def __init__(self, rule_code, rule_type, text_description, logic_config, scope_tags, intent_tags):
        self.rule_code = rule_code
        self.rule_type = rule_type
        self.text_description = text_description
        self.logic_config = logic_config
        self.scope_tags = scope_tags
        self.intent_tags = intent_tags

    def to_dict(self):
        return {
            "rule_code": self.rule_code,
            "rule_type": self.rule_type,
            "text": self.text_description,
            "logic_config": self.logic_config,
            "scope": self.scope_tags,
            "intent": self.intent_tags
        }

# --- 5. THE PARSER CLASSES ---
class BaseParser:
    def __init__(self):
        logger.info("PARSER: INITIALIZING DOCLING ENGINE...")
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=PyPdfiumDocumentBackend
                )
            }
        )
        logger.info("PARSER: ENGINE READY.")

    def extract_markdown(self, file_path):
        logger.info(f"DOCLING: ANALYZING LAYOUT FOR {file_path}...")
        result = self.converter.convert(file_path)
        md_output = result.document.export_to_markdown()
        logger.info(f"DOCLING: CONVERSION COMPLETE ({len(md_output)} CHARS).")
        return md_output

class ClinicalProtocolParser(BaseParser):
    def process_file(self, file_path):
        md_text = self.extract_markdown(file_path)
        split_pattern = r"(?m)^#+\s+(?:Section\s+|Tag\s+)?(?:(A-\d{4})|(\d+(?:\.\d+)*))\.?\s+"
        tokens = re.split(split_pattern, md_text)

        chunks = []
        clean_tokens = [t for t in tokens if t is not None]
        logger.info(f"PARSER: SCANNING {len(clean_tokens)} TOKENS...")

        for i in range(1, len(clean_tokens), 2):
            if i + 1 >= len(clean_tokens):
                break
            identifier = clean_tokens[i]
            content = clean_tokens[i + 1]
            if len(content.strip()) < 20:
                continue

            rule_code = f"Tag {identifier}" if identifier.startswith("A-") else f"Rule {identifier}"
            chunks.append({"code": rule_code, "text": content.strip()})

        return chunks

# --- 6. THE BRAIN (LOAD MODEL) ---
logger.info(f"MODEL: LOADING MEDGEMMA-4B ({BASE_MODEL})...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

# DIAGNOSTIC: Check tokenizer config
logger.info(f"TOKENIZER CONFIG:")
logger.info(f"  - EOS token: {tokenizer.eos_token} (ID: {tokenizer.eos_token_id})")
logger.info(f"  - PAD token: {tokenizer.pad_token} (ID: {tokenizer.pad_token_id})")
logger.info(f"  - BOS token: {tokenizer.bos_token} (ID: {tokenizer.bos_token_id if hasattr(tokenizer, 'bos_token_id') else 'N/A'})")

base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True
)

logger.info(f"MODEL: ATTACHING ADAPTER FROM {ADAPTER_PATH}")
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

# CRITICAL: Enable cache for generation
model.config.use_cache = True

logger.info("MODEL: COMPILER READY ON GPU.")

# --- 7. NORMALIZATION HELPER ---
def normalize_chunk(text):
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[•\-–—]", "-", text)
    text = text.strip()
    return text[:1200]  # hard cap to 1200 chars

# --- 8. THE COMPILER LOOP (FIXED WITH FORCED GENERATION) ---
def compile_block(unit_identifier, text_chunk):
    text_chunk = normalize_chunk(text_chunk)
    
    # Use EXACT training prompt format
    alpaca_prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.

### Input:
{text_chunk}

### Response:
"""

    inputs = tokenizer(alpaca_prompt, return_tensors="pt").to("cuda")
    input_length = inputs.input_ids.shape[1]
    
    logger.debug(f"[{unit_identifier}] Input length: {input_length} tokens")

    try:
        with torch.no_grad():
            # CRITICAL FIX: Force generation with explicit stopping criteria
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                min_new_tokens=10,  # Force at least 10 tokens
                do_sample=False,
                temperature=None,
                top_p=None,
                num_beams=1,
                # CRITICAL: Use a stop strings approach instead of EOS
                eos_token_id=None,  # Disable EOS temporarily
                pad_token_id=tokenizer.pad_token_id,
            )

        # Extract ONLY the generated response tokens
        total_length = outputs.shape[1]
        generated_tokens = outputs[0][input_length:]
        
        logger.info(f"[{unit_identifier}] Generated {len(generated_tokens)} tokens (input was {input_length})")
        
        # Decode with full visibility
        decoded_full = tokenizer.decode(outputs[0], skip_special_tokens=True)
        decoded = tokenizer.decode(generated_tokens, skip_special_tokens=True)
        
        # Show what we got
        logger.debug(f"[{unit_identifier}] FULL OUTPUT (first 200 chars):\n{decoded_full[:200]}")
        logger.debug(f"[{unit_identifier}] RESPONSE ONLY (first 300 chars):\n{decoded[:300]}")

        if len(decoded.strip()) == 0:
            logger.error(f"[{unit_identifier}] CRITICAL: Model generated empty response!")
            logger.error(f"[{unit_identifier}] Full token output: {outputs[0].tolist()[:50]}")
            raise ValueError("MODEL GENERATED EMPTY OUTPUT")

        # Clean markdown artifacts
        clean = decoded.strip()
        clean = clean.replace("```json", "").replace("```", "")
        
        # Extract JSON
        start = clean.find("{")
        end = clean.rfind("}")

        if start == -1 or end == -1 or end <= start:
            logger.error(f"[{unit_identifier}] NO JSON BRACKETS FOUND")
            logger.error(f"[{unit_identifier}] Cleaned output ({len(clean)} chars):\n{clean[:500]}")
            raise ValueError("NO JSON FOUND IN MODEL OUTPUT")

        json_str = clean[start:end + 1]
        logger.debug(f"[{unit_identifier}] Extracted JSON ({len(json_str)} chars)")
        
        parsed = json.loads(json_str)
        validate_forensic_output(parsed)
        
        logger.info(f"  ✓ SUCCESS: {parsed.get('rule_type', 'unknown')}")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"[{unit_identifier}] JSON DECODE ERROR: {e}")
        if 'json_str' in locals():
            logger.error(f"[{unit_identifier}] Attempted JSON:\n{json_str[:500]}")
        return None
    except ValidationError as e:
        logger.error(f"[{unit_identifier}] SCHEMA VALIDATION ERROR: {e.message}")
        if 'parsed' in locals():
            logger.error(f"[{unit_identifier}] Invalid structure:\n{json.dumps(parsed, indent=2)[:500]}")
        return None
    except Exception as e:
        logger.error(f"[{unit_identifier}] COMPILATION ERROR: {e}")
        if 'decoded' in locals():
            logger.error(f"[{unit_identifier}] Response:\n{decoded[:500]}")
        return None

# --- 9. RUN PIPELINE ---
logger.info("PIPELINE: STARTING MISSION...")

parser = ClinicalProtocolParser()
chunks = parser.process_file(PDF_PATH) if os.path.exists(PDF_PATH) else []

logger.info(f"PIPELINE: Found {len(chunks)} chunks to compile")

compiled_results = []
for i, chunk in enumerate(chunks):
    logger.info(f"\n{'='*60}")
    logger.info(f"COMPILING [{i+1}/{len(chunks)}]: {chunk['code']}")
    logger.info(f"{'='*60}")
    
    metadata = compile_block(chunk['code'], chunk['text'])

    if metadata:
        rule_obj = ForensicRule(
            rule_code=chunk['code'],
            rule_type=metadata["rule_type"],
            text_description=chunk['text'],
            logic_config=metadata["logic_config"],
            scope_tags=metadata["scope_tags"],
            intent_tags=metadata["intent_tags"]
        )
        compiled_results.append(rule_obj.to_dict())
        logger.info(f"  STATUS: ✓ PASS - {chunk['code']}")
    else:
        logger.warning(f"  STATUS: ✗ SKIP - {chunk['code']}")

# --- 10. EXPORT ---
output_file = "medgate_knowledge_graph.json"
logger.info(f"\n{'='*60}")
logger.info(f"EXPORT: SAVING {len(compiled_results)} VALIDATED RULES TO {output_file}...")
logger.info(f"{'='*60}")

with open(output_file, "w") as f:
    json.dump(compiled_results, f, indent=2)

logger.info(f"\nSUCCESS RATE: {len(compiled_results)}/{len(chunks)} ({100*len(compiled_results)/len(chunks) if chunks else 0:.1f}%)")
logger.info("MISSION COMPLETE. DOWNLOAD JSON FROM THE OUTPUT TAB.")