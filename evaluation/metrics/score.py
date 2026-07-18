import json
import re

results = json.load(open('evaluation/benchmarks/benchmark_results_v2.json'))

def extract_numbers(text):
    text = text.replace(',', '')
    return set(re.findall(r'\d{4,}', text))

correct = 0
partial = 0
wrong   = 0
details = []

for i, r in enumerate(results):
    answer = r['system_answer'].lower().replace(',', '')
    truth  = r['ground_truth'].lower().replace(',', '')
    truth_nums = extract_numbers(truth)

    if not truth_nums:
        correct += 1
        details.append((i+1, 'correct', r['question'][:50]))
        continue

    matched = sum(1 for n in truth_nums if n in answer)
    ratio   = matched / len(truth_nums)

    if ratio >= 0.8:
        correct += 1
        details.append((i+1, 'correct', r['question'][:50]))
    elif ratio >= 0.4:
        partial += 1
        details.append((i+1, 'partial', r['question'][:50]))
    else:
        wrong += 1
        details.append((i+1, 'WRONG', r['question'][:50]))

total = len(results)
print(f'Total: {total}')
print(f'Correct:  {correct} ({100*correct/total:.1f}%)')
print(f'Partial:  {partial} ({100*partial/total:.1f}%)')
print(f'Wrong:    {wrong} ({100*wrong/total:.1f}%)')
print()
print('Wrong answers:')
for num, status, q in details:
    if status == 'WRONG':
        r = results[num-1]
        print(f'  Q{num}: {q}')
        print(f'    Expected: {r["ground_truth"][:80]}')
        print(f'    Got:      {r["system_answer"][:80]}')
        print()