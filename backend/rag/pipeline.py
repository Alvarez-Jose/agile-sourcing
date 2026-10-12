"""
backend/rag/pipeline.py
RAG pipeline entry point for the FastAPI backend.
Call ask() from your API routes to get answers from the UC policy corpus.
"""

import re
from pathlib import Path

import chromadb
import ollama
from sentence_transformers import SentenceTransformer

from rag_pipeline.parser.pdf_extractor import extract_pdf
from rag_pipeline.parser.docx_extractor import extract_docx
from rag_pipeline.parser.section_parser import chunk_by_section
from rag_pipeline.parser.metadata_tagger import tag_chunk
from rag_pipeline.indexer.hybrid_index import HybridRetriever
from rag_pipeline.retriever.intent_classifier import IntentClassifier
from rag_pipeline.retriever.reranker import Reranker
from rules import RuleEngine, parse_query, should_use_rule_engine

CHROMA_DIR      = "data/embeddings/chroma_store"
COLLECTION_NAME = "uc_policies"
EMBED_MODEL     = "all-MiniLM-L6-v2"
LLM_MODEL       = "qwen3:8b"
TOP_K           = 8     # chunks to the LLM when the reranker is off
RERANK_TOP_K    = 5     # chunks to the LLM after reranking
RERANK_POOL     = 20    # candidates per query that go into the reranker

SYSTEM_PROMPT = (
    "You are a UC procurement policy assistant for UC Santa Cruz. "
    "Answer questions strictly based on the official UC policy excerpts provided. "
    "Never output placeholder text like [Cite policy] or [Policy Text]. "
    "Always provide the actual answer. "
    "Cite source numbers like [1], [2] for every claim you make."
)

# only added to the prompt when the rule engine ran
RULE_ENGINE_INSTRUCTIONS = (
    "- A RULE ENGINE DETERMINATION block appears above the excerpts. It is computed "
    "deterministically from UC policy and is final. Your answer must agree with it: use the "
    "same YES/NO answers, dollar thresholds, required forms and prohibitions. If an excerpt "
    "seems to conflict (excerpts often describe a different funding type or threshold), the "
    "determination governs; do not call it incorrect and do not mention the rule engine. "
    "Use the excerpts only to explain and cite.\n"
)

# explicit refusals instead of vague "the excerpts don't specify" answers.
#
# REFUSAL_MIN_RERANK: if the best cross-encoder score is below this and the rule engine
# has nothing, refuse without calling the LLM. picked from the 60-question benchmark
# (full corpus): correct answers go as low as -7.70 (Q45) and -6.51 (Q43), so any floor
# above that loses correct answers (-6: 2 lost, -4: 4 lost, -2: 8 lost). -8.0 loses 0
# and still refuses clearly off-topic questions (weather -9.8, pizza -10.4, sports -8.7).
# ms-marco scores aren't calibrated for policy text, so this is a floor, not a filter.
REFUSAL_MIN_RERANK = -8.0
NOT_FOUND_ANSWER = ("Not found in policy: I couldn't find UC policy text in the indexed documents that answers "
                    "this question. Please check with Procurement, or rephrase with the policy or form name.")
# the LLM's own way of saying it has no answer; replaced with the explicit refusal above
VAGUE_ANSWER = re.compile(
    r"(excerpts?|provided (text|context|documents?)|sources?) (do(es)? not|don't) "
    r"(contain|provide|specify|mention|address|include)|not (specified|mentioned|addressed|covered) in the"
    r"|insufficient (information|evidence)|cannot (be )?(determine|answer)d?", re.I)

# topics specific enough that the reference facts help even if the intent says "rag".
# "bid" isn't in here on purpose, COI questions say "bidding companies" all the time
STRONG_RULE_TOPICS = {"covered", "sspr", "equipment", "split", "small_business", "micro", "sat", "mixed"}

embedder = SentenceTransformer(EMBED_MODEL)
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
_retriever = None
_reranker = None
rule_engine = RuleEngine()
classifier = IntentClassifier(embedder)


def get_collection():
    try:
        return chroma_client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


def _get_retriever(collection):
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(collection, embedder)
    return _retriever


def _get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker


def _rewrite_query(question: str, intent: dict) -> str:
    # intent has its own search terms for most categories
    if intent["search_terms"]:
        return intent["search_terms"]

    # "general" intent -> have the LLM pull out keywords
    prompt = (
        "/no_think\n"
        "Convert this question into UC procurement policy search keywords only.\n"
        "Output keywords only, no question format, no punctuation, under 10 words.\n\n"
        "Question: " + question + "\n\nKeywords:"
    )
    response = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _retrieve_reranked(search_query: str, question: str, collection):
    # grab candidates for both the rewritten query and the original question, then let
    # the cross-encoder pick. rerank against the original question since a lot of
    # questions rewrite to the exact same intent search terms
    retriever = _get_retriever(collection)
    candidates, seen = [], set()
    for q in dict.fromkeys([search_query, question]):
        docs, metas = retriever.retrieve(q, top_k=RERANK_POOL)
        for doc, meta in zip(docs, metas):
            if doc not in seen:
                seen.add(doc)
                candidates.append({"document": doc, "metadata": meta})
    ranked = _get_reranker().rerank(question, candidates, top_k=RERANK_TOP_K)
    return [c["document"] for c in ranked], [c["metadata"] for c in ranked], [c["rerank_score"] for c in ranked]


def _evaluate_rules(question: str, intent: dict):
    # the parser decides if the rule engine applies at all. the intent route just decides
    # how much of the result to keep - for "rag" questions only keep it if the engine
    # actually decided something, otherwise COI questions etc get random threshold text
    parsed = parse_query(question)
    if not should_use_rule_engine(question, parsed):
        return None
    result = rule_engine.evaluate(parsed.request, topics=parsed.topics)
    if result.is_empty:
        return None
    if intent["route_to"] == "rag" and not result.is_substantive \
            and not (result.reference and parsed.topics & STRONG_RULE_TOPICS):
        return None
    return result


def ask(question: str, think: bool = False, use_rules: bool = True, use_reranker: bool = True) -> dict:
    """
    Main entry point for the API.

    Returns:
        {
            "answer": str,
            "sources": [{"policy": str, "page": str}, ...],
            "intent": str,
            "determination": str | None   (rule engine block, if it ran)
            "rule_sources": [{document_id, document, version, page, section, quote, ...}]
        }
    """
    collection = get_collection()
    if collection is None:
        return {"answer": "Policy database not loaded. Run ingestion first.", "sources": []}

    intent = classifier.classify(question)
    rule_result = _evaluate_rules(question, intent) if use_rules else None
    retrieval_query = _rewrite_query(question, intent)

    if use_reranker:
        chunks, metas, scores = _retrieve_reranked(retrieval_query, question, collection)
    else:
        chunks, metas = _get_retriever(collection).retrieve(retrieval_query, top_k=TOP_K)
        scores = [None] * len(chunks)

    context = ""
    sources = []
    for i, (chunk, meta, score) in enumerate(zip(chunks, metas, scores)):
        policy = meta.get("policy_name") or meta.get("source", "Unknown")
        page = meta.get("page", "")
        context += f"\n[{i+1}] {policy}, p.{page}\n{chunk}\n"
        # policy/page are the original fields the frontend reads; the rest is the citation
        sources.append({"policy": policy, "page": page, "ref": i + 1, "section": meta.get("section", ""),
                        "file": meta.get("source", ""), "text": chunk,
                        "score": round(score, 3) if score is not None else None})

    if not rule_result and scores and scores[0] is not None and scores[0] < REFUSAL_MIN_RERANK:
        return _refusal(sources, intent, "low_retrieval_score")

    rules_block = f"{rule_result.to_prompt_context()}\n\n" if rule_result else ""
    mode_tag = "/think" if think else "/no_think"
    prompt = (
        f"{mode_tag}\n\n"
        f"{SYSTEM_PROMPT}\n\n"
        "RULES:\n"
        "- Read every excerpt carefully before answering.\n"
        "- If ANY excerpt contains the answer, use it.\n"
        "- Cite source numbers [1], [2] etc. for every claim.\n"
        "- Be direct and specific.\n"
        f"{RULE_ENGINE_INSTRUCTIONS if rule_result else ''}\n"
        f"{rules_block}"
        f"POLICY EXCERPTS:\n{context}\n"
        f"QUESTION: {question}\n\n"
        "ANSWER:"
    )

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response["message"]["content"]
    answer = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    if not rule_result and VAGUE_ANSWER.search(answer):
        return _refusal(sources, intent, "llm_found_no_answer")

    # put the rule engine's answer at the top word for word, the LLM just explains it
    header = rule_result.to_answer_header() if rule_result else ""
    if header:
        answer = f"{header}\n\n{answer}"

    for s in sources:
        s["cited"] = f"[{s['ref']}]" in answer

    return {
        "answer": answer,
        "sources": sources,
        "citations": [s for s in sources if s["cited"]],
        "intent": intent["intent"],
        "determination": rule_result.to_prompt_context() if rule_result else None,
        "rule_sources": [s.to_dict() for s in rule_result.sources] if rule_result else [],
        "refused": False,
    }


def _refusal(sources: list, intent: dict, reason: str) -> dict:
    # closest sections still come back in "sources" so a user can check them
    for s in sources:
        s["cited"] = False
    return {"answer": NOT_FOUND_ANSWER, "sources": sources, "citations": [], "intent": intent["intent"],
            "determination": None, "rule_sources": [], "refused": True, "refusal_reason": reason}
