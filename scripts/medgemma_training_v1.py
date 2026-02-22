"""
TRAINING SCRIPT: MEDGEMMA-NEUROMORPHIC-COMPILER-V1
ROLE: Neurosymbolic Structural Compiler (Clinical Guidelines -> Executable Logic)
TARGET MODEL: google/medgemma-1.5-4b-it
PRECISION: 4-bit NormalFloat (NF4) with FP16 Compute
CAPABILITY: Fine-tuned adapter for deterministic Knowledge Graph synthesis and clinical verification.
"""

import os mn
import json
import re
import logging
import torch
import gc
import subprocess
import sys

# --- ENVIRONMENT SETUP ---
# Configure hardware isolation and memory management parameters
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["WANDB_DISABLED"] = "true"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["BITSANDBYTES_NOWELCOME"] = "1"

print("Initializing High-Throughput Forensic Training Environment (MedGemma Trainer - TURBO)...")
print("="*70)

# ------------------------------------
# 0. DEPENDENCY MANAGEMENT
# ------------------------------------
# Enforce specific library versions required for MedGemma 1.5 4B IT structural compilation.
# Unsloth is removed to ensure standard Hugging Face Transformer compatibility for production.
print("-> Installing packages...")

install_cmd = """
pip uninstall -y unsloth unsloth_zoo > /dev/null 2>&1
pip install -q --no-cache-dir \
    "transformers>=4.48.0" \
    "peft>=0.7.0" \
    "accelerate>=0.26.0" \
    "bitsandbytes>=0.41.0" \
    "datasets>=2.16.0" \
    "jsonschema"
"""
subprocess.run(install_cmd, shell=True)

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)
from datasets import Dataset
from jsonschema import validate, ValidationError

print("Environment ready.")

# -------------------------------
# HUGGING FACE AUTHENTICATION
# -------------------------------
# Authenticate using Kaggle Secrets to access the gated Google MedGemma repository.
print("Authenticating with Hugging Face...")
from huggingface_hub import login
from kaggle_secrets import UserSecretsClient

user_secrets = UserSecretsClient()
hf_token = user_secrets.get_secret("HF_TOKEN")
login(token=hf_token)
print("Authentication successful.")

# -----------------------------------------------------
# 1. LOAD MODEL & TOKENIZER (FP16 SPEED OPTIMIZED)
# -----------------------------------------------------
# Initialize the base MedGemma model using NF4 quantization for 4-bit precision efficiency.
MODEL_ID = "google/medgemma-1.5-4b-it"

print(f"\nLoading base model ({MODEL_ID})...")

compute_dtype = torch.float16 

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=compute_dtype,
    bnb_4bit_use_double_quant=True,
)

# Clear VRAM fragmentation before loading the weights
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map={"": 0},
    trust_remote_code=True,
    torch_dtype=compute_dtype,
    attn_implementation="sdpa",
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)

# ---- PAD = EOS (NO NEW TOKEN INTRODUCTION) ----
# Align Pad and End-of-Sequence tokens to ensure sequence termination stability.
tokenizer.pad_token = tokenizer.eos_token
tokenizer.pad_token_id = tokenizer.eos_token_id

print(f"-> EOS token: {tokenizer.eos_token} (ID: {tokenizer.eos_token_id})")
print(f"-> PAD token: {tokenizer.pad_token} (ID: {tokenizer.pad_token_id})")

tokenizer.padding_side = "right"
model.config.pad_token_id = tokenizer.pad_token_id

# Configure model for k-bit training and activate gradient checkpointing to conserve memory.
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
model.config.use_cache = False

# LoRA Configuration targeting all major projection layers for maximized forensic specificity.
peft_config = LoraConfig(
    r=16, 
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)

model = get_peft_model(model, peft_config)
print("Model loaded and adapted.")
model.print_trainable_parameters()

# --------------------
# 2. DATASET
# --------------------
# Load the verified training dataset containing the clinical-to-symbolic mapping rules.
print("\nLoading dataset...")
dataset_path = "/kaggle/input/medgate-compiler-data/medgate_finetune_FINAL.jsonl"
raw_data = []
with open(dataset_path, "r") as f:
    for line in f:
        if line.strip():
            raw_data.append(json.loads(line))

print(f"Loaded {len(raw_data)} records.")

# Implement the standard Alpaca prompt template used for instruction-tuning datasets.
alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{}

### Input:
{}

### Response:
{}"""

# --------------------------------------------------------
# 3. TOKENIZATION (DYNAMIC PADDING SPEEDUP)
# --------------------------------------------------------
# Process dataset through prompt-masking to ensure loss is calculated only on JSON outputs.
max_seq_length = 2048

def tokenize_function(examples):
    res_input_ids = []
    res_attention_mask = []
    res_labels = []
    
    for instruction, input_text, output in zip(
        examples["instruction"],
        examples["input"],
        examples["output"],
    ):
        prompt_only = alpaca_prompt.format(instruction, input_text, "")
        full_text = alpaca_prompt.format(instruction, input_text, output) + tokenizer.eos_token
        
        full_enc = tokenizer(
            full_text, 
            truncation=True, 
            max_length=max_seq_length, 
            padding=False, 
        )
        
        prompt_enc = tokenizer(
            prompt_only, 
            truncation=True, 
            max_length=max_seq_length, 
            padding=False, 
        )
        
        ids = full_enc["input_ids"]
        mask = full_enc["attention_mask"]
        prompt_len = len(prompt_enc["input_ids"])
        
        # Mask prompt tokens with -100 so the model does not attempt to predict the instruction.
        actual_split = min(prompt_len, len(ids))
        label = [-100] * actual_split + ids[actual_split:]
        label = label[:len(ids)]
        
        res_input_ids.append(ids)
        res_attention_mask.append(mask)
        res_labels.append(label)

    return {
        "input_ids": res_input_ids,
        "attention_mask": res_attention_mask,
        "labels": res_labels
    }

hf_dataset = Dataset.from_list(raw_data)
tokenized_dataset = hf_dataset.map(
    tokenize_function,
    batched=True,
    remove_columns=hf_dataset.column_names
)

# -----------------------
# 4. DATA COLLATOR 
# -------------------------
# Setup the language modeling collator and training hyper-parameters.
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False
)

# ---------------------------------
# 5. TRAINING (HIGH THROUGHPUT)
# ----------------------------------
training_args = TrainingArguments(
    output_dir="outputs",
    per_device_train_batch_size=1, 
    gradient_accumulation_steps=16,
    warmup_steps=5,
    max_steps=100,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    optim="paged_adamw_8bit",
    weight_decay=0.01,
    lr_scheduler_type="linear",
    seed=42,
    report_to="none",
    save_strategy="no",
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    dataloader_num_workers=2,
    group_by_length=True,
)

# Specialized trainer implementing weighted loss for sequence termination tokens.
class TurboForensicTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        
        loss_fct = torch.nn.CrossEntropyLoss(reduction='none')
        shift_logits = logits[..., :-1, :].contiguous()
        shift_labels = labels[..., 1:].contiguous()

        # ---- MASK PAD FROM LOSS ----
        shift_labels = shift_labels.masked_fill(
            shift_labels == tokenizer.pad_token_id, -100
        )
        
        loss = loss_fct(
            shift_logits.view(-1, shift_logits.size(-1)),
            shift_labels.view(-1)
        )
        
        # Upsample weight for EOS tokens to ensure the Structural Compiler terminates JSON correctly.
        eos_mask = (shift_labels.view(-1) == tokenizer.eos_token_id).float()
        loss_weights = 1.0 + (eos_mask * 2.0)
        loss = (loss * loss_weights).sum() / loss_weights.sum()
        
        return (loss, outputs) if return_outputs else loss

    def training_step(self, model, inputs, num_items_in_batch=None):
        loss = super().training_step(model, inputs, num_items_in_batch)
        if self.state.global_step % 25 == 0:
            torch.cuda.empty_cache()
            gc.collect()
        return loss

trainer = TurboForensicTrainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=data_collator,
)

print("Training starting...")
trainer.train()

# -----------------------------
# 6. VERIFICATION 
# ------------------------------
# Perform deterministic verification test on the fine-tuned Structural Compiler logic.
print("\nRunning verification test...")
model.eval()
model.config.use_cache = True
torch.cuda.empty_cache()
gc.collect()

test_input = "For patients with suspected stroke, a non-contrast CT must be performed within 20 minutes of arrival."
device = "cuda:0"
inputs = tokenizer(
    [alpaca_prompt.format(
        "You are a Forensic Logic Parser. Convert the following clinical guideline text into an executable JSON schema.",
        test_input,
        ""
    )],
    return_tensors="pt",
).to(device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=512,
        do_sample=False,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.pad_token_id,
        repetition_penalty=1.2, 
    )

decoded_response = tokenizer.decode(
    outputs[0][inputs.input_ids.shape[1]:],
    skip_special_tokens=True
)

print("\n" + "-"*70)
print(f"INPUT: {test_input}")
print("-"*70)
print(f"GENERATED RESPONSE:\n{decoded_response}")
print("-"*70)

# ------------------
# 7. EXPORT
# -------------------
# Serialize the final LoRA adapter for deployment in the Nexus Forensic backend.
print("\nSaving adapter...")
save_path = "nexus_forensic_adapter_V2"
model.save_pretrained(save_path)
tokenizer.save_pretrained(save_path)
subprocess.run(f"zip -r nexus_adapter_v2.zip {save_path}", shell=True)
print("TRAINING COMPLETE - ALL LOGIC PRESERVED")