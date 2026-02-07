# =========================================================
# MEDGATE FACTORY: THE NEUROSYMBOLIC KNOWLEDGE COMPILER (v3.2)
# =========================================================

import subprocess
import os
import sys
import json
import re
import logging
import gc
from IPython.display import FileLink

# 1. CLEAN INSTALL (Exactly as per Golden Script)
print("-> Installing core components...")
subprocess.run("pip install -q --no-cache-dir bitsandbytes transformers peft accelerate docling jsonschema pypdfium2", shell=True)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from huggingface_hub import login
from kaggle_secrets import UserSecretsClient
from jsonschema import validate

# Docling Imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# --- VISIBILITY LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MedGateCompiler")

# --- 2. CONFIGURATION & AUTH ---
PDF_PATH = "/kaggle/input/kenya-national-malaria-policy-2024/National_Malaria_Policy_2024.pdf"
ADAPTER_PATH = "/kaggle/input/medgate-forensic-adapter-v4/medgate_forensic_adapter_PRODUCTION"
BASE_MODEL = "google/medgemma-1.5-4b-it"

print("-> Authenticating with Hugging Face...")
user_secrets = UserSecretsClient()
hf_token = user_secrets.get_secret("HF_TOKEN")
login(token=hf_token)

# --- 3. THE CONSTITUTION (SCHEMA) ---
BASE_SCHEMA = {
    "type": "object",
    "required": ["rule_type", "logic_config", "scope_tags", "intent_tags"],
    "properties": {
        "rule_type": {"type": "string"},
        "scope_tags": {"type": "array"},
        "intent_tags": {"type": "array"},
        "logic_config": {"type": "object"}
    }
}

# --- 4. LOAD MODEL (Golden Script Pattern) ---
print("-> Loading Tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True, token=hf_token)
tokenizer.padding_side = "left"
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("-> Loading Base Model (4-bit Stability Mode)...")
compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=compute_dtype,
    bnb_4bit_use_double_quant=True,
)

base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map={"": 0},
    trust_remote_code=True,
    torch_dtype=compute_dtype,
    token=hf_token
)

# CRITICAL: Prevent Device-Side Assert (Matches Golden Script)
base_model.resize_token_embeddings(len(tokenizer))

print(f"-> Attaching Adapter from {ADAPTER_PATH}...")
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()
model.config.use_cache = True

# --- 5. PARSER ENGINE (DOCLING) ---
class ForensicParser:
    def __init__(self):
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options, backend=PyPdfiumDocumentBackend)}
        )

    def get_chunks(self, file_path):
        logger.info(f"PARSER: EXTRACTING CHUNKS FROM {file_path}")
        result = self.converter.convert(file_path)
        md_text = result.document.export_to_markdown()
        
        # LOGGING: See the raw Markdown result
        print(f"\n--- [PARSER] RAW MARKDOWN EXTRACTED (FIRST 1000 CHARS) ---")
        print(md_text[:1000])
        print("---------------------------------------------------------")

        # ADAPTED REGEX: Unified capturing group for Malaria Policy numbering (e.g., 1.1, 4.1.2.1)
        split_pattern = r"(?m)^#+\s+(?:Section\s+|Tag\s+)?((?:A-\d{4})|(?:\d+(?:\.\d+)*))\.?\s+"
        tokens = re.split(split_pattern, md_text)
        
        chunks = []
        clean_tokens = [t for t in tokens if t is not None]
        for i in range(1, len(clean_tokens), 2):
            if i + 1 < len(clean_tokens):
                chunks.append({"code": clean_tokens[i], "text": clean_tokens[i+1].strip()[:1200]})
        return chunks

# --- 6. EXTRACTION LOGIC (Surgical Balanced-Bracket Fix) ---
def extract_nested_json(text):
    """Finds and extracts the first balanced JSON object to handle nested structures."""
    start_idx = text.find('{')
    if start_idx == -1: return None
    
    bracket_count = 0
    for i in range(start_idx, len(text)):
        if text[i] == '{':
            bracket_count += 1
        elif text[i] == '}':
            bracket_count -= 1
            if bracket_count == 0:
                return text[start_idx:i+1]
    return None

def compile_block(unit_id, text_chunk):
    alpaca_prompt = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.

### Input:
{text_chunk}

### Response:
"""
    inputs = tokenizer(alpaca_prompt, return_tensors="pt", add_special_tokens=True).to("cuda")
    
    with torch.no_grad():
        outputs = model.generate(
            input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask,
            max_new_tokens=256,
            min_new_tokens=20,
            do_sample=False,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    decoded = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
    
    # VISIBILITY: RAW OUTPUT FROM BRAIN
    print(f"\n--- [DEBUG: {unit_id}] RAW MODEL RESPONSE ---")
    print(decoded)
    print("-" * 40)

    json_str = extract_nested_json(decoded)
    if json_str:
        try:
            parsed = json.loads(json_str)
            validate(instance=parsed, schema=BASE_SCHEMA)
            return parsed
        except Exception as e:
            logger.warning(f"[{unit_id}] JSON/Schema Error: {e}")
    return None

# --- 7. PIPELINE EXECUTION ---
logger.info("PIPELINE: STARTING COMPILATION...")
if not os.path.exists(PDF_PATH):
    logger.error(f"PDF NOT FOUND AT {PDF_PATH}")
    sys.exit(1)

parser = ForensicParser()
chunks = parser.get_chunks(PDF_PATH)

knowledge_graph = []
for i, chunk in enumerate(chunks):
    logger.info(f"PROCESSING [{i+1}/{len(chunks)}]: {chunk['code']}")
    
    # LOGGING: See exactly what text is being sent to the model
    print(f"\n--- [INPUT: {chunk['code']}] PARSED TEXT SENT TO MODEL ---")
    print(chunk['text'])
    print("-" * 40)

    logic_gate = compile_block(chunk['code'], chunk['text'])
    
    if logic_gate:
        logic_gate["rule_code"] = chunk['code']
        logic_gate["source_text"] = chunk['text']
        knowledge_graph.append(logic_gate)
        logger.info(f"   ✓ PASS: {logic_gate['rule_type']}")
    else:
        logger.info(f"   ✗ SKIP: Logic compilation failed.")
    
    if i % 5 == 0:
        torch.cuda.empty_cache()
        gc.collect()

# --- 8. EXPORT ---
output_file = "medgate_knowledge_graph.json"
with open(output_file, "w") as f:
    json.dump(knowledge_graph, f, indent=2)

logger.info(f"MISSION COMPLETE: {len(knowledge_graph)} rules exported to {output_file}")

# --- 9. DOWNLOAD LINK ---
FileLink(output_file)