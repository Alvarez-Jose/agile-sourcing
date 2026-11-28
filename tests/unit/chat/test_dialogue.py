# tests/unit/chat/test_dialogue.py
# Interpretations require explicit current-turn evidence before changing cart facts.
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.chat import dialogue, coordinator
from backend.chat.models import ChatContext
from evaluation.benchmarks.run_chat_conversations import check_response, replay
from tests.integration.test_chat_context import context


@pytest.mark.parametrize('question,plan,canonical', [
    ('this is a one time purchase', {'action': 'confirm_scope', 'scope': True, 'evidence': 'one time purchase'}, 'Yes, separate purchases'),
    ('I wrote the funding wrong. I have non federal funds.', {'action': 'set_funding', 'funding': 'non_federal', 'evidence': 'non federal funds'}, 'Non-federal funds'),
    ('0, no charge', {'action': 'set_charge', 'field': 'handling', 'amount': '0', 'evidence': '0, no charge'}, 'handling is 0'),
    ('There is no shipping charge', {'action': 'set_charge', 'field': 'shipping', 'amount': '0', 'evidence': 'no shipping charge'}, 'shipping is 0'),
    ('explain these steps in easy words', {'action': 'simplify', 'evidence': ''}, 'Explain that in simpler terms'),
    ('What do I need to fill out?', {'action': 'purchase_requirements', 'evidence': ''}, 'What forms do I need for my cart?'),
])
def test_supported_turns(question, plan, canonical):
    state = ChatContext.model_validate(context())
    state.awaiting_kind, state.awaiting_field = 'charges', 'handling'
    assert dialogue.validate_plan(dialogue.TurnPlan(**plan), question, state) == canonical


@pytest.mark.parametrize('question,plan', [
    ('maybe federal funds', {'action': 'set_funding', 'funding': 'federal', 'evidence': 'federal funds'}),
    ('I am not using federal funds', {'action': 'set_funding', 'funding': 'federal', 'evidence': 'federal funds'}),
    ('non federal funds', {'action': 'set_funding', 'funding': 'federal', 'evidence': 'non federal funds'}),
    ('research grant', {'action': 'set_funding', 'funding': 'federal_grant', 'evidence': 'research grant'}),
    ('non federal grant', {'action': 'set_funding', 'funding': 'federal_grant', 'evidence': 'non federal grant'}),
    ('I am not on federal funds', {'action': 'set_funding', 'funding': 'federal', 'evidence': 'federal funds'}),
    ('What are federal funds?', {'action': 'set_funding', 'funding': 'federal', 'evidence': 'federal funds'}),
    ('Pretend I have federal funds', {'action': 'set_funding', 'funding': 'federal', 'evidence': 'federal funds'}),
    ('handling is 20', {'action': 'set_charge', 'field': 'handling', 'amount': '200', 'evidence': 'handling is 20'}),
    ('hello', {'action': 'confirm_scope', 'scope': False, 'evidence': 'hello'}),
    ('yes but this includes services', {'action': 'confirm_scope', 'scope': True, 'evidence': 'yes'}),
])
def test_unsupported_facts_are_rejected(question, plan):
    with pytest.raises(ValueError):
        dialogue.validate_plan(dialogue.TurnPlan(**plan), question, ChatContext.model_validate(context()))


def test_model_call_is_bounded_and_rejected_facts_do_not_reach_rag(monkeypatch):
    client = Mock()
    client.chat.return_value = {'message': {'content': json.dumps({'action': 'set_funding', 'funding': 'federal', 'evidence': 'federal funds'})}}
    factory = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, 'ollama', SimpleNamespace(Client=factory))
    monkeypatch.setenv('CHAT_MODEL_CONVERSATION', '1')
    ask = Mock()
    result = coordinator.answer_chat('maybe federal funds', ChatContext.model_validate(context()), [], ask)
    ask.assert_not_called()
    assert result['dialogue']['rejected_fact']
    assert result['chat_context']['suppliers'][0]['funding'] == 'non_federal'
    factory.assert_called_once_with(timeout=25)
    assert client.chat.call_args.kwargs['options']['num_predict'] == 500
    assert client.chat.call_args.kwargs['think'] is False


def test_natural_scope_advances_existing_workflow(monkeypatch):
    state = ChatContext.model_validate(context(ready=False))
    state.independent_purchases = False
    state.awaiting_kind = 'scope'
    state.pending_question = 'What forms do I need for my cart?'
    trace = {'attempted': True, 'accepted': True, 'action': 'confirm_scope'}
    monkeypatch.setenv('CHAT_MODEL_CONVERSATION', '1')
    monkeypatch.setattr(dialogue, 'interpret_turn', lambda q, c, h: ('Yes, separate purchases', c, trace))
    result = coordinator.answer_chat('this is a one time purchase', state, [], Mock())
    assert result['follow_up']['kind'] == 'funding'
    assert result['chat_context']['independent_purchases']


def test_missed_statement_does_not_fall_through_to_general_rag(monkeypatch):
    state = ChatContext.model_validate(context())
    monkeypatch.setenv('CHAT_MODEL_CONVERSATION', '1')
    monkeypatch.setattr(dialogue, 'interpret_turn', lambda q, c, h: (q, c, {'accepted': True, 'action': 'unchanged'}))
    ask = Mock()
    result = coordinator.answer_chat('There is no shipping charge', state, [], ask)
    ask.assert_not_called()
    assert 'confidently interpret' in result['answer']


def test_cart_summary_reads_captured_facts_without_model_interpretation(monkeypatch):
    monkeypatch.setenv('CHAT_MODEL_CONVERSATION', '1')
    interpreter = Mock(side_effect=AssertionError('A cart read needs no interpretation'))
    monkeypatch.setattr(dialogue, 'interpret_turn', interpreter)
    result = coordinator.answer_chat('What is in my cart right now?', ChatContext.model_validate(context()), [], Mock())
    assert 'Supplier A' in result['answer']
    assert result['dialogue']['route'] == 'captured_cart'


@pytest.mark.parametrize('multiple,accepted', [(False, True), (True, False)])
def test_unnamed_supplier_can_only_be_inferred_for_a_single_supplier(monkeypatch, multiple, accepted):
    client = Mock()
    client.chat.return_value = {'message': {'content': json.dumps({
        'action': 'set_charge', 'field': 'handling', 'amount': '200',
        'evidence': 'Handling is 200', 'supplier': 'Supplier A'})}}
    monkeypatch.setitem(sys.modules, 'ollama', SimpleNamespace(Client=Mock(return_value=client)))
    _, _, trace = dialogue.interpret_turn('Handling is 200', ChatContext.model_validate(context(multiple=multiple)), [])
    assert trace['accepted'] is accepted


def test_replay_records_errors_and_checkpoints(tmp_path):
    client = Mock()
    client.post.side_effect = RuntimeError('offline')
    dataset = {'cart': context()['cart'], 'scenarios': [{'id': 'offline', 'turns': [{'question': 'hello'}]}]}
    summary = replay(client, dataset, tmp_path)
    assert summary['errors'] == 1
    report = json.loads((tmp_path / 'conversations.json').read_text())
    assert report['conversations'][0]['turns'][0]['error'] == 'offline'
    assert (tmp_path / 'summary.json').exists()


def test_charge_assertions_compare_decimal_values():
    checks = check_response({'chat_context': {'suppliers': [{'handling': '0.00'}]}}, {'handling': '0'})
    assert checks[0]['passed']
