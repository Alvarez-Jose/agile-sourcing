# rules/answer_format.py
# fixed answer format when the rule engine decides a question:
#
#   Answer:     what the LLM wrote, consistent with the determination
#   Rule:       the determination, word for word from the engine
#   Source:     document / version / page / section + quote, from rules/provenance.py
#   Conditions: what the LLM wrote (exceptions, next steps), citing excerpts [n]
#
# Rule and Source never come from the LLM, so it can't change a threshold or a source.

import re

from rules.engine import EvaluationResult

HEADER_PREFIX = "Determination (rule engine): "


def split_llm_sections(text: str) -> tuple[str, str]:
    # pull "Answer:" and "Conditions:" out of the LLM reply. anything it wrote under
    # Rule:/Source: is dropped since those lines are filled in by the engine
    text = text.strip()
    cond = re.search(r"^\s*\**Conditions\**\s*:\s*", text, re.I | re.M)
    head, conditions = (text[:cond.start()], text[cond.end():]) if cond else (text, "")
    head = re.split(r"^\s*\**(?:Rule|Source)s?\**\s*:", head, flags=re.I | re.M)[0]
    head = re.sub(r"^\s*\**Answer\**\s*:\s*", "", head.strip(), flags=re.I)
    conditions = re.split(r"^\s*\**(?:Rule|Source)s?\**\s*:", conditions, flags=re.I | re.M)[0]
    return " ".join(head.split()), conditions.strip() or "None"


def rule_line(result: EvaluationResult) -> str:
    header = result.to_answer_header()
    return header[len(HEADER_PREFIX):] if header.startswith(HEADER_PREFIX) else header


def source_line(result: EvaluationResult) -> str:
    return "; ".join(f'{s.cite()}: "{s.quote}"' for s in result.sources) or "See the policy excerpts cited below."


def format_rule_answer(result: EvaluationResult, llm_text: str) -> str:
    answer, conditions = split_llm_sections(llm_text)
    return (f"Answer: {answer or rule_line(result)}\n"
            f"Rule: {rule_line(result)}\n"
            f"Source: {source_line(result)}\n"
            f"Conditions: {conditions}")
