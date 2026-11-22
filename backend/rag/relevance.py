"""
backend/rag/relevance.py
LLM-based relevance check: given a search term and a list of product titles,
flag which products do not match what the user is looking for.
"""

import json
import logging
import os
import re

import ollama
from pydantic import BaseModel, ConfigDict, Field, StrictBool

logger = logging.getLogger("agile_sourcing.relevance")

LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")
LLM_TIMEOUT_S = 60
LLM_KEEP_ALIVE = "30m"
MAX_ITEMS = 100

SYSTEM_PROMPT = (
    "You are a procurement search relevance evaluator. "
    "Given a user's search term and a list of product titles from a purchasing platform, "
    "determine whether each product is what the user is likely looking for. "
    "Consider: material, product type, size/format, intended use. "
    "A product that shares a keyword but is a different product type is IRRELEVANT "
    '(e.g., searching "laptop" \u2192 "laptop stand" is irrelevant). '
    "When in doubt, mark as relevant."
)

USER_TEMPLATE = (
    'Search: "{search}"\n'
    "Products:\n"
    "{products}\n\n"
    'Return JSON: {{"flags": [{{"item": "...", "relevant": true/false, "reason": "..."}}]}}'
)


class ItemFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1, max_length=500)
    relevant: StrictBool
    reason: str = Field(min_length=1, max_length=300)


class RelevanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flags: list[ItemFlag]


def _build_prompt(search: str, items: list[str]) -> str:
    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))
    return USER_TEMPLATE.format(search=search, products=numbered)


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?(</think>|$)", "", raw, flags=re.DOTALL).strip()


def check_relevance(search: str, items: list[str]) -> RelevanceResult:
    """
    Call the LLM to evaluate each product title against the search term.
    Returns a RelevanceResult with one ItemFlag per item.
    Falls back to marking all items relevant if the LLM fails.
    """
    if not items:
        return RelevanceResult(flags=[])

    items = items[:MAX_ITEMS]
    prompt = _build_prompt(search, items)
    llm = ollama.Client(timeout=LLM_TIMEOUT_S)

    for attempt in range(2):
        response = llm.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            format="json",
            think=False,
            keep_alive=LLM_KEEP_ALIVE,
            options={"temperature": 0, "num_predict": 4096},
        )
        raw = _strip_think(response["message"]["content"])
        try:
            result = RelevanceResult.model_validate_json(raw)
            if len(result.flags) == len(items):
                return result
            logger.warning(
                "LLM returned %d flags for %d items (attempt %d)",
                len(result.flags), len(items), attempt + 1,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid LLM response (attempt %d): %s", attempt + 1, exc)

    return RelevanceResult(flags=[
        ItemFlag(item=item, relevant=True, reason="Could not evaluate (LLM error)")
        for item in items
    ])