"""
evaluation/benchmarks/generate_benchmark_multi.py

Generates UC procurement benchmark questions from 3 independent LLMs:
- Claude (Anthropic)
- GPT-4o (OpenAI)
- DeepSeek (DeepSeek API)

Each model generates questions from different policy areas so there's
no overlap and no single model bias.

Usage:
    python generate_benchmark_multi.py
"""

import json
import re
import os

# ── Policy facts split across 3 models ───────────────────────────────────────
# Each model gets different facts to eliminate overlap bias

CLAUDE_FACTS = [
    "BFB-BUS-43: competitive bidding required for purchases over $100,000 annually",
    "Small business set-aside exception up to $250,000 with two price quotes",
    "SSPR form required for federal purchases over $50,000",
    "Split-order purchasing to avoid bidding thresholds is explicitly prohibited",
    "Federal funds over $10,000 means entire transaction follows federal rules",
]

GPT4_FACTS = [
    "Independent contractor vs employee determination follows IRS common law test",
    "BAA required when vendor handles UC protected health information",
    "Data Security Appendix required when vendor accesses UC institutional data",
    "Post-employment COI restriction: one year ban on UC contracts for former employees",
    "Competitive bidding exceptions must be documented with justification",
]

DEEPSEEK_FACTS = [
    "UC equipment valued over $5,000 must be tagged and tracked in asset management system",
    "Tax-free alcohol permits require DEA registration and annual inventory reconciliation",
    "Risk transfer requirements: vendors must carry general liability insurance minimum $1M per occurrence",
    "Regents Policy 5402 prohibits contracting out work that displaces UC employees",
    "Conflict of interest disclosure required before participating in any procurement decision involving a financial interest",
]

PROMPT_TEMPLATE = """You are creating benchmark test questions for a UC procurement AI compliance system.

Based on this UC policy fact: {fact}

Generate 3 realistic questions a UC faculty or staff member would actually ask.
Make them progressively harder:
1. Simple direct question about the policy rule
2. Scenario-based question with specific dollar amounts and context
3. Edge case or exception that tests the boundaries of the rule

Also provide the verified correct answer for each, grounded strictly in the policy fact.

Respond in JSON array only, no markdown fences, no extra text:
[
  {{"question": "...", "answer": "...", "difficulty": "simple"}},
  {{"question": "...", "answer": "...", "difficulty": "scenario"}},
  {{"question": "...", "answer": "...", "difficulty": "edge_case"}}
]"""


# ── Claude ────────────────────────────────────────────────────────────────────
def generate_claude(facts, api_key):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    questions = []

    for i, fact in enumerate(facts):
        print(f"  [Claude] Fact {i+1}/{len(facts)}: {fact[:55]}...")
        try:
            r = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1500,
                messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(fact=fact)}]
            )
            raw   = r.content[0].text.strip()
            raw   = re.sub(r'```json|```', '', raw).strip()
            pairs = json.loads(raw)
            for p in pairs:
                p["source_fact"] = fact
                p["generator"]   = "claude-opus-4"
            questions.extend(pairs)
            print(f"    ✓ {len(pairs)} questions")
        except Exception as e:
            print(f"    ✗ ERROR: {e}")

    return questions


# ── GPT-4o ────────────────────────────────────────────────────────────────────
def generate_gpt4(facts, api_key):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    questions = []

    for i, fact in enumerate(facts):
        print(f"  [GPT-4o] Fact {i+1}/{len(facts)}: {fact[:55]}...")
        try:
            r = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1500,
                messages=[
                    {"role": "system", "content": "You are a UC procurement policy expert creating benchmark test questions."},
                    {"role": "user",   "content": PROMPT_TEMPLATE.format(fact=fact)}
                ]
            )
            raw   = r.choices[0].message.content.strip()
            raw   = re.sub(r'```json|```', '', raw).strip()
            pairs = json.loads(raw)
            for p in pairs:
                p["source_fact"] = fact
                p["generator"]   = "gpt-4o"
            questions.extend(pairs)
            print(f"    ✓ {len(pairs)} questions")
        except Exception as e:
            print(f"    ✗ ERROR: {e}")

    return questions


# ── DeepSeek ──────────────────────────────────────────────────────────────────
def generate_deepseek(facts, api_key):
    from openai import OpenAI
    # DeepSeek uses OpenAI-compatible API
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    questions = []

    for i, fact in enumerate(facts):
        print(f"  [DeepSeek] Fact {i+1}/{len(facts)}: {fact[:55]}...")
        try:
            r = client.chat.completions.create(
                model="deepseek-chat",
                max_tokens=1500,
                messages=[
                    {"role": "system", "content": "You are a UC procurement policy expert creating benchmark test questions."},
                    {"role": "user",   "content": PROMPT_TEMPLATE.format(fact=fact)}
                ]
            )
            raw   = r.choices[0].message.content.strip()
            raw   = re.sub(r'```json|```', '', raw).strip()
            pairs = json.loads(raw)
            for p in pairs:
                p["source_fact"] = fact
                p["generator"]   = "deepseek-chat"
            questions.extend(pairs)
            print(f"    ✓ {len(pairs)} questions")
        except Exception as e:
            print(f"    ✗ ERROR: {e}")

    return questions


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Load API keys from environment variables (safer than hardcoding)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key    = os.getenv("OPENAI_API_KEY", "")
    deepseek_key  = os.getenv("DEEPSEEK_API_KEY", "")

    all_questions = []

    # ── Claude
    if anthropic_key:
        print("\n── Generating with Claude ────────────────────────────")
        questions = generate_claude(CLAUDE_FACTS, anthropic_key)
        all_questions.extend(questions)
        print(f"Claude total: {len(questions)} questions")
    else:
        print("ANTHROPIC_API_KEY not set — skipping Claude")

    # ── GPT-4o
    if openai_key:
        print("\n── Generating with GPT-4o ────────────────────────────")
        questions = generate_gpt4(GPT4_FACTS, openai_key)
        all_questions.extend(questions)
        print(f"GPT-4o total: {len(questions)} questions")
    else:
        print("OPENAI_API_KEY not set — skipping GPT-4o")

    # ── DeepSeek
    if deepseek_key:
        print("\n── Generating with DeepSeek ──────────────────────────")
        questions = generate_deepseek(DEEPSEEK_FACTS, deepseek_key)
        all_questions.extend(questions)
        print(f"DeepSeek total: {len(questions)} questions")
    else:
        print("DEEPSEEK_API_KEY not set — skipping DeepSeek")

    # ── Save combined benchmark
    output = {
        "metadata": {
            "total_questions":  len(all_questions),
            "generators":       ["claude-opus-4", "gpt-4o", "deepseek-chat"],
            "policy_areas":     15,
            "difficulty_split": {
                "simple":    len([q for q in all_questions if q.get("difficulty") == "simple"]),
                "scenario":  len([q for q in all_questions if q.get("difficulty") == "scenario"]),
                "edge_case": len([q for q in all_questions if q.get("difficulty") == "edge_case"]),
            }
        },
        "questions": all_questions
    }

    with open("benchmark_questions_multi.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n── Summary ───────────────────────────────────────────")
    print(f"Total questions: {len(all_questions)}")
    print(f"  Simple:     {output['metadata']['difficulty_split']['simple']}")
    print(f"  Scenario:   {output['metadata']['difficulty_split']['scenario']}")
    print(f"  Edge cases: {output['metadata']['difficulty_split']['edge_case']}")
    print(f"\nSaved to benchmark_questions_multi.json")
    print(f"\nNext: python run_benchmark.py")


if __name__ == "__main__":
    main()