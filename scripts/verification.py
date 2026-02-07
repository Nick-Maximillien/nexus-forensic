import subprocess
import os

# 1. CLEAN INSTALL (RUN THIS FIRST AFTER RESTART)
print("-> Installing core components...")
subprocess.run("pip install -q --no-cache-dir bitsandbytes transformers peft accelerate", shell=True)

import torch
import json
import gc
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from huggingface_hub import login
from kaggle_secrets import UserSecretsClient

# 2. HF AUTHENTICATION (RESTORED)
print("-> Authenticating with Hugging Face...")
user_secrets = UserSecretsClient()
hf_token = user_secrets.get_secret("HF_TOKEN")
login(token=hf_token)

# 3. CONFIG
BASE_MODEL = "google/medgemma-1.5-4b-it"
ADAPTER_PATH = "/kaggle/input/medgate-forensic-adapter-v4/medgate_forensic_adapter_PRODUCTION"

# 4. LOAD TOKENIZER (SURGICAL ALIGNMENT)
print("-> Loading Tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True, token=hf_token)

# Gemma/MedGemma Fix: Ensure left-padding for generation
tokenizer.padding_side = "left"
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# 5. LOAD MODEL WITH DTYPE STABILITY
print("-> Loading Base Model (4-bit)...")
# Using bfloat16 to match MedGemma's native training and prevent CUDA asserts
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

# CRITICAL: Prevent index out of range (Device-Side Assert)
base_model.resize_token_embeddings(len(tokenizer))

print(f"-> Attaching Adapter from {ADAPTER_PATH}...")
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

# 6. STABLE FORENSIC INFERENCE (EXPANDED TESTS)
test_cases = [
    "For patients with suspected stroke, a non-contrast CT must be performed within 20 minutes of arrival.",
    "Aspirin 325mg should be given to all STEMI patients unless contraindicated.",
    "Antibiotics must be administered within 1 hour for patients with septic shock.",
    "Warfarin must be discontinued at least 5 days prior to elective major surgery.",
    "An ECG should be performed within 10 minutes for any patient presenting with chest pain.",
    "All patients with a suspected hip fracture must have surgery within 36 hours."
]

alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.

### Input:
{}

### Response:
"""

print("\n" + "="*70)
print("🚀 TRIGGERING STABLE LOGIC EXTRACTION")
print("="*70)

for i, test_input in enumerate(test_cases, 1):
    print(f"\n[TEST {i}] Input: {test_input}")
    
    prompt = alpaca_prompt.format(test_input)
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=True).to("cuda")

    with torch.no_grad():
        outputs = model.generate(
            input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask,
            max_new_tokens=256,
            min_new_tokens=20,     # Force speech to bypass silence artifacts
            do_sample=False,        # Deterministic logic
            repetition_penalty=1.1, 
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    print("\n--- COMPILED LOGIC ---")
    print(generated_text.strip())
    
    if "{" in generated_text:
        print("✅ SUCCESS: System Stabilized.")
    else:
        print("⚠️ Output generated but JSON markers missing.")
    print("-" * 70)

print("\n🚀 ALL TESTS COMPLETE.")