"""Analyze saved Agile Sourcing benchmark outputs without running any models.

Usage:
    python analyze_benchmark.py evaluation/results/benchmark_results.json
    python analyze_benchmark.py evaluation/results/benchmark_results_v2.json --output-dir evaluation/results/analysis

This is diagnostic analysis, NOT an automated correctness or citation-verification judge.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

CITATION_RE = re.compile(r"\[\d+\]")
THINK_RE = re.compile(r"</?think>", re.I)
# Heuristics for model self-dialogue outside explicit <think> tags.
# These are review flags, not proof that a response is incorrect.
REASONING_LEAK_RE = re.compile(
    r"\b(?:wait,? the answer|let me (?:check|recheck|verify|think)|"
    r"the answer seems contradictory|let me finalize|"
    r"I should (?:check|reconsider)|the answer is correct\.)",
    re.I,
)
PLACEHOLDER_CITATION_RE = re.compile(
    r"\[\s*(?:cite (?:the )?(?:policy )?(?:excerpt|source|document)|"
    r"insert citation|citation needed)[^\]]*\]",
    re.I,
)
UNCERTAINTY_RE = re.compile(r"\b(?:not found in policy|cannot determine|insufficient (?:information|evidence))\b", re.I)


def analyze(results):
    rows = []
    for i, item in enumerate(results, start=1):
        answer = str(item.get('system_answer', ''))
        ground = str(item.get('ground_truth', ''))
        question = str(item.get('question', ''))
        cited = len(CITATION_RE.findall(answer))
        # Text markers only: these do NOT establish that a cited source supports a claim.
        flags = []
        if not answer.strip():
            flags.append('empty_answer')
        if answer.lstrip().startswith('ERROR:'):
            flags.append('error_response')
        if THINK_RE.search(answer):
            flags.append('thinking_marker_present')
        if REASONING_LEAK_RE.search(answer):
            flags.append('possible_reasoning_leakage')
        placeholders = PLACEHOLDER_CITATION_RE.findall(answer)
        if placeholders:
            flags.append('placeholder_citation_present')
        if len(placeholders) >= 3:
            flags.append('repeated_placeholder_citations')
        if cited == 0:
            flags.append('no_numbered_citation')
        if UNCERTAINTY_RE.search(answer):
            flags.append('uncertainty_or_refusal_phrase')
        if len(answer) > 2000:
            flags.append('long_answer_over_2000_chars')
        rows.append({
            'question_id': i,
            'difficulty': item.get('difficulty', 'unknown'),
            'generator': item.get('generator', 'unknown'),
            'question': question,
            'ground_truth': ground,
            'system_answer': answer,
            'answer_chars': len(answer),
            'numbered_citation_count': cited,
            'flags': ';'.join(flags),
            'manual_grade': '',
            'reviewer_notes': '',
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results_json', type=Path)
    parser.add_argument('--output-dir', type=Path, default=None)
    args = parser.parse_args()
    with args.results_json.open(encoding='utf-8') as f:
        items = json.load(f)
    if not isinstance(items, list):
        parser.error('Expected a JSON array of benchmark result objects.')
    rows = analyze(items)
    out = args.output_dir or args.results_json.parent / 'analysis'
    out.mkdir(parents=True, exist_ok=True)
    stem = args.results_json.stem
    csv_path = out / f'{stem}_review.csv'
    md_path = out / f'{stem}_summary.md'
    # Preserve any manual annotations from a previous run of this same benchmark.
    if csv_path.exists():
        with csv_path.open(newline='', encoding='utf-8-sig') as f:
            old_rows = list(csv.DictReader(f))
        for row in rows:
            i = row['question_id'] - 1
            if i < len(old_rows):
                old = old_rows[i]
                if old.get('question') == row['question'] and old.get('system_answer') == row['system_answer']:
                    row['manual_grade'] = old.get('manual_grade', '')
                    row['reviewer_notes'] = old.get('reviewer_notes', '')
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['question_id'])
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(flag for row in rows for flag in row['flags'].split(';') if flag)
    difficulty = Counter(row['difficulty'] for row in rows)
    total = len(rows)
    with md_path.open('w', encoding='utf-8') as f:
        f.write(f'# Benchmark Diagnostic Summary: {stem}\n\n')
        f.write(f'- Questions analyzed: **{total}**\n')
        f.write('- Type: **heuristic diagnostics only; not accuracy measurement**\n')
        f.write('- Existing manual grades and reviewer notes are preserved when the question and response are unchanged.\n\n')
        f.write('## Questions by difficulty\n\n')
        for k,v in sorted(difficulty.items()):
            f.write(f'- {k}: {v}\n')
        f.write('\n## Flags worth reviewing\n\n')
        for k,v in sorted(counts.items(), key=lambda z:(-z[1],z[0])):
            f.write(f'- {k}: {v}/{total}\n')
        if not counts:
            f.write('- None detected\n')
        f.write('\n## Review notes\n\n')
        f.write('A numbered citation marker does not prove a correct citation. Lack of a numbered marker does not always mean no source is present. Verify correctness, groundedness, and policy currency manually or using a separately validated evaluator.\n')
        f.write('Reasoning-leakage and placeholder-citation flags are pattern-based and require manual review.\n')
        f.write('Fill `manual_grade` (correct / partial / incorrect) and `reviewer_notes` in the CSV after checking examples.\n')
    print(f'Analyzed {total} questions')
    print(f'CSV: {csv_path}')
    print(f'Markdown: {md_path}')
    print('Flag counts:', dict(counts))


if __name__ == '__main__':
    main()
