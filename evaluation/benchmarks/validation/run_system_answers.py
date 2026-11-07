# evaluation/benchmarks/validation/run_system_answers.py
# runs the pipeline on the review questions (facts + question presented, as a department would
# put them) and saves its answers separately from the workbook sent to Procurement, so the
# reviewers never see the system's drafts and the answers can be scored once responses return.
#
#   python evaluation/benchmarks/validation/run_system_answers.py
#   -> system_answers_<date>.json next to this file

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.rag.pipeline import LLM_MODEL, ask

HERE = Path(__file__).resolve().parent
qs = json.load(open(HERE / "review_questions.json", encoding="utf-8"))["questions"]
out = []
for q in qs:
    text = f"{q['facts']} {q['question']}"
    t0 = time.time()
    r = ask(text)
    out.append({"no": q["no"], "subject": q["subject"], "input": text, "answer": r["answer"],
                "refused": r.get("refused"), "intent": r.get("intent"),
                "rule_engine": r.get("determination") is not None,
                "cited": [f"{s['policy']} p.{s['page']}" for s in r.get("citations", [])],
                "latency_s": round(time.time() - t0, 1)})
    print(f"Q{q['no']:2d} {q['subject'][:45]:45s} {'refused' if r.get('refused') else 'answered':8s} "
          f"rule={'Y' if r.get('determination') else 'n'} {out[-1]['latency_s']}s")
path = HERE / f"system_answers_{date.today().isoformat()}.json"
json.dump({"model": LLM_MODEL, "run": date.today().isoformat(), "answers": out},
          open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("wrote", path)
