# runs the 60 question benchmark through the backend pipeline
#
#   python evaluation/benchmarks/run_benchmark.py --out evaluation/results/full.json
#   python evaluation/benchmarks/run_benchmark.py --no-rules --no-rerank     # ablation
# then score it: python evaluation/metrics/score.py evaluation/results/full.json --judge

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import ollama

from backend.rag.pipeline import ask

parser = argparse.ArgumentParser()
parser.add_argument('--out', default='evaluation/results/benchmark_results_full.json')
parser.add_argument('--no-rules', action='store_true', help='turn off the rule engine')
parser.add_argument('--no-rerank', action='store_true', help='turn off the cross-encoder reranker')
args = parser.parse_args()

# if ollama isn't running every answer comes back as an error, so just stop
try:
    ollama.list()
except Exception as e:
    sys.exit(f'Ollama is not reachable ({e}). Start it with `ollama serve` and rerun.')

questions = json.load(open('evaluation/results/benchmark_questions_multi.json', encoding='utf-8'))['questions']
print(f'Running {len(questions)} questions (rules={not args.no_rules}, rerank={not args.no_rerank})...')

answers = []
start = time.time()
for i, q in enumerate(questions):
    try:
        answer = ask(q['question'], use_rules=not args.no_rules, use_reranker=not args.no_rerank)['answer']
    except Exception as e:
        answer = f'ERROR: {e}'

    answers.append({
        'question':      q['question'],
        'ground_truth':  q['answer'],
        'system_answer': answer,
        'difficulty':    q['difficulty'],
        'generator':     q.get('generator', '')
    })
    elapsed = time.time() - start
    eta = elapsed / (i + 1) * (len(questions) - i - 1)
    done = int(30 * (i + 1) / len(questions))
    print(f"\r[{'#' * done}{'.' * (30 - done)}] {i+1}/{len(questions)}  "
          f"elapsed {elapsed / 60:.1f}m  eta {eta / 60:.1f}m", end='', flush=True)
print()

os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
with open(args.out, 'w', encoding='utf-8') as f:
    json.dump(answers, f, indent=2)

print(f'Done. Saved to {args.out}')
