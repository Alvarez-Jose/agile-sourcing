# Rule engine for the procurement questions where we can't afford the LLM guessing
# (bid thresholds, SSPR, federal funding, covered services, equipment tagging).
# Everything in here is plain if/else logic taken straight from the policy docs.

from rules.engine import EvaluationResult, RuleEngine, should_use_rule_engine
from rules.models import EquipmentItem, PurchaseRequest
from rules.query_parser import parse_query

__all__ = ["RuleEngine", "EvaluationResult", "PurchaseRequest", "EquipmentItem",
           "should_use_rule_engine", "parse_query"]
