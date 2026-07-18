"""
finetune_a100.py — Full fine-tune on A100 80GB (no QLoRA needed)

Usage:
    python finetune_a100.py
    python finetune_a100.py --epochs 5
    python finetune_a100.py --dry-run
"""

import argparse
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from trl import SFTTrainer, SFTConfig

# ── Config ────────────────────────────────────────────────────────────────────
BASE_MODEL  = "Qwen/Qwen3-8B"
TRAIN_FILE  = "/workspace/dataset/train.jsonl"
EVAL_FILE   = "/workspace/dataset/eval.jsonl"
OUTPUT_DIR  = "/workspace/uc-policy-qwen3-a100"
FINAL_DIR   = "/workspace/uc-policy-qwen3-a100-final"

# A100 80GB — full bfloat16, no quantization needed
EPOCHS       = 5
BATCH_SIZE   = 8      # A100 can handle 8x vs 1x on 4070 Ti
GRAD_ACCUM   = 2      # effective batch = 16
LR           = 1e-5   # lower LR for full fine-tune vs QLoRA
MAX_SEQ_LEN  = 2048   # double the local run
WARMUP_RATIO = 0.05
SAVE_STEPS   = 100
EVAL_STEPS   = 100
LOG_STEPS    = 10


def check_gpu():
    if not torch.cuda.is_available():
        print("ERROR: No GPU detected.")
        return False
    name   = torch.cuda.get_device_name(0)
    vram   = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {name} ({vram:.1f} GB VRAM)")
    return True


def load_model_and_tokenizer():
    print(f"Loading {BASE_MODEL} in bfloat16 (full precision, no quantization)...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    tokenizer.pad_token    = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype   = torch.bfloat16,
        device_map    = "auto",
        trust_remote_code = True,
    )
    model.enable_input_require_grads()
    model.config.use_cache = False

    total_params = sum(p.numel() for p in model.parameters()) / 1e9
    print(f"Model loaded: {total_params:.2f}B parameters (full fine-tune — all layers trainable)")
    return model, tokenizer


def format_messages(example):
    messages  = example["messages"]
    formatted = ""
    for msg in messages:
        formatted += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
    return {"text": formatted}


def load_data():
    print(f"Loading dataset...")
    dataset = load_dataset("json", data_files={"train": TRAIN_FILE, "eval": EVAL_FILE})
    dataset = dataset.map(format_messages)
    print(f"  Train: {len(dataset['train'])} examples")
    print(f"  Eval:  {len(dataset['eval'])} examples")
    return dataset


def train(model, tokenizer, dataset, epochs):
    print(f"\nStarting full fine-tune — {epochs} epochs on A100 80GB")
    print(f"  Batch size: {BATCH_SIZE} × grad_accum {GRAD_ACCUM} = effective {BATCH_SIZE * GRAD_ACCUM}")
    print(f"  Max sequence length: {MAX_SEQ_LEN} tokens")
    print(f"  Learning rate: {LR}")

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    config = SFTConfig(
        output_dir                  = OUTPUT_DIR,
        num_train_epochs            = epochs,
        per_device_train_batch_size = BATCH_SIZE,
        per_device_eval_batch_size  = BATCH_SIZE,
        gradient_accumulation_steps = GRAD_ACCUM,
        gradient_checkpointing      = True,
        optim                       = "adamw_torch_fused",  # faster on A100
        learning_rate               = LR,
        lr_scheduler_type           = "cosine",
        warmup_ratio                = WARMUP_RATIO,
        max_seq_length              = MAX_SEQ_LEN,
        dataset_text_field          = "text",
        bf16                        = True,
        fp16                        = False,
        logging_steps               = LOG_STEPS,
        save_steps                  = SAVE_STEPS,
        eval_steps                  = EVAL_STEPS,
        eval_strategy               = "steps",
        save_strategy               = "steps",
        load_best_model_at_end      = True,
        metric_for_best_model       = "eval_loss",
        report_to                   = "none",
        dataloader_num_workers      = 4,
    )

    trainer = SFTTrainer(
        model         = model,
        args          = config,
        train_dataset = dataset["train"],
        eval_dataset  = dataset["eval"],
        processing_class = tokenizer,
    )

    print("\nTraining started — watch GPU with: nvidia-smi -l 1")
    trainer.train()

    print(f"\nSaving model to {FINAL_DIR}...")
    trainer.save_model(FINAL_DIR)
    tokenizer.save_pretrained(FINAL_DIR)
    print(f"Done. Model saved to {FINAL_DIR}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs",  type=int,  default=EPOCHS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("── Agile Sourcing — A100 Full Fine-Tune ──────────────────")

    if not check_gpu():
        return

    if args.dry_run:
        dataset = load_data()
        print("Dry run complete — setup looks good.")
        return

    model, tokenizer = load_model_and_tokenizer()
    dataset          = load_data()
    train(model, tokenizer, dataset, args.epochs)


if __name__ == "__main__":
    main()