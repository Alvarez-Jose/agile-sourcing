# rules/engine.py
# puts funding + thresholds + forms + category flags together and formats the
# result block that goes into the LLM prompt.
#
#   from rules import RuleEngine, PurchaseRequest
#   result = RuleEngine().evaluate(PurchaseRequest(amount=175_000, funding="federal_grant",
#                                                  source_selection="sole_source"))
#   print(result.to_prompt_context())
#
#   # or from a question directly
#   result = RuleEngine().evaluate_query("Do I need to bid a $150K NIH-funded purchase?")

from dataclasses import dataclass, field
from typing import Optional

from rules import thresholds as T
from rules.category_flags import (AFSCME_NOTICE_THRESHOLD, CONTRACTING_OUT_EXCEPTIONS, COVERED_SERVICES,
                                  EQUIPMENT_TAG_THRESHOLD, CategoryResult, evaluate_categories)
from rules.form_router import route_forms
from rules.funding_rules import MIXED_FUNDING_FEDERAL_TRIGGER, FundingDetermination, determine_funding
from rules.models import Flag, PurchaseRequest
from rules.query_parser import RULE_TOPICS, ParsedQuery, parse_query
from rules.thresholds import ThresholdDetermination, detect_split_order, evaluate_thresholds

HEADER = "=== RULE ENGINE DETERMINATION (authoritative - do not override) ==="
FOOTER = "=== END RULE ENGINE DETERMINATION ==="


@dataclass
class EvaluationResult:
    request: PurchaseRequest
    funding: Optional[FundingDetermination]
    thresholds: Optional[ThresholdDetermination]
    categories: CategoryResult
    forms: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    reference: list = field(default_factory=list)

    # shortcuts used by the tests / pipeline
    @property
    def competitive_bid_required(self) -> Optional[bool]:
        return self.thresholds.competitive_bid_required if self.thresholds else None

    @property
    def sspr_required(self) -> Optional[bool]:
        return self.thresholds.sspr_required if self.thresholds else None

    @property
    def sspr_sections(self) -> list:
        return self.thresholds.sspr_sections if self.thresholds else []

    @property
    def federal_rules_apply(self) -> Optional[bool]:
        return self.funding.federal_rules_apply if self.funding else None

    @property
    def form_names(self) -> list:
        return [f.name for f in self.forms]

    def has_flag(self, code: str) -> bool:
        return any(f.code == code for f in self.flags)

    @property
    def is_empty(self) -> bool:
        return not (self.thresholds or self.categories.equipment or self.flags or self.reference)

    @property
    def is_substantive(self) -> bool:
        # True if the engine actually decided something worth putting in the answer
        # (something required/blocked, or equipment items). a $5K purchase that
        # triggers nothing, or just reference facts, doesn't count
        return bool(
            self.competitive_bid_required or self.sspr_required or self.forms or self.categories.equipment
            or any(f.severity in ("block", "require", "caution") for f in self.flags)
        )

    # output formatting
    def summary_lines(self) -> list:
        lines = []
        if self.funding:
            lines.append(f"FUNDING: {self.funding.explanation}")
        if self.thresholds:
            t = self.thresholds
            lines.append("THRESHOLDS: " + " ".join(t.explanations))
            lines.append(f"  Competitive bid required: {'YES' if t.competitive_bid_required else 'NO'}")
            lines.append(f"  SSPR form required: {'YES' if t.sspr_required else 'NO'}")
            if t.sspr_required:
                lines.append(f"  SSPR sections: {', '.join(t.sspr_sections)}")
        if self.categories.equipment:
            lines.append("EQUIPMENT TAGGING (BUS-29):")
            lines += [f"  - {e.explanation}" for e in self.categories.equipment]
        if self.forms:
            lines.append("REQUIRED FORMS:")
            for f in self.forms:
                lines.append(f"  - {f.name}" + (f": {f.detail}" if f.detail else "") + f"  [{f.reason}]")
        blocking = [f for f in self.flags if f.severity in ("block", "require", "caution")]
        info = [f for f in self.flags if f.severity == "info"]
        if blocking:
            lines.append("COMPLIANCE FLAGS:")
            lines += [f"  - [{f.severity.upper()}] {f.message} ({f.policy})" for f in blocking]
        if info:
            lines.append("RELATED POLICIES:")
            lines += [f"  - {f.message} ({f.policy})" for f in info]
        if self.reference:
            lines.append("POLICY THRESHOLDS (reference):")
            lines += [f"  - {r}" for r in self.reference]
        return lines

    def to_answer_header(self) -> str:
        # one line summary that goes at the very top of the answer. qwen was sometimes
        # arguing with the determination in its explanation, so this makes sure the
        # real answer is always there word for word
        parts = []
        if self.funding:
            if self.funding.is_mixed:
                parts.append(f"Federal rules {'apply to the entire transaction' if self.federal_rules_apply else 'do NOT apply; UC/State rules only'} "
                             f"(federal portion ${self.funding.federal_amount:,.0f} "
                             f"{'exceeds' if self.federal_rules_apply else 'does not exceed'} $10,000).")
        if self.thresholds:
            t = self.thresholds
            parts.append(f"Competitive bid required: {'YES' if t.competitive_bid_required else 'NO'} "
                         f"(${t.evaluated_value:,.0f}; threshold $100,000"
                         + (f"; exemption: {t.bid_exemption}" if t.bid_exemption and t.bid_threshold_exceeded else "") + ").")
            parts.append(f"SSPR required: {'YES' if t.sspr_required else 'NO'} (threshold ${t.sspr_threshold:,.0f}"
                         + (f"; sections {', '.join(t.sspr_sections)}" if t.sspr_required else "") + ").")
        for e in self.categories.equipment:
            parts.append(f"{e.item.name} (${e.item.cost:,.0f}): {'must be tagged' if e.must_tag else 'no tagging required'} "
                         f"(BUS-29 threshold ${e.threshold:,}).")
        for f in self.flags:
            if f.severity in ("block", "require") and f.code in ("SPLIT_ORDER", "SOLE_SOURCE_INVALID", "SB_LIMIT_EXCEEDED"):
                parts.append(f.message)
        cs = self.categories.covered_service
        if cs:
            parts.append(f"Covered service ({', '.join(cs.services)}) under Regents Policy 5402: "
                         + ("PROHIBITED (displaces UC employees)." if cs.prohibited else "allowed only under a listed exception.")
                         + f" AFSCME notice: {'YES' if cs.afscme_notice_required else 'NO'}."
                         + (f" Wage/benefit parity: {'YES' if cs.wage_parity_required else 'NO'}." if cs.afscme_notice_required else ""))
        forms = [f.name for f in self.forms if f.name != "SSPR Form"]
        if forms:
            parts.append("Also required: " + "; ".join(forms) + ".")
        if not parts and self.reference:
            parts = self.reference[:1]
        return "Determination (rule engine): " + " ".join(parts) if parts else ""

    def to_prompt_context(self) -> str:
        return "\n".join([HEADER, *self.summary_lines(), FOOTER])

    def to_dict(self) -> dict:
        return {
            "federal_rules_apply": self.federal_rules_apply,
            "competitive_bid_required": self.competitive_bid_required,
            "sspr_required": self.sspr_required,
            "sspr_sections": self.sspr_sections,
            "forms": self.form_names,
            "flags": [f.code for f in self.flags],
            "equipment": [(e.item.name, e.item.cost, e.must_tag) for e in self.categories.equipment],
        }


# general facts for questions that don't have a specific purchase in them
REFERENCE_FACTS = {
    "bid": [f"Competitive bid required at ${T.COMPETITIVE_BID_THRESHOLD:,} or more (BUS-43: more than $100,000 "
            "annually, aggregated per supplier; CA Public Contract Code). The same $100,000 bid threshold applies "
            f"to federal funds because the CA PCC is stricter than the ${T.SIMPLIFIED_ACQUISITION_THRESHOLD:,} "
            "federal Simplified Acquisition Threshold."],
    "sspr": [f"SSPR form required for: federal contract purchases >= ${T.SSPR_FEDERAL_CONTRACT:,}; federal "
             f"grant/cooperative agreement purchases >= ${T.SSPR_FEDERAL_GRANT:,}; non-federal purchases >= "
             f"${T.SSPR_NON_FEDERAL:,}.",
             "SSPR sections by source selection: competitive bid I, VII, VIII; federal competitive proposals "
             "(<$100K, 3 quotes per 2 CFR 200.320(a)(2)(i)) I, II, VII, VIII; federal sole source I, III, IV, VII, "
             "VIII; non-federal sole source I, III-VIII; small business/DVBE I, III, VII, VIII; professional/"
             "personal services (non-federal) I, III, V, VII, VIII; unusual & compelling urgency (non-federal) "
             "I, VI, VII, VIII."],
    "federal": [f"Federal micro-purchase threshold: ${T.FEDERAL_MICRO_PURCHASE:,}; campuses may set up to "
                f"${T.CAMPUS_GRANT_MICRO_PURCHASE_MAX:,} for grants/cooperative agreements (OMB). Simplified "
                f"Acquisition Threshold: ${T.SIMPLIFIED_ACQUISITION_THRESHOLD:,}.",
                "Federally funded orders require the Federal Funds Checklist, Debarment & Suspension verification, "
                f"Anti-Lobbying (Byrd) verification at ${T.ANTI_LOBBYING_THRESHOLD:,}+, and flow-down articles "
                "(grants: UC T&C Articles 1, 8.1(c)(i-v), 11.8, 11.9, 11.10; contracts: 8.1(a) or 8.1(b), 1, 11.10)."],
    "mixed": [f"Mixed funding: if the federal portion exceeds ${MIXED_FUNDING_FEDERAL_TRIGGER:,}, federal "
              "requirements apply to the ENTIRE transaction; if it is $10,000 or less, only UC/State rules apply "
              "(SSPR FAQ)."],
    "multi_year": ["Multi-year agreements: with federal funds, use the total anticipated contract value (e.g. "
                   "$25K/year x 5 years = $125K must be bid and use the SSPR). BUS-43 alone looks at annual "
                   "expenditures of more than $100,000."],
    "small_business": [f"Certified small business/DVBE: may award up to ${T.SMALL_BUSINESS_LIMIT:,} without formal "
                       "bid, any funding source. BUS-43: 1 SB/DVBE quote for $10K-$100K; 2 quotes from certified "
                       "SB/DVBEs for $100K-$250K. (SSPR form federal SB option: under $100K.)"],
    "sole_source": ["Allowable sole source justifications - federal: one-of-a-kind, emergency, awarding agency "
                    "approval, no competition (grants/coops only); non-federal: one-of-a-kind/unique, match "
                    "existing (UC PO#). NOT allowable: pre-work with the supplier that excludes competition, price, "
                    "brand name, and (federal) geographic preference. Document in SSPR Section IV.",
                    f"Sole-sourced federal non-commercial contract orders >= ${T.CERTIFIED_COST_PRICING_THRESHOLD:,} "
                    "require certified cost or pricing data (FAR 15.403-4)."],
    "split": ["Split orders: requirements must not be artificially divided into separate transactions to avoid "
              "competition (BUS-43). Related orders are evaluated at their combined value."],
    "equipment": [f"BUS-29: equipment costing ${EQUIPMENT_TAG_THRESHOLD:,} or more must be inventoried, tagged, "
                  "tracked, and assigned a CAAN (threshold was $1,500 before July 1, 2004). Items under $5,000 are "
                  "not inventorial equipment. Accessories of $5,000+ acquired later must also be capitalized."],
    "micro": [f"Federal micro-purchase threshold: ${T.FEDERAL_MICRO_PURCHASE:,} (campus may set up to "
              f"${T.CAMPUS_GRANT_MICRO_PURCHASE_MAX:,} for grants/cooperative agreements)."],
    "sat": [f"Federal Simplified Acquisition Threshold: ${T.SIMPLIFIED_ACQUISITION_THRESHOLD:,}; UC still bids at "
            f"${T.COMPETITIVE_BID_THRESHOLD:,} because the CA PCC is stricter."],
    "covered": ["Regents Policy 5402 generally prohibits contracting out covered services that UC employees can "
                "perform: " + ", ".join(COVERED_SERVICES) + ".",
                "Exceptions: " + "; ".join(CONTRACTING_OUT_EXCEPTIONS.values()) + ". Contracting out must not "
                "displace UC employees (demotion, layoff, or involuntary reduction in time).",
                f"Covered-service contracts over ${AFSCME_NOTICE_THRESHOLD:,}: notify AFSCME 3299 (30 days, or RFP "
                "copy at issuance; 14 days to respond). Over $100,000 and more than 90 days: wage/benefit parity."],
}


def reference_facts(topics: set) -> list:
    facts = []
    for topic in REFERENCE_FACTS:
        if topic in topics:
            facts += REFERENCE_FACTS[topic]
    return facts


class RuleEngine:
    def evaluate(self, req: PurchaseRequest, topics: Optional[set] = None) -> EvaluationResult:
        funding, thresholds = None, None
        flags: list = []

        if req.amount > 0:
            funding = determine_funding(req)
            split_flags = detect_split_order(req, funding)
            aggregate = req.amount + sum(float(o) for o in req.related_orders)
            thresholds = evaluate_thresholds(req, funding, aggregate=aggregate)
            flags += split_flags + thresholds.flags
            if funding.is_mixed and not funding.federal_rules_apply:
                flags.append(Flag("FEDERAL_PORTION_BELOW_TRIGGER", "info",
                                  "Federal dollars are present but at or below $10,000, so only UC/State "
                                  "procurement rules govern this transaction.", "SSPR FAQ"))

        categories = evaluate_categories(req)
        flags += categories.flags
        forms = route_forms(funding, thresholds, categories) if thresholds else \
            route_forms(_no_funding(), _no_thresholds(), categories)

        reference = reference_facts(topics or set()) if req.amount == 0 and not req.items else []
        return EvaluationResult(req, funding, thresholds, categories, forms, flags, reference)

    def evaluate_query(self, question: str) -> EvaluationResult:
        parsed = parse_query(question)
        return self.evaluate(parsed.request, topics=parsed.topics)


def _no_funding() -> FundingDetermination:
    return FundingDetermination(0, 0, 0, None, False, False, "")


def _no_thresholds() -> ThresholdDetermination:
    return ThresholdDetermination(0, "", False, False, None, False, 0, "", [], None)


def should_use_rule_engine(question: str, parsed: Optional[ParsedQuery] = None) -> bool:
    # True if there's something in the question the engine can actually decide:
    # a purchase amount, equipment items, a covered service, or a threshold type
    # topic (bid, SSPR, split, mixed funding, small business, sole source, tagging...)
    parsed = parsed or parse_query(question)
    if parsed.has_purchase:
        return True
    if parsed.topics & RULE_TOPICS:
        return True
    return bool(evaluate_categories(parsed.request).covered_service)
