# evaluation/metrics/score.py
# scores benchmark results two ways:
#
#   numeric - the old way. checks if the 4+ digit numbers in the ground truth show up
#             in the answer. problem: any question with no numbers in the ground truth
#             just counts as correct automatically (~40 of the 60), and it marks good
#             answers wrong over wording (Q40 failed just because "5402" wasn't in it)
#   judge   - LLM-as-judge with local qwen3 through ollama, grades CORRECT / PARTIAL /
#             INCORRECT against the ground truth. this is the number to actually look at
#
#   python evaluation/metrics/score.py evaluation/results/a.json [b.json ...]
#   python evaluation/metrics/score.py evaluation/results/a.json --judge
#   python evaluation/metrics/score.py a.json --judge --show-wrong

import argparse
import json
import re
import sys
from pathlib import Path

JUDGE_MODEL = "qwen3:8b"
JUDGE_PROMPT = """/no_think
You are grading answers from a UC procurement policy assistant against a reference answer.

QUESTION:
{question}

REFERENCE ANSWER:
{truth}

SYSTEM ANSWER:
{answer}

Grade the SYSTEM ANSWER on substance, not wording:
- CORRECT: reaches the same conclusion as the reference (same yes/no, same key numbers,
  same required action or prohibition) and does not contradict it on the key point.
  Extra correct detail is fine.
- PARTIAL: gets the main conclusion but misses or garbles a key detail the reference
  treats as essential, or hedges without committing.
- INCORRECT: reaches a different conclusion, states a wrong key number, or does not answer.

Reply with exactly one word: CORRECT, PARTIAL, or INCORRECT."""


def extract_numbers(text):
    return set(re.findall(r'\d{4,}', text.replace(',', '')))


def score_numeric(r):
    truth_nums = extract_numbers(r['ground_truth'].lower())
    if not truth_nums:
        return 'correct'
    answer = r['system_answer'].lower().replace(',', '')
    ratio = sum(1 for n in truth_nums if n in answer) / len(truth_nums)
    return 'correct' if ratio >= 0.8 else 'partial' if ratio >= 0.4 else 'wrong'


def score_judge(r, model=JUDGE_MODEL):
    import ollama
    answer = re.sub(r"<think>.*?</think>", "", r['system_answer'], flags=re.DOTALL).strip()
    prompt = JUDGE_PROMPT.format(question=r['question'], truth=r['ground_truth'], answer=answer[:6000])
    resp = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}],
                       options={"temperature": 0})
    raw = re.sub(r"<think>.*?</think>", "", resp["message"]["content"], flags=re.DOTALL).upper()
    for label, out in (("INCORRECT", "wrong"), ("PARTIAL", "partial"), ("CORRECT", "correct")):
        if label in raw:
            return out
    return 'wrong'


def summarize(name, statuses):
    n = len(statuses)
    c, p, w = (statuses.count(s) for s in ('correct', 'partial', 'wrong'))
    wrong = [i + 1 for i, s in enumerate(statuses) if s == 'wrong']
    partial = [i + 1 for i, s in enumerate(statuses) if s == 'partial']
    print(f"  {name:8s} correct {c}/{n} ({100 * c / n:.1f}%)  partial {p}  wrong {w}  "
          f"wrong={wrong}  partial={partial}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+')
    parser.add_argument('--judge', action='store_true', help='also score with LLM-as-judge (slow)')
    parser.add_argument('--show-wrong', action='store_true')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    for path in args.files:
        results = json.load(open(path, encoding='utf-8'))
        print(Path(path).name)
        numeric = [score_numeric(r) for r in results]
        summarize('numeric', numeric)
        judged = None
        if args.judge:
            judged = []
            for i, r in enumerate(results, 1):
                judged.append(score_judge(r))
                done = int(30 * i / len(results))
                print(f"\r  judging [{'#' * done}{'.' * (30 - done)}] {i}/{len(results)}", end="", flush=True)
            print()
            summarize('judge', judged)
            cache = Path(path).with_suffix('.judge.json')
            json.dump(judged, open(cache, 'w'), indent=1)
        if args.show_wrong:
            statuses = judged or numeric
            for i, (r, s) in enumerate(zip(results, statuses)):
                if s != 'correct':
                    print(f"    Q{i + 1} [{s}] {r['question'][:90]}")
                    print(f"      Expected: {r['ground_truth'][:140]}")
                    print(f"      Got:      {r['system_answer'][:140].replace(chr(10), ' ')}")


if __name__ == '__main__':
    main()
