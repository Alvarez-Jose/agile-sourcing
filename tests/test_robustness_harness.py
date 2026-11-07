"""Run: python -m pytest tests/test_robustness_harness.py -q"""
from evaluation.test_robustness import extract_determination, assess, summarize


def test_structured_determination():
    result = extract_determination('THRESHOLDS:\n Competitive bid required: YES\n SSPR form required: NO')
    assert result == {'bid': True, 'sspr': False}


def test_no_structured_evidence_is_unavailable():
    assert extract_determination('Maybe competitive bidding is required')['bid'] is None


def test_conflicting_structured_evidence_is_unavailable():
    assert extract_determination('Competitive bid required: YES\nCompetitive bid required: NO')['bid'] is None


def test_assessment_flags_missing_and_wrong_fields():
    expected = dict(amount=100000, funding='non_federal', bid=True, sspr=True)
    status, reason = assess(expected, dict(amount=99999, funding='non_federal', bid=None, sspr=True))
    assert status == 'FAIL' and 'amount:expected' in reason and 'bid:unavailable' in reason


def test_summary_denominator_includes_errors():
    rows = [dict(status='PASS', kind='boundary', group='x'),
            dict(status='ERROR', kind='boundary', group='x')]
    result = summarize(rows, 'rules')
    assert result['pass_rate'] == .5 and result['errors'] == 1
