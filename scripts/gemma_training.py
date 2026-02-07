import os
# Force the process to only see ONE GPU. 
# This prevents the DataParallel "illegal memory access" crash on Kaggle T4x2.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["WANDB_DISABLED"] = "true"

import json
import torch

print(" Initializing Forensic Training Environment (Standard Trainer)...")

# =========================================================
# 0. DEPENDENCY MANAGEMENT
# =========================================================
print("-> Installing packages...")

install_cmd = """
pip uninstall -y unsloth unsloth_zoo > /dev/null 2>&1
pip install -q --no-cache-dir \
    "transformers>=4.30.0,<5.0.0" \
    "peft>=0.4.0" \
    "accelerate>=0.20.0" \
    "bitsandbytes>=0.40.0" \
    "datasets>=2.0.0" \
    "jsonschema"
"""

import subprocess
result = subprocess.run(install_cmd, shell=True, capture_output=True, text=True)

os.environ["BITSANDBYTES_NOWELCOME"] = "1"

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    default_data_collator,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)
from datasets import Dataset

try:
    from jsonschema import validate, ValidationError
except ImportError:
    subprocess.run("pip install jsonschema --quiet", shell=True)
    from jsonschema import validate, ValidationError

print(" Environment ready.")

# =========================================================
# HUGGING FACE AUTHENTICATION
# =========================================================
print(" Authenticating with Hugging Face...")
from huggingface_hub import login
from kaggle_secrets import UserSecretsClient

user_secrets = UserSecretsClient()
hf_token = user_secrets.get_secret("HF_TOKEN")
login(token=hf_token)
print(" Authentication successful.")

# =========================================================
# 1. LOAD MODEL & TOKENIZER
# =========================================================

MODEL_ID = "google/gemma-2-2b-it"

print(f"\n Loading base model ({MODEL_ID})...")

compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
print(f"-> Using compute dtype: {compute_dtype}")

# SWITCH TO 8-BIT QUANTIZATION (more stable than 4-bit for Gemma 2)
bnb_config = BitsAndBytesConfig(
    load_in_8bit=True,
    llm_int8_threshold=6.0,
)

# Clear CUDA cache
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map={"": 0},
    trust_remote_code=True,
    torch_dtype=compute_dtype,
    attn_implementation="eager",
)

if torch.cuda.is_available():
    torch.cuda.empty_cache()

# Load Tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.padding_side = "right"

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
    model.config.pad_token_id = tokenizer.pad_token_id
    print("-> Pad token set to EOS token.")

# Prepare for QLoRA Training
# Enabled gradient checkpointing here to prevent the OOM crash on T4 when using 8-bit quantization with Gemma 2.
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
model.config.use_cache = False

print("-> Model prepared for QLoRA training.")

# Apply LoRA
peft_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)

model = get_peft_model(model, peft_config)

print(" Model loaded and adapted.")
model.print_trainable_parameters()

# =========================================================
# 2. DATASET
# =========================================================
print("\n Loading dataset...")

dataset_path = "medgate_finetune_FINAL.jsonl"
if not os.path.exists(dataset_path):
    found = False
    for root, dirs, files in os.walk("/kaggle/input"):
        if "medgate_finetune_FINAL.jsonl" in files:
            dataset_path = os.path.join(root, "medgate_finetune_FINAL.jsonl")
            found = True
            break

    if not found:
        print(" Dataset not found. Creating dummy...")
        with open(dataset_path, "w") as f:
            dummy = {
                "instruction": "Test",
                "input": "Test Input",
                "output": '{"rule_type": "unsupported", "logic_config": {}, "scope_tags": [], "intent_tags": []}'
            }
            f.write(json.dumps(dummy) + "\n")

print(f"-> Dataset: {dataset_path}")

raw_data = []
with open(dataset_path, "r") as f:
    for line in f:
        if line.strip():
            raw_data.append(json.loads(line))

print(f" Loaded {len(raw_data)} records.")

alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{}

### Input:
{}

### Response:
{}"""

# =========================================================
# 3. TOKENIZATION
# =========================================================
print(" Tokenizing...")

max_seq_length = 512

def tokenize_function(examples):
    texts = []
    for instruction, input_text, output in zip(
        examples["instruction"],
        examples["input"],
        examples["output"],
    ):
        text = alpaca_prompt.format(instruction, input_text, output) + tokenizer.eos_token
        texts.append(text)

    tokenized = tokenizer(
        texts,
        truncation=True,
        max_length=max_seq_length,
        padding="max_length",
        return_tensors=None,
    )

    tokenized["labels"] = [
        [token_id if token_id != tokenizer.pad_token_id else -100 for token_id in ids]
        for ids in tokenized["input_ids"]
    ]

    return tokenized

hf_dataset = Dataset.from_list(raw_data)

tokenized_dataset = hf_dataset.map(
    tokenize_function,
    batched=True,
    num_proc=1,
    remove_columns=hf_dataset.column_names,
)

print(f"-> Columns: {tokenized_dataset.column_names}")
print(f"-> Sample length: {len(tokenized_dataset[0]['input_ids'])} tokens")

# =========================================================
# 4. DATA COLLATOR
# =========================================================
data_collator = default_data_collator

# =========================================================
# 5. TRAINING
# =========================================================
print("\n Starting training...")

training_args = TrainingArguments(
    output_dir="outputs",
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    warmup_steps=5,
    max_steps=100,
    learning_rate=2e-4,
    fp16=False,
    bf16=True,
    logging_steps=10,
    optim="adamw_8bit",  # Changed from paged_adamw_8bit
    weight_decay=0.01,
    lr_scheduler_type="linear",
    seed=42,
    report_to="none",
    save_strategy="steps",
    save_steps=50,
    # SURGICAL FIX: Matches the prepare_model call to ensure memory stays within T4 limits
    gradient_checkpointing=True,
    dataloader_num_workers=0,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=data_collator,
)

trainer.train()

print(" Training complete.")

# =========================================================
# 6. VERIFICATION & EXPORT
# =========================================================
print("\n🔎 Verification test...")

model.eval()
model.config.use_cache = True

test_input = (
    "For patients with suspected stroke, a non-contrast CT "
    "must be performed within 20 minutes of arrival."
)

device = "cuda:0"

inputs = tokenizer(
    [
        alpaca_prompt.format(
            "You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.",
            test_input,
            "",
        )
    ],
    return_tensors="pt",
).to(device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=256,
        use_cache=True,
        do_sample=False,
    )

decoded_output = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

json_start = decoded_output.find("{")
json_end = decoded_output.rfind("}")

raw_json = decoded_output[json_start:json_end + 1] if json_start != -1 else ""

print("-" * 60)
print("INPUT:")
print(test_input)
print("-" * 60)
print("RAW OUTPUT:")
print(raw_json)
print("-" * 60)

print(" Parsing JSON...")

parsed_json = None
try:
    parsed_json = json.loads(raw_json)
    print(" JSON parsing successful.")
except json.JSONDecodeError as e:
    print(" JSON parsing failed.")
    print(str(e))

MEDGATE_SCHEMA = {
    "type": "object",
    "required": ["rule_type"],
    "properties": {
        "intent_tags": {"type": "array", "items": {"type": "string"}},
        "logic_config": {"type": "object"},
        "rule_type": {"type": "string"},
        "scope_tags": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "additionalProperties": True,
}

if parsed_json is not None:
    print(" Validating schema...")
    try:
        validate(instance=parsed_json, schema=MEDGATE_SCHEMA)
        print(" Schema validation PASSED.")
    except ValidationError as e:
        print(" Schema validation FAILED.")
        print(e.message)

save_path = "medgate_forensic_adapter_v1"

model.save_pretrained(save_path)
tokenizer.save_pretrained(save_path)

print(f"\n Adapter saved to {save_path}")
print("-> Zipping...")

subprocess.run("zip -r medgate_adapter.zip medgate_forensic_adapter_v1", shell=True)

print(" medgate_adapter.zip ready.")