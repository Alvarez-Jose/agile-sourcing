# swap the ground_truth in a results file for the corrected answer key, matched by question text,
# so a run made with the original benchmark_questions_multi.json can be judged against the
# corrected key without re-running the pipeline
#
#   python evaluation/benchmarks/make_corrected.py evaluation/results/exp.json
#   -> writes evaluation/results/exp_corrected.json
#   then: python evaluation/metrics/score.py evaluation/results/exp_corrected.json --judge

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('results')
parser.add_argument('--key', default='evaluation/results/benchmark_questions_corrected.json')
parser.add_argument('--out', default=None, help='default: <results>_corrected.json')
args = parser.parse_args()

out = Path(args.out) if args.out else Path(args.results).with_name(Path(args.results).stem + '_corrected.json')
results = json.load(open(args.results, encoding='utf-8'))
by_question = {q['question']: q['answer'] for q in json.load(open(args.key, encoding='utf-8'))['questions']}

swapped = 0
for r in results:
    new = by_question.get(r['question'])
    if new is None:
        print(f"WARNING: no corrected answer for: {r['question'][:80]}")
        continue
    swapped += new != r['ground_truth']
    r['ground_truth'] = new

json.dump(results, open(out, 'w', encoding='utf-8'), indent=2)
print(f'wrote {out}; {swapped} ground truths differ from the original key')
