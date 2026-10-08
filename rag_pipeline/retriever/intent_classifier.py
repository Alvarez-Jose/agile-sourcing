# rag_pipeline/retriever/intent_classifier.py
# intent classifier using embedding similarity (replaces the old logistic regression one,
# which was trained on pretty noisy labels).
#
# each intent has a few example questions + its description. a question gets embedded
# and compared to all of them, and the intent with the closest match wins. if something
# gets misrouted, add an example question instead of another if/else.
#
# the intent gives us:
#   search_terms -> better retrieval query for that topic
#   route_to     -> "rule_engine", "hybrid" or "rag"
#
#   clf = IntentClassifier(embedder)
#   clf.classify("Can I split a $120K order into two POs?")

import numpy as np

INTENT_CATEGORIES = {
    "bidding_threshold": {
        "description": "Questions about competitive bidding requirements, dollar thresholds",
        "search_terms": "competitive bidding threshold requirement dollar amount",
        "policy_domains": ["BUS-43", "CA Public Contract Code"],
        "route_to": "rule_engine",
        "examples": [
            "Do I need to go out to bid for this purchase?",
            "What dollar amount triggers a formal competitive bid?",
            "Is a $120,000 purchase required to be competitively bid?",
            "Can I buy from a certified small business without bidding?",
            "How many quotes do I need from small businesses or DVBEs?",
            "Is the bid threshold annual or per order with the same supplier?",
        ],
    },
    "sspr_form": {
        "description": "Questions about SSPR form requirements, which sections to complete",
        "search_terms": "SSPR source selection price reasonableness form",
        "policy_domains": ["SSPR Form", "Federal Funds Checklist"],
        "route_to": "rule_engine",
        "examples": [
            "When do I have to fill out the source selection and price reasonableness justification?",
            "Which sections of the SSPR do I complete for a small business purchase?",
            "Is an SSPR needed for a $20,000 order on a federal contract?",
            "What paperwork justifies price reasonableness for my requisition?",
        ],
    },
    "federal_funding": {
        "description": "Questions about federal vs non-federal rules, mixed funding, UG, FAR",
        "search_terms": "federal funds grant cooperative agreement uniform guidance FAR",
        "policy_domains": ["2 CFR 200", "FAR", "SSPR FAQ"],
        "route_to": "rule_engine",
        "examples": [
            "I'm paying part of this from my NIH grant and part from department funds - which rules apply?",
            "What changes when a purchase is paid with NSF award money?",
            "Does the Uniform Guidance apply to my grant-funded order?",
            "What is the federal micro-purchase threshold?",
            "Which flow-down clauses are required for purchases on a federal award?",
            "Do I need debarment or anti-lobbying checks for a federally funded order?",
        ],
    },
    "split_order": {
        "description": "Questions about splitting purchases to avoid bidding",
        "search_terms": "split order purchase divide artificially separated procurement",
        "policy_domains": ["BUS-43"],
        "route_to": "rule_engine",
        "examples": [
            "Can I break this order into two smaller POs so it stays under the limit?",
            "Is it okay to divide one purchase across several requisitions?",
            "We place many small orders with one vendor that add up over the year - is that a problem?",
            "Can separate project budgets be used to keep each order below the threshold?",
        ],
    },
    "sole_source": {
        "description": "Questions about sole source procurement justification",
        "search_terms": "sole source single supplier justification one-of-a-kind",
        "policy_domains": ["SSPR Form Section IV", "BUS-43"],
        "route_to": "hybrid",   # rule engine for the $ part, RAG for the justification
        "examples": [
            "Only one manufacturer makes this instrument - how do I justify buying from them?",
            "Can I skip bidding because our team prefers a specific brand?",
            "What counts as an acceptable reason to use a single supplier?",
            "How do I document an exception to competitive bidding?",
        ],
    },
    "post_employment_coi": {
        "description": "Questions about post-employment conflict of interest restrictions",
        "search_terms": "post-employment conflict interest former employee ban restriction departure",
        "policy_domains": ["Post-Employment COI Rules"],
        "route_to": "rag",
        "examples": [
            "Can a person who just retired from UC bid on a university contract?",
            "How long must a former staff member wait before contracting with UC?",
            "Our ex-employee started a consulting firm - can we hire it?",
        ],
    },
    "contracting_out": {
        "description": "Questions about contracting out services, covered services, Regents 5402",
        "search_terms": "contracting out covered services janitorial custodial security AFSCME",
        "policy_domains": ["Regents Policy 5402", "Article 5"],
        "route_to": "hybrid",
        "examples": [
            "Can we hire an outside company to do custodial work in our building?",
            "Is outsourcing food service or grounds keeping allowed?",
            "Would contracting a security guard company displace union employees?",
            "Do we have to notify the union before contracting out services?",
        ],
    },
    "equipment_tagging": {
        "description": "Questions about equipment inventory, tagging, asset management",
        "search_terms": "equipment tagging inventory asset CAAN $5000 threshold BUS-29",
        "policy_domains": ["BUS-29"],
        "route_to": "hybrid",
        "examples": [
            "Does this instrument need a property tag?",
            "What is the inventorial equipment threshold?",
            "Do donated items have to be added to the asset inventory?",
            "What happens to equipment when a grant ends or a PI leaves?",
        ],
    },
    "independent_contractor": {
        "description": "Questions about independent contractor vs employee determination",
        "search_terms": "independent contractor employee classification 1099 W-2",
        "policy_domains": ["UC Independent Contractor Guidelines"],
        "route_to": "rag",
        "examples": [
            "Should this consultant be paid as an employee or an independent contractor?",
            "How do I classify a guest lecturer we are paying?",
            "What test determines worker classification?",
        ],
    },
    "conflict_of_interest": {
        "description": "Questions about active employment COI, vendor relationships, gifts",
        "search_terms": "conflict interest vendor relationship gift gratuity relative ownership",
        "policy_domains": ["BFB-G-39 Compendium", "COI Training"],
        "route_to": "rag",
        "examples": [
            "My relative works for one of the bidders - what must I disclose?",
            "Can I accept a gift from a supplier?",
            "I own stock in a vendor - can I approve their purchase order?",
        ],
    },
    "data_security": {
        "description": "Questions about data security requirements, vendor data access",
        "search_terms": "data security appendix vendor access institutional data IS-3",
        "policy_domains": ["Appendix Data Security", "IS-3"],
        "route_to": "rag",
        "examples": [
            "The vendor will host our student records - what contract terms are needed?",
            "Do we need a business associate agreement for a vendor handling patient information?",
            "What security appendix applies when a supplier accesses UC data?",
            "Is a BAA required for de-identified health data?",
        ],
    },
    "risk_insurance": {
        "description": "Questions about insurance requirements, risk transfer",
        "search_terms": "insurance requirement risk transfer liability indemnification BUS-63",
        "policy_domains": ["BUS-63"],
        "route_to": "rag",
        "examples": [
            "How much general liability coverage must a caterer carry?",
            "Can an umbrella policy satisfy the vendor insurance requirement?",
            "What certificate of insurance do we need from a contractor?",
        ],
    },
    "general": {
        "description": "General procurement questions not matching a specific category",
        "search_terms": None,
        "policy_domains": [],
        "route_to": "rag",
        "examples": [],
    },
}

# tried a few on evaluation/benchmarks/intent_eval_set.json: 0.30 -> 84% route accuracy,
# 0.40 -> 78%, 0.50 -> 69%. (evaluation/eval_intent_classifier.py)
DEFAULT_THRESHOLD = 0.30


def _normalize(m):
    m = np.asarray(m, dtype=np.float32)
    return m / np.clip(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12, None)


class IntentClassifier:
    def __init__(self, embedder, categories=None, threshold: float = DEFAULT_THRESHOLD):
        self.embedder = embedder
        self.categories = categories or INTENT_CATEGORIES
        self.threshold = threshold

        texts, owners = [], []
        for name, cat in self.categories.items():
            if name == "general":
                continue
            texts.append(cat["description"] + " " + (cat["search_terms"] or ""))
            owners.append(name)
            for ex in cat.get("examples", []):
                texts.append(ex)
                owners.append(name)
        self._proto = _normalize(embedder.encode(texts))
        self._owners = np.array(owners)
        self._names = [n for n in self.categories if n != "general"]

    def scores(self, query: str) -> dict:
        q = _normalize(self.embedder.encode([query]))[0]
        sims = self._proto @ q
        return {name: float(sims[self._owners == name].max()) for name in self._names}

    def classify(self, query: str, threshold: float = None) -> dict:
        threshold = self.threshold if threshold is None else threshold
        scores = self.scores(query)
        best = max(scores, key=scores.get)
        best_score = scores[best]
        if best_score < threshold:
            best = "general"
        cat = self.categories[best]
        return {
            "intent": best,
            "confidence": best_score,
            "route_to": cat["route_to"],
            "search_terms": cat["search_terms"],
            "policy_domains": cat["policy_domains"],
        }
