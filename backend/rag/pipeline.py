"""
backend/rag/pipeline.py
RAG pipeline entry point for the FastAPI backend.
Call ask() from your API routes to get answers from the UC policy corpus.
"""

import re
from functools import lru_cache

from backend.rag.access import ScopedCollection, ScopedCorpus
from rag_pipeline.documents.models import AccessScope
from rag_pipeline.documents.store import DEFAULT_INDEX, PolicyIndex
from rag_pipeline.indexer.source_chroma import CHROMA_DIR, POINTER_NAME, active_collection
from rag_pipeline.retriever.section_retriever import requested_source_ids, requested_sources_available
from rules import RuleEngine, parse_query, should_use_rule_engine
from rules.answer_format import (format_rule_answer, is_pure_threshold_question, source_citations,
                                 templated_answer)
from rules.query_parser import RULE_TOPICS

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
# topics where the engine actually decides something ("multi_year" alone just means "annual")
DECISION_TOPICS = RULE_TOPICS - {"multi_year"}

# when the rule engine fires, the LLM only explains its fixed determination. Rule and
# Source lines are filled in from the determination/provenance, not by the LLM
FIXED_FORMAT_INSTRUCTIONS = (
    "The FIXED DETERMINATION and its SOURCES below are final. Do not change, recompute or contradict any "
    "YES/NO, dollar amount, threshold, form or prohibition in them, and do not mention a rule engine. "
    "Your only job is to explain them for this question.\n"
    "Reply in exactly this format and nothing else:\n"
    "Answer: <1-3 sentences that directly answer the user's actual question, consistent with the "
    "determination. Start with Yes or No if it is a yes/no question.>\n"
    "Conditions: <the conditions, exceptions or next steps that matter for this question, citing policy "
    "excerpts as [1], [2]; or None>\n"
)

rule_engine = RuleEngine()


@lru_cache(maxsize=1)
def _get_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


@lru_cache(maxsize=1)
def _get_classifier():
    from rag_pipeline.retriever.intent_classifier import IntentClassifier
    return IntentClassifier(_get_embedder())


def get_collection():
    import chromadb
    # Legacy/preview collections have no reviewed generation pointer.
    if not (CHROMA_DIR / POINTER_NAME).exists():
        raise ValueError("Reviewed policy vectors not published; run python -m scripts.ingest_policies --ingest")
    return active_collection(chromadb.PersistentClient(path=str(CHROMA_DIR)))


def _get_retriever(collection):
    from rag_pipeline.indexer.hybrid_index import HybridRetriever
    return HybridRetriever(collection, _get_embedder())


@lru_cache(maxsize=1)
def _get_reranker():
    from rag_pipeline.retriever.reranker import Reranker
    return Reranker()


LLM_KEEP_ALIVE = "30m"   # keep qwen3 in memory between requests (Ollama's default unloads after 5m)
# qwen3 sometimes loops (seen at 23k+ tokens on a warm-up question), and with no cap the
# request never returns. answers on the benchmark top out around 600 tokens.
ANSWER_MAX_TOKENS = 1024
REWRITE_MAX_TOKENS = 48
LLM_TIMEOUT_S = 90
@lru_cache(maxsize=1)
def _get_llm():
    import ollama
    return ollama.Client(host="http://127.0.0.1:11434", timeout=LLM_TIMEOUT_S)


def warm_up():
    # Optional startup warm-up loads models, never an unscoped policy corpus.
    _get_classifier()
    _get_reranker().rerank("warm up", [{"document": "warm up", "metadata": {}}], top_k=1)
    try:
        _get_llm().generate(model=LLM_MODEL, prompt="", keep_alive=LLM_KEEP_ALIVE)
    except Exception:
        pass   # Ollama not running yet; the first question will load it


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
    try:
        response = _get_llm().chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            keep_alive=LLM_KEEP_ALIVE,
            options={"num_predict": REWRITE_MAX_TOKENS},
        )
    except Exception:
        return question     # search with the question itself rather than fail
    return _strip_think(response["message"]["content"]) or question


def _strip_think(raw: str) -> str:
    # drop <think> blocks, including one cut off by the token cap
    return re.sub(r"<think>.*?(</think>|$)", "", raw, flags=re.DOTALL).strip()


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
    # a stray dollar amount with nothing required and no procurement topic isn't a rule
    # question ("a $50 classroom order" of tax-free alcohol, benchmark Q36)
    if not result.is_substantive and not result.reference and not parsed.topics & DECISION_TOPICS:
        return None
    return result


def ask(question: str, think: bool = False, use_rules: bool = True, use_reranker: bool = True,
        *, scope=None, index_path=DEFAULT_INDEX) -> dict:
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
    scope = scope if scope is not None else AccessScope()
    if scope.include_review or scope.include_archived:
        raise ValueError("Chat cannot use local-review or archived-source access")
    corpus = ScopedCorpus(PolicyIndex(index_path, scope))
    if not requested_sources_available(question, list(corpus.documents.values())):
        return _refusal([], {"intent": "unavailable_source"}, "unavailable_source")
    if not corpus.records:
        return _refusal([], {"intent": "empty_corpus"}, "no_authorized_sources")

    intent = _get_classifier().classify(question)
    rule_result = _evaluate_rules(question, intent) if use_rules else None
    rule_citations = corpus.rule_citations(rule_result) if rule_result else None
    if rule_result and not rule_citations:
        rule_result = None   # rule constants never bypass source review or clearance

    # pure threshold question: answer straight from the engine, no retrieval or LLM
    if rule_result and is_pure_threshold_question(rule_result, intent["intent"]):
        citations = rule_citations
        return {"answer": templated_answer(rule_result), "sources": citations, "citations": citations,
                "intent": intent["intent"], "determination": rule_result.to_prompt_context(),
                "rule_sources": [s.to_dict() for s in rule_result.sources], "refused": False,
                "llm_called": False}

    requested = requested_source_ids(question)
    collection = ScopedCollection(get_collection(), corpus, requested or None)
    if not collection.count():
        return _refusal([], intent, "no_authorized_sources")
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
        citation = corpus.citation(meta, i + 1)
        citation["score"] = round(score, 3) if score is not None else None
        sources.append(citation)

    if not sources:
        return _refusal([], intent, "no_retrieval_results")

    if not rule_result and scores and scores[0] is not None and scores[0] < REFUSAL_MIN_RERANK:
        return _refusal(sources, intent, "low_retrieval_score")

    mode_tag = "/think" if think else "/no_think"
    if rule_result:
        prompt = (
            f"{mode_tag}\n\n"
            f"{SYSTEM_PROMPT}\n\n"
            f"{FIXED_FORMAT_INSTRUCTIONS}\n"
            f"FIXED DETERMINATION:\n{rule_result.to_answer_header()}\n{rule_result.to_prompt_context()}\n\n"
            "SOURCES FOR THE DETERMINATION:\n" + "\n".join(f"- {line}" for line in rule_result.source_lines()) + "\n\n"
            f"POLICY EXCERPTS:\n{context}\n"
            f"QUESTION: {question}\n"
        )
    else:
        prompt = (
            f"{mode_tag}\n\n"
            f"{SYSTEM_PROMPT}\n\n"
            "RULES:\n"
            "- Read every excerpt carefully before answering.\n"
            "- If ANY excerpt contains the answer, use it.\n"
            "- Cite source numbers [1], [2] etc. for every claim.\n"
            "- Be direct and specific.\n\n"
            f"POLICY EXCERPTS:\n{context}\n"
            f"QUESTION: {question}\n\n"
            "ANSWER:"
        )

    try:
        response = _get_llm().chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            keep_alive=LLM_KEEP_ALIVE,
            # /think spends tokens on reasoning first, so give it more room
            options={"num_predict": ANSWER_MAX_TOKENS * (4 if think else 1)},
        )
        answer = _strip_think(response["message"]["content"])
    except Exception:
        if not rule_result:
            raise
        answer = ""     # the engine's determination still answers it (format_rule_answer)

    if not rule_result and VAGUE_ANSWER.search(answer):
        return _refusal(sources, intent, "llm_found_no_answer")

    if rule_result:
        answer = format_rule_answer(rule_result, answer)

    valid_refs = {str(s["ref"]) for s in sources}
    if set(re.findall(r"\[(\d+)\]", answer)) - valid_refs:
        return _refusal([], intent, "invalid_citation")

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
        "llm_called": True,
    }


def _refusal(sources: list, intent: dict, reason: str) -> dict:
    # closest sections still come back in "sources" so a user can check them
    for s in sources:
        s["cited"] = False
    return {"answer": NOT_FOUND_ANSWER, "sources": sources, "citations": [], "intent": intent["intent"],
            "determination": None, "rule_sources": [], "refused": True, "refusal_reason": reason,
            "llm_called": reason in {"llm_found_no_answer", "invalid_citation"}}
