# =========================================================
# STEP 7: EDGE CONVERSION (MEDGEMMA 4B -> GGUF)
# =========================================================
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import os
import glob
from huggingface_hub import login
from kaggle_secrets import UserSecretsClient

print("STARTING EXPORT PIPELINE...")

# 0. AUTHENTICATION
print("Authenticating with Hugging Face...")
user_secrets = UserSecretsClient()
hf_token = user_secrets.get_secret("HF_TOKEN")
login(token=hf_token)
print("Authentication successful.")

# 1. DYNAMIC PATH FINDER
# We need to find where Kaggle mounted your adapter dataset.
print("\nScanning for adapter in /kaggle/input...")
adapter_config_path = None

# Search recursively for adapter_config.json
search_pattern = "/kaggle/input/**/adapter_config.json"
found_files = glob.glob(search_pattern, recursive=True)

if not found_files:
    raise FileNotFoundError("CRITICAL: Could not find 'adapter_config.json' in /kaggle/input. Ensure the dataset is attached.")

# We take the directory of the first valid config found
adapter_path = os.path.dirname(found_files[0])
print(f"✅ FOUND ADAPTER AT: {adapter_path}")

base_model_id = "google/medgemma-1.5-4b-it"
temp_merged_path = "medgemma_merged_16bit"
final_gguf_name = "medgate_brain_4b_Q8.gguf"

# 2. MERGE (The Brain Transplant)
print(f"\nLoading Base Model: {base_model_id}...")
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_id,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

print(f"Attaching Adapter: {adapter_path}...")
model = PeftModel.from_pretrained(base_model, adapter_path)

print("Merging Weights...")
model = model.merge_and_unload()

print(f"Saving Intermediate 16-bit Model to {temp_merged_path}...")
model.save_pretrained(temp_merged_path)
tokenizer = AutoTokenizer.from_pretrained(base_model_id)
tokenizer.save_pretrained(temp_merged_path)

# Cleanup VRAM
del model
del base_model
torch.cuda.empty_cache()

# 3. COMPILE LLAMA.CPP
print("\nBuilding Llama.cpp (Quantization Engine)...")
if not os.path.exists("llama.cpp"):
    !git clone https://github.com/ggerganov/llama.cpp
    !cd llama.cpp && make clean && make -j

!pip install -r llama.cpp/requirements.txt --quiet

# 4. CONVERT TO GGUF
print(f"\nQuantizing to {final_gguf_name} (Q8_0)...")

# Handle potential script name changes in llama.cpp
if os.path.exists("llama.cpp/convert_hf_to_gguf.py"):
    script_path = "llama.cpp/convert_hf_to_gguf.py"
else:
    script_path = "llama.cpp/convert.py"

!python {script_path} {temp_merged_path} \
    --outfile {final_gguf_name} \
    --outtype q8_0

# 5. GENERATE DOWNLOAD
print("\nCONVERSION COMPLETE.")
from IPython.display import FileLink
print(f"DOWNLOAD YOUR BRAIN ({final_gguf_name}):")
FileLink(final_gguf_name)