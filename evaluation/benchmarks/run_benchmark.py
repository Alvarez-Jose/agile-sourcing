import json
import sys
import os

sys.path.insert(0, 'C:/side-stepped')
os.chdir('C:/side-stepped')

from main import ask, get_collection

results = json.load(open('evaluation/benchmarks/benchmark_questions_multi.json'))
questions = results['questions']

print(f'Running {len(questions)} questions with hybrid search...')
collection = get_collection()

answers = []
for i, q in enumerate(questions):
    try:
        answer = ask(q['question'], collection)
    except Exception as e:
        answer = f'ERROR: {e}'
    
    answers.append({
        'question':     q['question'],
        'ground_truth': q['answer'],
        'system_answer': answer,
        'difficulty':   q['difficulty'],
        'generator':    q.get('generator', '')
    })
    print(f'[{i+1}/{len(questions)}] done')

with open('evaluation/benchmarks/benchmark_results_hybrid.json', 'w') as f:
    json.dump(answers, f, indent=2)

print('Done. Saved to benchmark_results_hybrid.json')