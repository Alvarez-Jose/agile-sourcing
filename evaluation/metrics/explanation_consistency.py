"""Conservative checks for contradictions in the user-facing Answer field.

This is a narrow, deterministic triage tool, NOT a general factuality judge.
It compares the Answer section with an independently supplied expected decision.
Rule/Source/Conditions are intentionally excluded: Rule is a fixed authoritative
block inserted by the backend and must not mask contradictory generated prose.
"""
import re

SECTION = re.compile(r"^\s*(?:\*\*)?(?:Rule|Source|Conditions)(?:\*\*)?\s*:", re.I | re.M)
ANSWER = re.compile(r"^\s*(?:\*\*)?Answer(?:\*\*)?\s*:\s*", re.I)
LEADING = re.compile(r"^\s*(yes|no)\b[\s,.:;!\-]*", re.I)

# A check specifically about the topic asked in each case. Broad words like
# "required" alone are deliberately excluded because different forms may apply.
TOPIC = {
    'bid': r'(?:competitive\s+(?:bids?|bidding)|\bcompetitive\s+bid\s+process\b)',
    'sspr': r'\bSSPR\b(?:\s+form)?',
}
PREDICATE = r'(?:is|are|was|were|would\s+be|will\s+be)\s+(?P<neg>not\s+)?(?:legally\s+)?(?:required|necessary|needed|mandatory)'
DO_NEED = r'(?:(?:do|does|would|will)\s+not\s+(?:need|require)|(?:do|does|would|will)\s+(?:need|require))'


def answer_section(text):
    """Get only the user-facing Answer, not fixed Rule or quoted Source material."""
    if not isinstance(text, str) or not text.strip():
        return None
    part = SECTION.split(text, maxsplit=1)[0].strip()
    if not ANSWER.match(part):
        return None  # uncertain formatting: don't treat an arbitrary source as prose
    return ANSWER.sub('', part, count=1).strip() or None


def check_explanation(answer_text, target, expected, *, refused=False, llm_called=None):
    """Return PASS / CONTRADICTION / REVIEW / NOT_RUN for an answer's main decision.

    REVIEW means the text is ambiguous or not safely parseable, not incorrect.
    We do not claim to check Conditions, exceptions, citations, or other claims.
    """
    if llm_called is False:
        return dict(status='NOT_RUN', detected=None, reason='No LLM call; not an explanation-generation test')
    if refused:
        return dict(status='REVIEW', detected=None, reason='Backend refused; no decision to compare')
    section = answer_section(answer_text)
    if not section:
        return dict(status='REVIEW', detected=None, reason='Missing or empty Answer section')
    if expected is None or target not in TOPIC:
        return dict(status='REVIEW', detected=None, reason='No supported target or expected decision')

    # In the benchmark the question is a yes/no requirement question. The LLM
    # normally begins "Yes"/"No". Scan also for an explicit topic-specific
    # statement; if the two disagree, request manual review.
    lead = LEADING.match(section)
    lead_value = (lead.group(1).lower() == 'yes') if lead else None
    topic = TOPIC[target]
    explicit = []
    # "competitive bidding is not required" / "SSPR form is required"
    for match in re.finditer(rf'{topic}\s+{PREDICATE}', section, re.I):
        explicit.append(match.group('neg') is None)
    # "an SSPR form is not required" / "competitive bidding isn't required"
    # Above is intentionally narrow; phrasing not covered receives REVIEW.
    for match in re.finditer(rf'{topic}\s+(?:isn\'t|aren\'t)\s+(?:required|needed|necessary)', section, re.I):
        explicit.append(False)
    # "I do not need competitive bids", "we need an SSPR form".
    for match in re.finditer(rf'\b(?:do|does|would|will)\s+(?P<neg>not\s+)?(?:need|require)\s+(?:an?\s+|the\s+)?{topic}', section, re.I):
        explicit.append(match.group('neg') is None)

    unique = set(explicit)
    if len(unique) > 1:
        return dict(status='REVIEW', detected=None, reason='Conflicting topic-specific statements in Answer')
    explicit_value = next(iter(unique)) if unique else None
    if lead_value is not None and explicit_value is not None and lead_value != explicit_value:
        return dict(status='REVIEW', detected=None, reason='Leading Yes/No conflicts with explanation wording')
    detected = explicit_value if explicit_value is not None else lead_value
    if detected is None:
        return dict(status='REVIEW', detected=None, reason='No unambiguous Yes/No for the tested requirement')
    if detected != expected:
        return dict(status='CONTRADICTION', detected=detected,
                    reason=f'Answer says {"YES" if detected else "NO"}; expected {"YES" if expected else "NO"} for {target}')
    return dict(status='PASS', detected=detected, reason='Answer decision agrees with expected requirement')
