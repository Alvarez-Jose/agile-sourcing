"""
training/finetune.py

QLoRA fine-tuning of Qwen3-8B on UC policy Q&A data.
Tuned for a single NVIDIA 3080 Ti (12GB VRAM).

Usage:
    python training/finetune.py
    python training/finetune.py --epochs 5
    python training/finetune.py --dry-run
"""

import argparse
import os
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer, SFTConfig

BASE_MODEL = "Qwen/Qwen3-8B"
TRAIN_FILE = "training/dataset/train.jsonl"
EVAL_FILE = "training/dataset/eval.jsonl"
OUTPUT_DIR = "training/uc-policy-qwen3"
FINAL_DIR = "training/uc-policy-qwen3-final"

# LoRA rank 16 is a good middle ground — higher rank = more capacity but more VRAM
LORA_R = 16
LORA_ALPHA = 32  # typically 2x rank
LORA_DROPOUT = 0.05
LORA_TARGET = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

EPOCHS = 3
BATCH_SIZE = 1  # 12GB VRAM can't go higher without oom
GRAD_ACCUM = 8  # effective batch = 8
LEARNING_RATE = 2e-4
MAX_SEQ_LEN = 1024
WARMUP_RATIO = 0.05
SAVE_STEPS = 50
EVAL_STEPS = 50
LOG_STEPS = 10


def check_gpu():
    if not torch.cuda.is_available():
        print("ERROR: No CUDA GPU detected.")
        print("  Make sure you're on your PC with the 3080 Ti and CUDA drivers installed.")
        print("  Run: nvidia-smi   to verify your GPU is visible.")
        return False

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU detected: {gpu_name} ({vram_gb:.1f} GB VRAM)")

    if vram_gb < 10:
        print("WARNING: Less than 10GB VRAM. Training may OOM.")
        print("  Try reducing MAX_SEQ_LEN to 512 if you hit memory errors.")

    return True


def load_model_and_tokenizer():
    print(f"\nLoading base model: {BASE_MODEL}")
    print("First run will download ~16GB...")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,  # saves ~0.4 bits/param
        bnb_4bit_quant_type="nf4",       # NormalFloat4, best for LLMs
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16
    )
    model.config.use_cache = False  # needed for gradient checkpointing
    model.enable_input_require_grads()

    print(f"Model loaded. Parameters: {model.num_parameters() / 1e9:.2f}B")
    return model, tokenizer


def apply_lora(model):
    print("\nApplying QLoRA adapters...")

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET,
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


def format_messages(example):
    """Convert messages list to Qwen3 ChatML format."""
    messages = example["messages"]
    formatted = ""
    for msg in messages:
        formatted += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
    return {"text": formatted}


def load_data():
    print(f"\nLoading dataset...")
    print(f"  Train: {TRAIN_FILE}")
    print(f"  Eval:  {EVAL_FILE}")

    if not Path(TRAIN_FILE).exists():
        raise FileNotFoundError(
            f"Training data not found at {TRAIN_FILE}.\n"
            f"Run first: python training/generate_dataset.py"
        )

    dataset = load_dataset(
        "json",
        data_files={"train": TRAIN_FILE, "eval": EVAL_FILE}
    )
    dataset = dataset.map(format_messages)

    print(f"  Train examples: {len(dataset['train'])}")
    print(f"  Eval examples:  {len(dataset['eval'])}")
    return dataset


def train(model, tokenizer, dataset, epochs: int):
    print(f"\nStarting fine-tuning for {epochs} epochs...")
    print(f"  Effective batch size: {BATCH_SIZE * GRAD_ACCUM}")
    print(f"  Learning rate: {LEARNING_RATE}")
    print(f"  Max sequence length: {MAX_SEQ_LEN}")

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        num_train_epochs=epochs,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        learning_rate=LEARNING_RATE,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP_RATIO,
        max_seq_length=MAX_SEQ_LEN,
        dataset_text_field="text",
        fp16=False,
        bf16=True,  # 3080 Ti supports bfloat16
        logging_steps=LOG_STEPS,
        save_steps=SAVE_STEPS,
        eval_steps=EVAL_STEPS,
        eval_strategy="steps",
        save_strategy="steps",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none",
        dataloader_pin_memory=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        tokenizer=tokenizer,
    )

    print("\nTraining started. Watch GPU memory with: watch -n1 nvidia-smi")
    trainer.train()

    print(f"\nSaving final model to {FINAL_DIR}...")
    trainer.save_model(FINAL_DIR)
    tokenizer.save_pretrained(FINAL_DIR)

    print("\nFine-tuning complete.")
    print(f"Model saved to: {FINAL_DIR}")
    print(f"\nNext step: python training/evaluate.py")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen3-8B on UC policy data")
    parser.add_argument("--epochs", type=int, default=EPOCHS, help="Training epochs")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup only, no training")
    args = parser.parse_args()

    print("--- Agile Sourcing QLoRA Fine-Tuning ---")

    if not check_gpu():
        return

    if args.dry_run:
        print("\nDry run — validating dataset and imports only...")
        load_data()
        print("Setup looks good. Run without --dry-run to start training.")
        return

    model, tokenizer = load_model_and_tokenizer()
    model = apply_lora(model)
    dataset = load_data()
    train(model, tokenizer, dataset, args.epochs)


if __name__ == "__main__":
    main()
