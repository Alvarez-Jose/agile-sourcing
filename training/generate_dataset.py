"""
training/generate_dataset.py

Generates UC policy Q&A training pairs from existing ChromaDB chunks
using local Qwen3. Outputs train.jsonl and eval.jsonl for fine-tuning.

Usage:
    python training/generate_dataset.py
    python training/generate_dataset.py --max 200
    python training/generate_dataset.py --review
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so rules/ can be imported

import chromadb
import ollama

CHROMA_DIR = "data/embeddings/chroma_store"
COLLECTION_NAME = "uc_policies"
OUTPUT_DIR = Path("training/dataset")
TRAIN_FILE = OUTPUT_DIR / "train.jsonl"
EVAL_FILE = OUTPUT_DIR / "eval.jsonl"
EDGE_CASE_FILE = OUTPUT_DIR / "edge_cases.jsonl"
LLM_MODEL = "qwen3:8b"
EVAL_SPLIT = 0.15
MAX_PAIRS = 500
SYSTEM_PROMPT = (
    "You are a UC procurement policy expert. Answer questions strictly based "
    "on UC and UCSC policy documents. Always cite the policy source. "
    "If the answer is not in the policy, say so clearly."
)

# question templates to get diversity in the generated pairs
QUESTION_TEMPLATES = [
    "What is the requirement for {topic}?",
    "When is {topic} required?",
    "What are the dollar thresholds for {topic}?",
    "What forms are needed for {topic}?",
    "What happens if {topic} is not followed?",
    "How does federal funding affect {topic}?",
    "What exceptions exist for {topic}?",
    "What is the process for {topic}?",
    "Who is responsible for {topic}?",
    "What documentation is required for {topic}?",
]

# edge cases and high-stakes scenarios that have to be in the dataset
# these are the ones that determine whether the model actually understands policy
MUST_INCLUDE_SCENARIOS = [
    {
        "question": "I need to purchase a $75,000 microscope using an NIH federal grant. What procurement process do I follow?",
        "doc_type": "Procurement"
    },
    {
        "question": "Can I split a $120,000 purchase into two $60,000 orders to avoid competitive bidding?",
        "doc_type": "Procurement"
    },
    {
        "question": "What is the competitive bidding threshold for UC purchases?",
        "doc_type": "Procurement"
    },
    {
        "question": "When do I need to complete an SSPR form?",
        "doc_type": "Procurement"
    },
    {
        "question": "I want to hire an independent contractor for $15,000. What do I need to do?",
        "doc_type": "Contracting"
    },
    {
        "question": "What insurance requirements apply when contracting for services?",
        "doc_type": "Risk & Insurance"
    },
    {
        "question": "When does a Business Associate Agreement need to be signed?",
        "doc_type": "GDPR & Privacy"
    },
    {
        "question": "What are the small business set-aside thresholds for UC procurement?",
        "doc_type": "Procurement"
    },
    {
        "question": "I have a conflict of interest with a vendor. What must I disclose?",
        "doc_type": "Conflict of Interest"
    },
    {
        "question": "What happens to university equipment when a grant ends?",
        "doc_type": "Property & Equipment"
    },
    {
        "question": "Can I use federal grant funds to buy alcohol for a faculty event?",
        "doc_type": "Finance"
    },
    {
        "question": "What is the simplified acquisition threshold for federal purchases?",
        "doc_type": "Procurement"
    },
    {
        "question": "When is a Data Security Appendix required in a vendor contract?",
        "doc_type": "GDPR & Privacy"
    },
    {
        "question": "What are the post-employment conflict of interest restrictions for UC employees?",
        "doc_type": "Conflict of Interest"
    },
    {
        "question": "What is the threshold that requires a formal source selection process?",
        "doc_type": "Procurement"
    },
]


# edge cases the model kept getting wrong (benchmark Q7, Q9, Q32, Q41).
# I wrote these answers from the policy docs instead of having qwen generate them,
# since qwen generating them is how we got the wrong answers in the first place.
# each one also gets run through the rule engine (the `request` part) and has to
# match `expect`, so the training data can't disagree with the rules.
EDGE_CASE_SCENARIOS = [
    # equipment tagging around $5,000 (BUS-29)
    {"question": "Our lab bought a spectrometer for exactly $5,000. Does it need to be tagged?",
     "answer": "Yes. Under BFB-BUS-29, equipment costing $5,000 or more is inventorial: it must be tagged, tracked, "
               "and assigned a Capital Asset Account Number (CAAN). At exactly $5,000 the spectrometer meets the threshold.",
     "request": {"items": [("spectrometer", 5_000)]}, "expect": {"tagged": [True]}},
    {"question": "One pump cost $4,999 and another cost $5,001. Which one goes into the equipment inventory?",
     "answer": "Only the $5,001 pump. BFB-BUS-29 requires equipment costing $5,000 or more to be inventoried, tagged, "
               "and assigned a CAAN. The $4,999 pump is below the threshold and is not inventorial equipment.",
     "request": {"items": [("pump A", 4_999), ("pump B", 5_001)]}, "expect": {"tagged": [False, True]}},
    {"question": "I bought a $4,800 centrifuge and a $5,200 microscope. Which need tagging?",
     "answer": "Only the microscope ($5,200) must be tagged and tracked per BFB-BUS-29, because it meets the $5,000 "
               "inventorial equipment threshold. The centrifuge ($4,800) is below the threshold and does not require tagging.",
     "request": {"items": [("centrifuge", 4_800), ("microscope", 5_200)]}, "expect": {"tagged": [False, True]}},
    {"question": "We purchased a $3,200 laptop, a $12,000 incubator, and a $5,000 freezer. What has to be tagged?",
     "answer": "The incubator ($12,000) and the freezer ($5,000) must be inventoried, tagged, and assigned a CAAN under "
               "BFB-BUS-29 because each costs $5,000 or more. The $3,200 laptop is below the threshold and is not tagged "
               "as inventorial equipment.",
     "request": {"items": [("laptop", 3_200), ("incubator", 12_000), ("freezer", 5_000)]},
     "expect": {"tagged": [False, True, True]}},
    {"question": "A year after buying a microscope we added a $6,500 camera attachment. Does the accessory get capitalized?",
     "answer": "Yes. Under BFB-BUS-29, accessories costing $5,000 or more that are acquired after the initial purchase "
               "must also be capitalized and added to the equipment record.",
     "request": {"items": [("camera attachment", 6_500, False, True)]}, "expect": {"tagged": [True]}},
    # federal grant SSPR at $50K
    {"question": "My NSF grant is paying exactly $50,000 for an instrument. Do I need an SSPR?",
     "answer": "Yes. The SSPR form is required for federal grant/cooperative agreement purchases of $50,000 or more, "
               "so an exactly $50,000 grant-funded purchase requires it. (Competitive bidding is not required below $100,000.)",
     "request": {"amount": 50_000, "funding": "federal_grant"}, "expect": {"sspr": True, "bid": False}},
    {"question": "Is an SSPR required for a $49,500 purchase on an NIH grant?",
     "answer": "No. For federal grant/cooperative agreement funds the SSPR threshold is $50,000, so a $49,500 purchase "
               "does not require the SSPR. Federal contract funds have a lower $15,000 SSPR threshold.",
     "request": {"amount": 49_500, "funding": "federal_grant"}, "expect": {"sspr": False}},
    # federal contract SSPR at $15K
    {"question": "We're buying $15,000 of supplies on a federal DOE contract. Is an SSPR form needed?",
     "answer": "Yes. For federal contract funds the SSPR form is required for purchases of $15,000 or more (including "
               "tax and shipping). At $15,000 the SSPR is required; for a purchase under $100,000 you document three "
               "competitive quotes in Section II per 2 CFR 200.320(a)(2)(i).",
     "request": {"amount": 15_000, "funding": "federal_contract"}, "expect": {"sspr": True, "bid": False}},
    {"question": "What are the SSPR thresholds for federal contracts, federal grants, and non-federal purchases?",
     "answer": "The SSPR form is required for federal contract purchases of $15,000 or more, federal grant/cooperative "
               "agreement purchases of $50,000 or more, and non-federal purchases of $100,000 or more.",
     "request": None, "expect": {}},
    # mixed funding right at $10K
    {"question": "A $60,000 purchase is paid with exactly $10,000 of federal funds and $50,000 of state funds. Which rules apply?",
     "answer": "Only UC/State rules apply. Under the SSPR FAQ, federal requirements govern the whole transaction only "
               "when the federal portion exceeds $10,000. A federal portion of exactly $10,000 does not exceed it.",
     "request": {"amount": 60_000, "funding": "federal_grant", "federal_amount": 10_000}, "expect": {"federal": False}},
    {"question": "A $60,000 purchase uses $10,500 from an NIH grant and the rest from department funds. Do federal rules apply?",
     "answer": "Yes, to the entire $60,000 transaction. Because the federal portion ($10,500) exceeds $10,000, federal "
               "requirements apply to the whole purchase, not only the federal share. At $60,000 on grant funds the SSPR "
               "is required ($50,000 threshold).",
     "request": {"amount": 60_000, "funding": "federal_grant", "federal_amount": 10_500},
     "expect": {"federal": True, "sspr": True}},
    # every covered service type
    *[{"question": f"Can our department contract out {svc} services to an outside company?",
       "answer": f"Generally no. {svc.capitalize()} is a covered service under Regents Policy 5402 and AFSCME 3299 "
                 "Article 5, which generally prohibit contracting out services that UC employees can perform. It is "
                 "permitted only under limited exceptions: emergency; insufficient UC staff; specialized expertise not "
                 "available internally; services incidental to a property lease; an urgent, temporary, or occasional "
                 "need; a remote facility more than 10 miles from campus; registry personnel in clinical operations; or "
                 "when required by law, federal requirement, or court order. It must not displace UC employees. "
                 "Contracts over $100,000 require advance notice to AFSCME 3299, and contracts over $100,000 lasting "
                 "more than 90 days require wage and benefit parity.",
       "request": {"amount": 1, "description": f"{svc} services"}, "expect": {"covered": True}}
      for svc in ["janitorial", "custodial", "food service", "laundry", "grounds keeping", "parking", "security guard",
                  "housekeeping"]],
    {"question": "Our department wants to contract out a $50,000 janitorial service contract for a new building, and it "
                 "would eliminate the jobs of three UC janitorial staff. Is it allowed?",
     "answer": "No. Janitorial work is a covered service under Regents Policy 5402, and a contract that displaces UC "
               "employees (demotion, layoff, or involuntary reduction in time) is prohibited regardless of the contract "
               "value. At $50,000 AFSCME advance notice would not be triggered, but the displacement alone makes the "
               "contract impermissible.",
     "request": {"amount": 50_000, "description": "janitorial services", "displaces_uc_employees": True},
     "expect": {"prohibited": True, "afscme": False}},
    {"question": "We plan a $150,000, one-year custodial contract. What union requirements apply?",
     "answer": "Custodial work is a covered service. Because the contract exceeds $100,000, AFSCME 3299 must be notified "
               "before entering, extending, or renewing it: 30 calendar days' notice, or a copy of the RFP at issuance, "
               "and AFSCME has 14 calendar days to respond. Because it also runs longer than 90 days, the contractor must "
               "pay wages and benefits equivalent to UC employees doing the same work. A Regents Policy 5402 exception "
               "must also apply, and the contract may not displace UC employees.",
     "request": {"amount": 150_000, "description": "custodial services"}, "expect": {"afscme": True, "parity": True}},
    {"question": "Is an $80,000 security guard contract subject to AFSCME notice?",
     "answer": "No. Security services are a covered service under Regents Policy 5402, so an exception must still "
               "apply, but AFSCME 3299 advance notice is only required for covered-service contracts over $100,000.",
     "request": {"amount": 80_000, "description": "security guard services"}, "expect": {"afscme": False}},
    {"question": "Is a $200,000 IT consulting engagement a covered service under Regents Policy 5402?",
     "answer": "No. IT consulting is not among the covered services (cleaning, custodial, janitorial, housekeeping, food "
               "service, laundry, grounds keeping, building maintenance excluding skilled crafts, transportation, parking, "
               "security, nursing assistant, medical imaging, medical technician). The $200,000 value does trigger "
               "competitive bidding and the SSPR under BUS-43.",
     "request": {"amount": 200_000, "description": "IT consulting"}, "expect": {"covered": False, "bid": True}},
    # contracting out exceptions
    *[{"question": f"Can we contract out grounds keeping services when {why}?",
       "answer": f"Possibly. Grounds keeping is a covered service under Regents Policy 5402, but contracting out is "
                 f"permitted under the '{label}' exception. The exception must be documented, the contract must not "
                 "displace UC employees, and contracts over $100,000 still require AFSCME 3299 notice.",
       "request": {"amount": 1, "description": "grounds keeping services", "contracting_out_exception": code},
       "expect": {"prohibited": False}}
      for code, why, label in [
          ("emergency", "a storm has created an emergency", "emergency"),
          ("specialized_expertise", "the work needs specialized equipment no UC crew has",
           "specialized expertise not available internally"),
          ("remote_facility", "the site is a field station 40 miles from campus", "remote facility"),
          ("urgent_temporary", "we only need a one-time cleanup after an event", "urgent, temporary, or occasional need"),
      ]],
    # multi-year contracts
    {"question": "A 5-year service agreement costs $25,000 per year and is paid from a federal grant. Must it be bid?",
     "answer": "Yes. With federal funds, the threshold applies to the anticipated total value: 5 x $25,000 = $125,000, "
               "which exceeds $100,000, so it must be competitively bid and the SSPR used (SSPR FAQ), even though each "
               "year is under $100,000.",
     "request": {"amount": 125_000, "funding": "federal_grant", "contract_years": 5}, "expect": {"bid": True, "sspr": True}},
    {"question": "A 3-year non-federal maintenance contract is $40,000 per year. Is a bid required under BUS-43?",
     "answer": "No. BUS-43 applies the bid threshold to annual expenditures of more than $100,000; at $40,000 per year a "
               "bid is not compelled for non-federal funds, although seeking competition is encouraged. If federal "
               "funds were used, the $120,000 total would require a bid.",
     "request": {"amount": 120_000, "contract_years": 3}, "expect": {"bid": False}},
    # sole source reasons that aren't allowed (pre-work, price, brand)
    {"question": "The vendor helped us customize the equipment specs so only their product qualifies. Can we sole source "
                 "this $150,000 grant-funded purchase?",
     "answer": "No. Per the SSPR form, pre-work with the selected supplier to customize the equipment, thereby excluding "
               "competition, is not an allowable sole source justification. The $150,000 purchase must be competitively bid.",
     "request": {"amount": 150_000, "funding": "federal_grant", "source_selection": "sole_source",
                 "sole_source_justification": "pre_work"}, "expect": {"bid": True, "sole_source_invalid": True}},
    {"question": "Can I sole source a $120,000 purchase because the vendor has the lowest price?",
     "answer": "No. Price is not an allowable sole source justification. Allowable non-federal justifications are "
               "one-of-a-kind/unique or matching existing equipment; otherwise the $120,000 purchase must be bid.",
     "request": {"amount": 120_000, "source_selection": "sole_source", "sole_source_justification": "price"},
     "expect": {"bid": True, "sole_source_invalid": True}},
    {"question": "Our team prefers one brand of software. Can we sole source a $110,000 license on that basis?",
     "answer": "No. Brand names and staff preference or familiarity are not allowable sole source justifications. "
               "Sole source requires that only one supplier can meet the requirement.",
     "request": {"amount": 110_000, "source_selection": "sole_source", "sole_source_justification": "brand"},
     "expect": {"bid": True, "sole_source_invalid": True}},
    {"question": "What SSPR sections do I complete for a $175,000 one-of-a-kind instrument on an NIH grant?",
     "answer": "A valid one-of-a-kind sole source is exempt from competitive bidding, but the SSPR is required. Complete "
               "Sections I, III (price reasonableness), IV (sole source justification), VII (conflict of interest), and "
               "VIII (representation). The purchase also needs the Federal Funds Checklist, Debarment & Suspension and "
               "Anti-Lobbying verifications, and the Uniform Guidance flow-down articles.",
     "request": {"amount": 175_000, "funding": "federal_grant", "source_selection": "sole_source",
                 "sole_source_justification": "one_of_a_kind"},
     "expect": {"bid": False, "sections": ["I", "III", "IV", "VII", "VIII"]}},
]


def _check_edge_case(scenario) -> list:
    # run it through the rule engine, returns a list of mismatches (empty = all good)
    from rules import PurchaseRequest, RuleEngine
    if scenario["request"] is None:
        return []
    r = RuleEngine().evaluate(PurchaseRequest(**scenario["request"]))
    cs = r.categories.covered_service
    actual = {
        "tagged": [e.must_tag for e in r.categories.equipment],
        "sspr": r.sspr_required, "bid": r.competitive_bid_required, "federal": r.federal_rules_apply,
        "covered": cs is not None, "prohibited": bool(cs and cs.prohibited),
        "afscme": bool(cs and cs.afscme_notice_required), "parity": bool(cs and cs.wage_parity_required),
        "sole_source_invalid": r.has_flag("SOLE_SOURCE_INVALID"), "sections": r.sspr_sections,
    }
    return [f"{k}: expected {v}, engine says {actual[k]}" for k, v in scenario["expect"].items() if actual[k] != v]


def build_edge_case_pairs() -> list[dict]:
    pairs = []
    for s in EDGE_CASE_SCENARIOS:
        problems = _check_edge_case(s)
        if problems:
            raise ValueError(f"Edge case label disagrees with rule engine: {s['question']}\n  " + "\n  ".join(problems))
        pairs.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": s["question"]},
                {"role": "assistant", "content": s["answer"]},
            ],
            "metadata": {"source": "edge case (rule-engine verified)", "doc_type": "Procurement", "page": ""},
        })
    return pairs


def load_chunks():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    results = collection.get(include=["documents", "metadatas"])
    chunks = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        if doc and len(doc.strip()) > 100:
            chunks.append({"text": doc, "meta": meta})
    print(f"Loaded {len(chunks)} chunks from ChromaDB")
    return chunks


def generate_qa(chunk: dict, retries: int = 2) -> dict | None:
    source = chunk["meta"].get("policy_name") or chunk["meta"].get("source", "UC Policy")
    text = chunk["text"]

    prompt = f"""/no_think

You are creating training data for a UC procurement AI assistant.

Given the policy excerpt below, generate ONE realistic question that a UC faculty
or staff member might ask about procurement, and a precise answer grounded
strictly in the excerpt.

RULES:
- The question must be something a real person would actually ask
- The answer must come ONLY from the excerpt — no outside knowledge
- The answer must cite the policy name
- If the excerpt does not contain enough information for a good Q&A pair, respond with: SKIP

POLICY SOURCE: {source}

POLICY EXCERPT:
{text}

Respond in valid JSON only, no markdown, no extra text:
{{"question": "...", "answer": "..."}}"""

    for attempt in range(retries + 1):
        try:
            response = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response["message"]["content"].strip()
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            if "SKIP" in raw:
                return None

            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not json_match:
                return None

            pair = json.loads(json_match.group())

            if not pair.get("question") or not pair.get("answer"):
                return None

            if len(pair["answer"]) < 40:
                return None

            return {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": pair["question"]},
                    {"role": "assistant", "content": pair["answer"]}
                ],
                "metadata": {
                    "source": source,
                    "doc_type": chunk["meta"].get("doc_type", ""),
                    "page": chunk["meta"].get("page", "")
                }
            }

        except (json.JSONDecodeError, KeyError):
            if attempt < retries:
                time.sleep(1)
            continue

    return None


def generate_scenario(scenario: dict, collection) -> dict | None:
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    query_vec = embedder.encode([scenario["question"]])[0].tolist()

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=4,
        include=["documents", "metadatas"]
    )
    chunks = results["documents"][0]
    metas = results["metadatas"][0]

    context = ""
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        source = meta.get("policy_name") or meta.get("source", "UC Policy")
        context += f"\n[{i+1}] {source}\n{chunk}\n"

    prompt = f"""/think

You are creating a high-quality training example for a UC procurement AI assistant.

Answer the question below using ONLY the policy excerpts provided.
This is a complex scenario requiring careful multi-policy reasoning.
Be thorough, specific, and cite sources [1], [2], etc.

POLICY EXCERPTS:
{context}

QUESTION: {scenario["question"]}

Respond in valid JSON only:
{{"question": "{scenario["question"]}", "answer": "..."}}"""

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response["message"]["content"].strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return None

        pair = json.loads(json_match.group())

        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": pair["question"]},
                {"role": "assistant", "content": pair["answer"]}
            ],
            "metadata": {
                "source": "multi-policy scenario",
                "doc_type": scenario["doc_type"],
                "page": ""
            }
        }
    except Exception:
        return None


def write_jsonl(pairs: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"Wrote {len(pairs)} pairs to {path}")


def main():
    parser = argparse.ArgumentParser(description="Generate UC policy training dataset")
    parser.add_argument("--max", type=int, default=MAX_PAIRS, help="Max Q&A pairs to generate")
    parser.add_argument("--review", action="store_true", help="Print sample pairs for review")
    parser.add_argument("--edge-cases-only", action="store_true",
                        help=f"Only write the rule-engine-verified edge cases to {EDGE_CASE_FILE}")
    args = parser.parse_args()

    edge_pairs = build_edge_case_pairs()
    if args.edge_cases_only:
        write_jsonl(edge_pairs, EDGE_CASE_FILE)
        print(f"Merge into the fine-tuning set with the train file of your choice, e.g. train_large.jsonl")
        return

    chunks = load_chunks()

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION_NAME)

    all_pairs = list(edge_pairs)

    # step 1: must-include scenarios first so they always make it in
    print(f"\nGenerating {len(MUST_INCLUDE_SCENARIOS)} must-include scenarios...")
    for i, scenario in enumerate(MUST_INCLUDE_SCENARIOS):
        print(f"  Scenario {i+1}/{len(MUST_INCLUDE_SCENARIOS)}: {scenario['question'][:60]}...")
        pair = generate_scenario(scenario, collection)
        if pair:
            all_pairs.append(pair)
            print(f"    generated")
        else:
            print(f"    skipped")

    # step 2: fill rest from chunk-based generation
    remaining = args.max - len(all_pairs)
    print(f"\nGenerating {remaining} Q&A pairs from policy chunks...")

    priority_types = ["Procurement", "Contracting", "Risk & Insurance", "Conflict of Interest"]
    priority_chunks = [c for c in chunks if c["meta"].get("doc_type") in priority_types]
    other_chunks = [c for c in chunks if c["meta"].get("doc_type") not in priority_types]

    # 70/30 split toward priority doc types
    priority_n = int(len(chunks) * 0.7)
    other_n = len(chunks) - priority_n

    sampled = (
        random.sample(priority_chunks, min(priority_n, len(priority_chunks))) +
        random.sample(other_chunks, min(other_n, len(other_chunks)))
    )
    random.shuffle(sampled)

    generated = 0
    skipped = 0

    for chunk in sampled:
        if generated >= remaining:
            break

        doc_type = chunk["meta"].get("doc_type", "General")
        print(f"  [{generated+1}/{remaining}] {doc_type} — {chunk['meta'].get('source','')[:40]}...")

        pair = generate_qa(chunk)
        if pair:
            all_pairs.append(pair)
            generated += 1
        else:
            skipped += 1

        time.sleep(0.2)

    print(f"\nGenerated: {len(all_pairs)} pairs  |  Skipped: {skipped} chunks")

    # step 3: split train/eval
    random.shuffle(all_pairs)
    eval_n = max(1, int(len(all_pairs) * EVAL_SPLIT))
    eval_pairs = all_pairs[:eval_n]
    train_pairs = all_pairs[eval_n:]

    write_jsonl(train_pairs, TRAIN_FILE)
    write_jsonl(eval_pairs, EVAL_FILE)

    if args.review:
        print("\n--- Sample training pairs ---")
        for pair in random.sample(all_pairs, min(3, len(all_pairs))):
            print(f"\nQ: {pair['messages'][1]['content']}")
            print(f"A: {pair['messages'][2]['content'][:300]}...")
            print(f"   Source: {pair['metadata']['source']}")

    print(f"\nDataset ready:")
    print(f"  Train: {len(train_pairs)} pairs  ->  {TRAIN_FILE}")
    print(f"  Eval:  {len(eval_pairs)} pairs   ->  {EVAL_FILE}")
    print(f"\nNext step: python training/finetune.py")


if __name__ == "__main__":
    main()
