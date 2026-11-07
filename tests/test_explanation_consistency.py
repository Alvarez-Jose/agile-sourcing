"""Run: python -m pytest tests/test_explanation_consistency.py -v"""
from evaluation.explanation_consistency import answer_section, check_explanation


def check(text, target='bid', expected=True, **kw):
    return check_explanation(text, target, expected, llm_called=True, **kw)


def test_only_answer_section_not_fixed_rule():
    text = 'Answer: No, competitive bidding is not required.\nRule: Competitive bid required: YES\nSource: policy'
    assert answer_section(text) == 'No, competitive bidding is not required.'
    assert check(text)['status'] == 'CONTRADICTION'


def test_yes_matches_bid_requirement():
    assert check('Answer: Yes, competitive bidding is required.\nRule: Competitive bid required: YES')['status'] == 'PASS'


def test_no_matches_bid_not_required():
    assert check('Answer: No, competitive bids are not required.\nRule: Competitive bid required: NO', expected=False)['status'] == 'PASS'


def test_no_matches_sspr_not_required():
    assert check('Answer: No, an SSPR form is not required.\nRule: SSPR required: NO', target='sspr', expected=False)['status'] == 'PASS'


def test_sspr_wrong_yes_is_contradiction():
    assert check('Answer: Yes, the SSPR form is required.\nRule: SSPR required: NO', target='sspr', expected=False)['status'] == 'CONTRADICTION'


def test_yes_conflicting_with_not_required_goes_to_review():
    assert check('Answer: Yes, but competitive bidding is not required.\nRule: Competitive bid required: YES')['status'] == 'REVIEW'


def test_no_leading_or_requirement_goes_to_review():
    assert check('Answer: The policy might allow several options.\nRule: Competitive bid required: YES')['status'] == 'REVIEW'


def test_rule_only_not_sufficient():
    assert check('Rule: Competitive bid required: YES')['status'] == 'REVIEW'


def test_refusal_needs_review():
    assert check('Answer: Not found in policy.', refused=True)['status'] == 'REVIEW'


def test_no_llm_is_not_run():
    assert check_explanation('Answer: No', 'bid', True, llm_called=False)['status'] == 'NOT_RUN'


def test_other_form_does_not_change_target():
    text = 'Answer: No, an SSPR form is not required, but a Federal Funds Checklist is required.\nRule: SSPR required: NO'
    assert check(text, target='sspr', expected=False)['status'] == 'PASS'


def test_unrecognized_phrasing_is_review_not_false_pass():
    assert check('Answer: The bid threshold has been met.\nRule: Competitive bid required: YES')['status'] == 'REVIEW'
