# rules/query_parser.py
# pulls the purchase details out of a plain english question with regex:
# dollar amounts, federal vs not, mixed funding split, multi-year, split orders,
# sole source reasons, equipment items, displacement etc.
#
# this only fills in a PurchaseRequest, the actual decision happens in the engine

import re
from dataclasses import dataclass, field
from typing import Optional

from rules.models import EquipmentItem, PurchaseRequest

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10, "twelve": 12}

AMOUNT_RE = re.compile(
    r"\$\s?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<dec>\.\d+)?\s*(?P<mult>k|m|mm|million|thousand)?\b"
    r"|\b(?P<num2>\d+(?:\.\d+)?)\s?(?P<mult2>k)\b",
    re.I,
)
# amounts that are a threshold/limit people mention, not the actual purchase
REFERENCE_BEFORE = re.compile(
    r"(threshold|limit|maximum|minimum|cap)\s*(is|of|at|amount of)?\s*(the\s+)?$"
    r"|\b(under|below|over|exceeds?|exceeding|above|than|up to|at least|within)\s+(the\s+)?(approximately\s+)?$",
    re.I,
)
REFERENCE_AFTER = re.compile(
    r"^\s*(\w+\s+){0,2}(threshold|limit|per occurrence|umbrella|coverage|insurance|policy limit|grant\b|award\b|budget\b)",
    re.I,
)
TOTAL_BEFORE = re.compile(r"(total(ing|s)?|in total|combined|bringing .{0,40}to|overall|altogether)\s*(of|is|to)?\s*(about|approximately|roughly)?\s*$", re.I)
PER_YEAR_AFTER = re.compile(r"^\s*(/\s*(year|yr)|per\s+(year|yr|annum)|a\s+year|each\s+year|annually|every\s+year)", re.I)
YEARS_RE = re.compile(r"(?:×|x|for|over)?\s*\b(\d+|" + "|".join(NUM_WORDS) + r")[\s-]*(?:years?|yrs?)\b(?!\s+ago)", re.I)
DURATION_RE = re.compile(r"\b(\d+|" + "|".join(NUM_WORDS) + r")[\s-]*(day|week|month)s?\b", re.I)

FEDERAL_RE = re.compile(r"(?<!non-)(?<!non )\b(federal(ly)?|nih|nsf|doe|dod|nasa|usda|darpa|noaa|hhs|"
                        r"uniform guidance|2 cfr)\b", re.I)
FEDERAL_CONTRACT_RE = re.compile(r"(federal(ly funded)?|nih|nsf|doe|dod|nasa|darpa)\s+contracts?\b|"
                                 r"\bcontract (funds|funding)\b|\bFAR\b", re.I)
NONFED_PORTION_RE = re.compile(r"\b(non-?federal|state|departmental|discretionary|gift|general funds?|"
                               r"campus funds?|uc funds?|recharge|endowment|private)\b", re.I)

PROCUREMENT_CONTEXT = re.compile(r"\b(purchas\w*|buy\w*|bought|order\w*|procur\w*|vendors?|suppliers?|contract\w*|"
                                 r"bid\w*|quotes?|sspr|equipment|services?|acquisition|po\b|spend\w*|"
                                 r"janitor\w*|custodial|consult\w*|tag\w*)", re.I)

SOLE_SOURCE_RE = re.compile(r"sole.?source|single.?source|only (one|a single) (vendor|supplier|"
                            r"manufacturer|source|company)|one.of.a.kind|only available from|no other "
                            r"(manufacturer|vendor|supplier)", re.I)
SMALL_BUSINESS_RE = re.compile(r"small business|\bdvbe\b|disabled veteran", re.I)
PROF_SERVICES_RE = re.compile(r"professional (or|and|/) ?personal services|personal services", re.I)
URGENT_RE = re.compile(r"\burgen(t|cy)\b|compelling|\bemergency\b", re.I)

JUSTIFICATIONS = [   # order matters, the not-allowed ones get checked first
    ("pre_work", re.compile(r"pre-?work|customi[sz]\w+ .{0,40}(to exclude|exclud|so only)|helped (us )?(write|draft|develop) (the )?spec", re.I)),
    ("brand", re.compile(r"\bbrand\b", re.I)),
    ("price", re.compile(r"cheapest|lowest price|best price|better price|cheaper", re.I)),
    ("familiarity", re.compile(r"familiar|proficien|already (trained|know|use)|used to using|preference", re.I)),
    ("geographic", re.compile(r"\blocal (vendor|supplier|business)|nearby|geograph", re.I)),
    ("emergency", re.compile(r"\bemergency\b", re.I)),
    ("awarding_agency_approval", re.compile(r"(agency|sponsor|program officer)\s+(has\s+)?approv", re.I)),
    ("match_existing", re.compile(r"match(ing)? (our )?existing|compatib", re.I)),
    ("one_of_a_kind", re.compile(r"one.of.a.kind|unique|only (manufacturer|vendor|supplier|company)|no other "
                                 r"(manufacturer|vendor|supplier|company)|only available|only one (vendor|supplier|"
                                 r"manufacturer|company)|only available from", re.I)),
]

# "split" language = trying to divide it. "same vendor" just means the orders are related
SPLIT_INTENT_RE = re.compile(r"\bsplit|break (it |this |them |the purchase )?up|\bdivid|separate (purchase )?orders|"
                             r"(two|three|several|multiple) (separate )?(purchase )?orders|to avoid (the )?"
                             r"(competitive )?bid|stay (under|below)|smaller orders|independent purchases|"
                             r"separate purchases|without triggering", re.I)
RELATED_ORDERS_RE = re.compile(r"same (vendor|supplier|company)|" + SPLIT_INTENT_RE.pattern, re.I)
SPLIT_RE = RELATED_ORDERS_RE

EQUIPMENT_CONTEXT = re.compile(r"\btag(ged|ging)?\b|inventori(al|ed)|\basset|capitaliz|\bcaan\b|bus-29|tracked|"
                               r"equipment.{0,60}\$5,000 threshold|\$5,000 threshold.{0,60}equipment", re.I)
# insurance questions mention $ limits ($1M per occurrence etc), those aren't purchases
INSURANCE_SENTENCE = re.compile(r"insurance|liability|umbrella|per occurrence|coverage|policy limit", re.I)
ITEM_BEFORE_RE = re.compile(r"(?:an?|the|one)\s+([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*){0,2}?)\s+"
                            r"(?:for|costing|valued at|worth|priced at|at)\s*(?:about\s+)?$", re.I)
ITEM_AFTER_RE = re.compile(r"^\s*([a-z][a-z\-]*(?:\s+(?!and\b|or\b|for\b)[a-z][a-z\-]*)?)", re.I)
ITEM_STOPWORDS = {"and", "or", "for", "of", "in", "per", "from", "each", "total", "worth", "to", "the", "a",
                  "which", "that", "with", "purchase", "order", "grant", "annually", "but", "we", "i", "our",
                  "it", "is", "was", "this", "they", "you", "market", "value"}

DISPLACEMENT_RE = re.compile(r"displac|eliminat\w* (their|the|uc|our|those|these)? ?(jobs|positions)|lay ?offs?|"
                             r"laid off|replace (uc|university|our|existing) (staff|employees|workers)|job loss",
                             re.I)
CONTRACTING_EXCEPTIONS = [
    ("emergency", re.compile(r"\bemergency\b", re.I)),
    ("specialized_expertise", re.compile(r"specialized (skills|expertise|equipment)|no uc (employee|staff) has|"
                                         r"not available (internally|in-house)", re.I)),
    ("remote_facility", re.compile(r"\bremote (facility|site|location)|more than (10|ten) miles", re.I)),
    ("urgent_temporary", re.compile(r"\btemporary|occasional|one-time", re.I)),
    ("incidental_to_lease", re.compile(r"\blease\b", re.I)),
    ("registry_personnel", re.compile(r"\bregistry\b", re.I)),
    ("required_by_law", re.compile(r"required by (law|federal)|court order", re.I)),
    ("insufficient_staff", re.compile(r"insufficient (uc )?staff|not enough (uc )?staff|understaffed", re.I)),
]

TOPIC_PATTERNS = {
    "bid": re.compile(r"competitive(ly)? bid|bidding|bid threshold|formal bid|\bbid\b", re.I),
    "sspr": re.compile(r"\bsspr\b|source selection|price reasonableness", re.I),
    "federal": FEDERAL_RE,
    "mixed": re.compile(r"mixed fund|portion|state funds?|departmental|discretionary|federal fund\w* .{0,30}exceed", re.I),
    "multi_year": re.compile(r"multi-?year|\d+-year|(three|five|\d) years?|per year|annual", re.I),
    "small_business": SMALL_BUSINESS_RE,
    "sole_source": SOLE_SOURCE_RE,
    "split": SPLIT_RE,
    "equipment": re.compile(r"\btag(ged|ging)?\b|inventorial|capitaliz|\bcaan\b|bus-29|asset management", re.I),
    "micro": re.compile(r"micro-?purchase", re.I),
    "sat": re.compile(r"simplified acquisition", re.I),
    "covered": re.compile(r"contract(ing)? out|covered services?|regents policy 5402|afscme|wage parity", re.I),
}
RULE_TOPICS = {"bid", "sspr", "mixed", "multi_year", "small_business", "sole_source", "split",
               "equipment", "micro", "sat", "covered"}


@dataclass
class Amount:
    value: float
    start: int
    end: int
    reference: bool = False
    total: bool = False
    per_year: bool = False


@dataclass
class ParsedQuery:
    text: str
    request: Optional[PurchaseRequest]
    amounts: list = field(default_factory=list)
    topics: set = field(default_factory=set)
    notes: list = field(default_factory=list)

    @property
    def has_purchase(self) -> bool:
        return self.request is not None and (self.request.amount > 0 or bool(self.request.items))


def _num(word: str) -> float:
    return float(NUM_WORDS.get(word.lower(), word))


def extract_amounts(text: str) -> list:
    out = []
    for m in AMOUNT_RE.finditer(text):
        if m.group("num") is not None:
            v = float(m.group("num").replace(",", "") + (m.group("dec") or ""))
            mult = (m.group("mult") or "").lower()
        else:
            v = float(m.group("num2"))
            mult = m.group("mult2").lower()
        v *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6}.get(mult, 1)
        if v <= 0:
            continue
        before, after = text[max(0, m.start() - 45):m.start()], text[m.end():m.end() + 40]
        s_start = max(text.rfind(". ", 0, m.start()), text.rfind("? ", 0, m.start())) + 1
        s_end = min([i for i in (text.find(". ", m.end()), text.find("? ", m.end())) if i >= 0] or [len(text)])
        sentence = text[s_start:s_end]
        out.append(Amount(
            value=v, start=m.start(), end=m.end(),
            reference=bool(REFERENCE_BEFORE.search(before) or REFERENCE_AFTER.search(after)
                           or INSURANCE_SENTENCE.search(sentence)),
            total=bool(TOTAL_BEFORE.search(before)),
            per_year=bool(PER_YEAR_AFTER.search(after)),
        ))
    return out


def _window_after(text: str, amt: Amount, amounts: list) -> str:
    nxt = [a.start for a in amounts if a.start > amt.start]
    return text[amt.end:min(nxt[0] if nxt else len(text), amt.end + 70)]


def _years(text: str) -> float:
    m = YEARS_RE.search(text)
    if not m or re.search(r"fiscal year|this year|next year|last year|per year", m.group(0), re.I):
        return 1.0
    return max(_num(m.group(1)), 1.0)


def _duration_days(text: str) -> Optional[int]:
    m = DURATION_RE.search(text)
    if not m:
        return None
    return int(_num(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2).lower()])


def _equipment_items(text: str, amounts: list) -> list:
    items = []
    for i, a in enumerate(amounts):
        if a.reference:
            continue
        name = None
        mb = ITEM_BEFORE_RE.search(text[max(0, a.start - 50):a.start])
        if mb:
            name = mb.group(1)
        else:
            ma = ITEM_AFTER_RE.search(text[a.end:a.end + 40])
            if ma and ma.group(1).split()[0].lower() not in ITEM_STOPWORDS:
                name = ma.group(1)
        if name:
            words = [w for w in name.split() if w.lower() not in ITEM_STOPWORDS]
            name = " ".join(words) or None
        items.append(EquipmentItem(name=(name or f"Item {i + 1}").strip(), cost=a.value,
                                   is_accessory=bool(re.search(r"accessor", name or "", re.I))))
    return items


def parse_query(text: str) -> ParsedQuery:
    topics = {t for t, p in TOPIC_PATTERNS.items() if p.search(text)}
    amounts = extract_amounts(text)
    concrete = [a for a in amounts if not a.reference]
    notes = []

    # tagging question -> treat every $ amount as an item
    if EQUIPMENT_CONTEXT.search(text) and concrete:
        items = _equipment_items(text, concrete)
        req = PurchaseRequest(amount=0.0, items=items, description=text)
        return ParsedQuery(text, req, amounts, topics | {"equipment"}, notes)

    federal = bool(FEDERAL_RE.search(text))
    funding = "non_federal"
    if federal:
        funding = "federal_contract" if FEDERAL_CONTRACT_RE.search(text) else "federal_grant"

    common = dict(description=text, displaces_uc_employees=bool(DISPLACEMENT_RE.search(text)) or None)
    duration = _duration_days(text)

    if not concrete or not PROCUREMENT_CONTEXT.search(text):
        # no real purchase amount, but still run the category checks (covered services etc)
        req = PurchaseRequest(amount=0.0, funding=funding, **common)
        return ParsedQuery(text, req, amounts, topics, notes)

    # figure out which amount is the total and which are pieces
    total = next((a for a in concrete if a.total), None)
    if total is None and len(concrete) >= 3:
        for a in concrete:
            others = [o.value for o in concrete if o is not a]
            if abs(sum(others) - a.value) < 1:
                total = a
                break
    parts = [a for a in concrete if a is not total]

    # mixed funding - look at the words right after each amount
    fed_parts, nonfed_parts = [], []
    for a in parts:
        w = _window_after(text, a, concrete)
        if NONFED_PORTION_RE.search(w):
            nonfed_parts.append(a)
        elif FEDERAL_RE.search(w):
            fed_parts.append(a)

    amount, fed_amount, related, years = 0.0, None, [], 1.0
    split_intent = bool(SPLIT_INTENT_RE.search(text))
    related_signal = bool(RELATED_ORDERS_RE.search(text))

    if fed_parts and (nonfed_parts or total):
        amount = total.value if total else sum(a.value for a in fed_parts + nonfed_parts)
        fed_amount = sum(a.value for a in fed_parts)
        if funding == "non_federal":
            funding = "federal_grant"
        notes.append(f"mixed funding: ${fed_amount:,.0f} federal of ${amount:,.0f}")
    elif total and len(parts) >= 2 and abs(sum(a.value for a in parts) - total.value) < 1 and related_signal:
        amount, related = parts[0].value, [a.value for a in parts[1:]]
    elif total:
        amount = total.value
    elif len(parts) >= 2 and related_signal:
        amount, related = parts[0].value, [a.value for a in parts[1:]]
    else:
        main = max(parts, key=lambda a: a.value)
        amount = main.value
        years = _years(text)
        if main.per_year and years > 1:
            amount = main.value * years
            notes.append(f"multi-year: ${main.value:,.0f}/year x {years:g} years = ${amount:,.0f}")

    if years == 1.0 and not related:
        years = _years(text) if not any(a.per_year for a in parts) else years

    # source selection
    selection, justification = None, None
    is_federal = funding != "non_federal"
    if SOLE_SOURCE_RE.search(text) or (is_federal and re.search(r"\bemergency\b", text, re.I)):
        selection = "sole_source"
        justification = next((code for code, p in JUSTIFICATIONS if p.search(text)), None)
        if justification == "one_of_a_kind" and not re.search(r"one.of.a.kind|unique|no other|only (manufacturer|available)", text, re.I):
            justification = None   # just saying "sole source" isn't a reason
    elif SMALL_BUSINESS_RE.search(text):
        selection = "small_business"
    elif PROF_SERVICES_RE.search(text):
        selection = "professional_services"
    elif URGENT_RE.search(text):
        selection = "urgent"

    exception = next((code for code, p in CONTRACTING_EXCEPTIONS if p.search(text)), None)

    req = PurchaseRequest(
        amount=amount, funding=funding, federal_amount=fed_amount,
        source_selection=selection, sole_source_justification=justification,
        contract_years=years, duration_days=duration, related_orders=related,
        split_intent=split_intent,
        contracting_out_exception=exception, **common,
    )
    return ParsedQuery(text, req, amounts, topics, notes)
