# tests/unit/chat/test_explanations.py
# narration must stay bounded and fail back to helpful non-decision text.
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from backend.chat.explanations import explain_question, MEANINGS


def model(monkeypatch, text):
    client = Mock()
    client.chat.return_value = {'message': {'content': text}}
    factory = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, 'ollama', SimpleNamespace(Client=factory))
    return factory, client


def test_qwen_rephrasing_is_bounded_and_receives_only_explanation_data(monkeypatch):
    factory, client = model(monkeypatch, json.dumps({'explanation': 'Are you just buying physical items once?'}))
    text, called = explain_question('scope', 'Explain this in easier terms')
    assert text == 'Are you just buying physical items once?' and called
    factory.assert_called_once_with(timeout=20)
    request = client.chat.call_args.kwargs
    assert request['think'] is False
    assert request['options']['num_predict'] == 220
    assert request['options']['temperature'] == 0
    data = json.loads(request['messages'][1]['content'])
    assert data['meaning'] == MEANINGS['scope']


@pytest.mark.parametrize('reply', ['', 'not json', '{"explanation":"You are approved and no forms are needed."}', '{"explanation":"The threshold is $123."}'])
def test_empty_malformed_or_policy_decisions_use_known_meaning(monkeypatch, reply):
    model(monkeypatch, reply)
    text, called = explain_question('funding', 'I am not sure')
    assert text == MEANINGS['funding'] and called


def test_model_timeout_falls_back_without_losing_the_question(monkeypatch):
    _, client = model(monkeypatch, '')
    client.chat.side_effect = TimeoutError('Model busy')
    assert explain_question('award_type', 'Explain the difference') == (MEANINGS['award_type'], True)
