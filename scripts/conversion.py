# ---------------------------------------------------------
# STEP 0: AUTO-DETECT ADAPTER PATH
# ---------------------------------------------------------
import os

print("🔍 Scanning for MedGate Adapter...")
adapter_path = None

# Walk through the input directory to find 'adapter_config.json'
for root, dirs, files in os.walk("/kaggle/input"):
    if "adapter_config.json" in files:
        adapter_path = root
        print(f"✅ Found Adapter at: {adapter_path}")
        break

if not adapter_path:
    print("❌ CRITICAL ERROR: Could not find 'adapter_config.json' in /kaggle/input.")
    print("   Did you attach the 'medgate-forensic-adapter' dataset?")
    raise FileNotFoundError("Adapter not found.")

# ---------------------------------------------------------
# STEP 1: INSTALL STANDARD TOOLS (No Unsloth)
# ---------------------------------------------------------
print("\n🛠️ Installing Dependencies...")
!pip install --upgrade pip --quiet
!pip install "transformers>=4.38.0" "peft>=0.10.0" "accelerate>=0.27.0" "huggingface_hub" "sentencepiece" --quiet

# ---------------------------------------------------------
# STEP 2: AUTHENTICATE
# ---------------------------------------------------------
from huggingface_hub import login
from kaggle_secrets import UserSecretsClient

try:
    user_secrets = UserSecretsClient()
    hf_token = user_secrets.get_secret("HF_TOKEN")
    login(token=hf_token)
    print("✅ Auth Successful.")
except:
    print("⚠️ Could not auto-authenticate. Ensure HF_TOKEN is in Secrets.")

# ---------------------------------------------------------
# STEP 3: MERGE ADAPTER INTO BASE MODEL
# ---------------------------------------------------------
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base_model_id = "google/gemma-2-2b-it"
temp_merged_path = "medgate_merged_model_16bit"

print(f"\n🧠 Loading Base Model: {base_model_id}")
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_id,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

print(f"🔗 Attaching Adapter from: {adapter_path}")
model = PeftModel.from_pretrained(base_model, adapter_path)

print("⚡ Merging Weights (Brain Transplant)...")
model = model.merge_and_unload()

print(f"💾 Saving Merged Model to: {temp_merged_path}")
model.save_pretrained(temp_merged_path)
tokenizer = AutoTokenizer.from_pretrained(base_model_id)
tokenizer.save_pretrained(temp_merged_path)

print("✅ Merge Complete. Clearing VRAM...")
del model
del base_model
torch.cuda.empty_cache()

# ---------------------------------------------------------
# STEP 4: COMPILE LLAMA.CPP & CONVERT TO GGUF
# ---------------------------------------------------------
print("\n🛠️ Building Llama.cpp...")
!git clone https://github.com/ggerganov/llama.cpp > /dev/null 2>&1
%cd llama.cpp
!make clean > /dev/null 2>&1
!make > /dev/null 2>&1
!pip install -r requirements.txt --quiet

print("\n📦 Converting to GGUF (Q8_0 - High Accuracy)...")
output_gguf = "../medgate_brain_8bit.gguf"

# Run conversion script
!python convert_hf_to_gguf.py ../medgate_merged_model_16bit \
    --outfile {output_gguf} \
    --outtype q8_0

# ---------------------------------------------------------
# STEP 5: DELIVER ARTIFACT
# ---------------------------------------------------------
from IPython.display import FileLink
%cd ..

if os.path.exists("medgate_brain_8bit.gguf"):
    print(f"\n✅ SYSTEM SUCCESS.")
    print(f"⬇️ DOWNLOAD LINK GENERATED BELOW:")
    display(FileLink(r'medgate_brain_8bit.gguf'))
else:
    print("❌ Conversion failed.")