# run with: python -m pytest rules/test_answer_format.py -v

from rules import PurchaseRequest, RuleEngine
from rules.answer_format import format_rule_answer, split_llm_sections

engine = RuleEngine()


def ev(**kw):
    return engine.evaluate(PurchaseRequest(**kw))


def test_fixed_format_has_four_parts_in_order():
    out = format_rule_answer(ev(amount=185_000, source_selection="small_business"),
                             "Answer: Yes, no formal bid is needed [1].\nConditions: Get 2 quotes [2].")
    lines = out.split("\n")
    assert [line.split(":")[0] for line in lines] == ["Answer", "Rule", "Source", "Conditions"]
    assert lines[0] == "Answer: Yes, no formal bid is needed [1]."
    assert lines[3] == "Conditions: Get 2 quotes [2]."


def test_rule_and_source_come_from_engine_not_llm():
    llm = "Answer: No.\nRule: the bid threshold is $50,000\nSource: made up\nConditions: None"
    out = format_rule_answer(ev(amount=150_000), llm)
    assert "$50,000" not in out and "made up" not in out
    assert "threshold $100,000" in out
    assert 'p.9' in out and "$100,000 or more" in out          # BUS-43 interim, quoted


def test_unformatted_llm_reply_still_produces_format():
    answer, conditions = split_llm_sections("Yes, you can use a small business.")
    assert answer == "Yes, you can use a small business." and conditions == "None"
    out = format_rule_answer(ev(amount=185_000, source_selection="small_business"), "")
    assert out.startswith("Answer: Competitive bid required: NO")


def test_split_prohibition_leads_the_rule_line():
    h = ev(amount=35_000, related_orders=[25_000], split_intent=True).to_answer_header()
    assert h.index("prohibited") < h.index("Competitive bid required")
