# evaluation/benchmarks/run_chat_conversations.py
# Replay synthetic carts through the real local model/API; python -m evaluation.benchmarks.run_chat_conversations.
import argparse
import json
import os
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from evaluation.progress import Progress

ROOT = Path(__file__).resolve().parents[2]


def check_response(response, expected):
    context = response.get('chat_context') or {}
    suppliers = context.get('suppliers') or [{}]
    observed = {**suppliers[0], 'awaiting': context.get('awaiting_kind'),
                'independent_purchases': context.get('independent_purchases'),
                'intent': response.get('intent')}
    checks = []
    for key, value in expected.items():
        actual = response.get('answer', '') if key == 'answer_contains' else observed.get(key)
        passed = value in actual if key == 'answer_contains' else actual == value
        if key in ('tax', 'shipping', 'handling') and actual is not None:
            passed = Decimal(actual) == Decimal(value)
        checks.append({'field': key, 'expected': value, 'actual': actual, 'passed': passed})
    return checks


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def replay(client, dataset, output, limit=60):
    report = {'synthetic_data': True, 'authentication': 'local dependency override; not an auth test',
              'metric': 'scripted state/routing assertions, not policy accuracy', 'conversations': []}
    scenarios = dataset['scenarios'][:limit]
    total = sum(len(s['turns']) for s in scenarios)
    completed = 0
    with Progress('Chat replay', total) as progress:
        for scenario in scenarios:
            context = {'cart': dataset['cart']}
            history = []
            conversation = {'id': scenario['id'], 'turns': []}
            report['conversations'].append(conversation)
            for turn in scenario['turns']:
                started = time.monotonic()
                entry = {'question': turn['question'], 'context_before': context}
                try:
                    response = client.post('/api/ask', json={'question': turn['question'],
                        'chat_context': context, 'history': history[-8:]})
                    response.raise_for_status()
                    body = response.json()
                    if body.get('tool_request'):
                        raise RuntimeError('Unexpected scrape request; fixture cart is already attached')
                    entry.update(response=body, checks=check_response(body, turn.get('expect', {})))
                    context = body.get('chat_context') or context
                    history += [{'role': 'user', 'content': turn['question'][:4000]},
                                {'role': 'assistant', 'content': (body.get('original_answer') or body['answer'])[:4000]}]
                except Exception as error:
                    entry['error'] = str(error)
                entry['elapsed_seconds'] = round(time.monotonic() - started, 2)
                conversation['turns'].append(entry)
                save(output / 'conversations.json', report)
                completed += 1
                progress.update(completed)
    turns = [t for c in report['conversations'] for t in c['turns']]
    checks = [check for t in turns for check in t.get('checks', [])]
    plans = [t['response'].get('dialogue') for t in turns if 'response' in t]
    summary = {'turns': len(turns), 'errors': sum('error' in t for t in turns),
               'assertions_passed': sum(c['passed'] for c in checks), 'assertions_total': len(checks),
               'interpreter_accepted': sum(bool(p and p.get('accepted')) for p in plans),
               'interpreter_fallbacks': sum(bool(p and not p.get('accepted')) for p in plans)}
    save(output / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=60, help='Maximum conversations')
    parser.add_argument('--scenario', help='Replay only this scenario ID from the dataset')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error('--limit must be positive')
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'secret/.env')
    os.environ['CHAT_MODEL_CONVERSATION'] = '1'
    os.environ['RAG_WARM_UP'] = '0'
    import ollama
    model = os.environ.get('LLM_MODEL', 'qwen3:8b')
    model_info = ollama.Client(timeout=15).show(model)
    from backend.api.cart_routes import reviewed_sources
    reviewed_sources()  # Fail early if the pinned sources are missing/changed.
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.auth.dependencies import require_approved_user
    from backend.auth.models import UserProfile
    output = args.output_dir or ROOT / 'data/evaluation' / ('chat_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'metadata.json', {'model': model, 'model_details': model_info.model_dump(mode='json').get('details'),
                                   'temperature': 0, 'synthetic_cart': True})
    dataset = json.loads((ROOT / 'evaluation/scenarios/chat_conversations.json').read_text())
    if args.scenario:
        dataset['scenarios'] = [s for s in dataset['scenarios'] if s['id'] == args.scenario]
        if not dataset['scenarios']:
            parser.error('Unknown scenario ID')
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[require_approved_user] = lambda: UserProfile(uid='synthetic-replay', email='demo@example.invalid', is_approved=True)
    try:
        with TestClient(app) as client:
            summary = replay(client, dataset, output, args.limit)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    print(f"Chat report: {summary['assertions_passed']}/{summary['assertions_total']} state/routing assertions; "
          f"{summary['errors']} errors; {summary['interpreter_fallbacks']} model interpretation fallbacks.\nResults: {output}")
    return int(bool(summary['errors'] or summary['interpreter_fallbacks'] or summary['assertions_passed'] != summary['assertions_total']))


if __name__ == '__main__':
    raise SystemExit(main())
