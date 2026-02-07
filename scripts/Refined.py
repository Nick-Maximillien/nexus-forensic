# =========================================================
# MEDGATE FACTORY: THE GPU KNOWLEDGE COMPILER (v2)
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
    level=logging.INFO,
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
# Dynamically locate the PDF based on your recent logs
PDF_INPUT_DIR = "/kaggle/input/medgate-compiler-pdf/"
PDF_PATH = os.path.join(PDF_INPUT_DIR, "doc.pdf")

# Locate the Adapter
ADAPTER_PATH = "/kaggle/input/medgate-forensic-adapter-v1/medgate_forensic_adapter_v1"
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
    logger.warning(f"AUTH: HF_TOKEN NOT FOUND. ENSURE MODEL ACCESS IS PUBLIC OR TOKEN IS SET. ERROR: {e}")

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
        "properties": {"anchor": {"type": "string"}, "target": {"type": "string"}, "max_delay_minutes": {"type": ["number", "null"]}}
    },
    "threshold": {
        "required": ["target_vital", "operator"],
        "properties": {"target_vital": {"type": "string"}, "operator": {"enum": ["<", ">", "<=", ">=", "=", "!="]}, "min_value": {"type": ["number", "null"]}, "max_value": {"type": ["number", "null"]}, "unit": {"type": ["string", "null"]}}
    },
    "existence": {
        "required": ["required_artifact"],
        "properties": {"required_artifact": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}}
    },
    "contra": {
        "required": ["forbidden_treatment"],
        "properties": {"forbidden_treatment": {"type": "string"}, "trigger_drug": {"type": ["string", "null"]}, "trigger_condition": {"type": ["string", "null"]}}
    },
    "exclusive": {
        "required": ["event_1", "event_2"],
        "properties": {"event_1": {"type": "string"}, "event_2": {"type": "string"}}
    },
    "monotonic": {
        "required": ["event_type"],
        "properties": {"event_type": {"type": "string"}}
    },
    "conditional_existence": {
        "required": ["trigger_assertion", "required_artifact"],
        "properties": {"trigger_assertion": {"type": "string"}, "required_artifact": {"type": "string"}}
    },
    "count_sanity": {
        "required": ["event_type", "max_count"],
        "properties": {"event_type": {"type": "string"}, "max_count": {"type": "integer"}}
    },
    "duplicate": {"type": "object", "additionalProperties": True},
    "protocol_validity": {"type": "object", "additionalProperties": True}
}

def validate_forensic_output(instance):
    """The Hard Symbolic Gate """
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
        try:
            result = self.converter.convert(file_path)
            md_output = result.document.export_to_markdown()
            logger.info(f"DOCLING: CONVERSION COMPLETE ({len(md_output)} CHARS).")
            return md_output
        except Exception as e:
            logger.error(f"DOCLING: CRITICAL ERROR: {e}")
            raise e

class ClinicalProtocolParser(BaseParser):
    """Target: Hierarchical Documents """
    def process_file(self, file_path):
        md_text = self.extract_markdown(file_path)
        # Regex logic for tags and rules
        split_pattern = r"(?m)^#+\s+(?:Section\s+|Tag\s+)?(?:(A-\d{4})|(\d+(?:\.\d+)*))\.?\s+"
        tokens = re.split(split_pattern, md_text)
        
        chunks = []
        clean_tokens = [t for t in tokens if t is not None]
        logger.info(f"PARSER: SCANNING {len(clean_tokens)} TOKENS...")

        for i in range(1, len(clean_tokens), 2):
            if i+1 >= len(clean_tokens): break
            identifier = clean_tokens[i]
            content = clean_tokens[i+1]
            
            if len(content.strip()) < 20: continue
            
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
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True
)

logger.info(f"MODEL: ATTACHING ADAPTER FROM {ADAPTER_PATH}")
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()
logger.info("MODEL: COMPILER READY ON GPU.")

# --- 7. THE COMPILER LOOP ---
def compile_block(unit_identifier, text_chunk):
    """Neuro-Symbolic Compilation """
    alpaca_prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.

### Input:
{text_chunk}

### Response:
"""
    inputs = tokenizer(alpaca_prompt, return_tensors="pt").to("cuda")
    
    try:
        with torch.no_grad():
            outputs = model.generate(
                **inputs, 
                max_new_tokens=512,
                do_sample=False, 
                pad_token_id=tokenizer.eos_token_id
            )
        
        output_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        raw_json = output_text.split("### Response:")[-1].strip()
        
        # Surgical JSON extraction
        json_match = re.search(r"(\{.*\})", raw_json, re.DOTALL)
        if not json_match:
            raise ValueError("NO JSON STRUCTURE FOUND")
            
        parsed = json.loads(json_match.group(1))
        
        # THE HARD GATE
        validate_forensic_output(parsed)
        return parsed

    except Exception as e:
        logger.error(f"FAIL [{unit_identifier}]: {str(e)}")
        return None

# --- 8. RUN PIPELINE ---
logger.info("PIPELINE: STARTING MISSION...")

# 1. Parse PDF
parser = ClinicalProtocolParser()
if os.path.exists(PDF_PATH):
    chunks = parser.process_file(PDF_PATH)
    logger.info(f"PIPELINE: PARSED {len(chunks)} BLOCKS.")
else:
    logger.error(f"PIPELINE: PDF NOT FOUND AT {PDF_PATH}. CHECK KAGGLE INPUTS.")
    chunks = []

# 2. Compile and Validate
compiled_results = []
for i, chunk in enumerate(chunks):
    logger.info(f"COMPILING [{i+1}/{len(chunks)}]: {chunk['code']}")
    metadata = compile_block(chunk['code'], chunk['text'])
    
    if metadata:
        rule_obj = ForensicRule(
            rule_code=chunk['code'],
            rule_type=metadata.get('rule_type'),
            text_description=chunk['text'],
            logic_config=metadata.get('logic_config'),
            scope_tags=metadata.get('scope_tags'),
            intent_tags=metadata.get('intent_tags')
        )
        compiled_results.append(rule_obj.to_dict())
        logger.info(f"STATUS: PASS - {chunk['code']}")
    else:
        logger.warning(f"STATUS: SKIP - {chunk['code']}")

# --- 9. EXPORT ---
output_file = "medgate_knowledge_graph.json"
logger.info(f"EXPORT: SAVING {len(compiled_results)} VALIDATED RULES TO {output_file}...")
with open(output_file, "w") as f:
    json.dump(compiled_results, f, indent=2)

logger.info("MISSION COMPLETE. DOWNLOAD JSON FROM THE OUTPUT TAB.")