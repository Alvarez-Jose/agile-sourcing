# tests/unit/chat/test_conversation.py
# conversation rewrites retain uncertainty, quantities and source references.
import json
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest
from backend.chat import conversation
from backend.chat.forms import form_links
from rules.provenance import DOCUMENTS


@pytest.mark.parametrize('message,mode', [
    ('Can you make that easier to understand?', 'simple'),
    ('Explain that in plain English', 'simple'), ('Sum it up', 'summary'),
    ('Give me the full answer', 'detail'), ('Hi!', 'greeting'),
    ('Summarize my cart', None), ('Summarize the SSPR form', None),
])
def test_followups_and_new_topics_are_distinguished(message, mode):
    assert conversation.conversation_mode(message) == mode


@pytest.mark.parametrize('text', [
    'The amount is $999. Shipping is unknown, not zero. Guidance is provisional [1].',
    'The amount is $100. All charges are confirmed [1].',
    'The amount is $100. Shipping is unknown, not zero. Guidance is provisional [2].',
    'The amount is $100. Shipping is unknown, not zero. Guidance is provisional [1]. Submit an RFQ.',
    'The amount is $100. Shipping is unknown, not zero. Guidance is provisional [1]. https://evil.example',
])
def test_unsafe_or_unfaithful_rewrites_are_rejected(text):
    original = 'Known amount $100. Shipping is unknown, not zero. This is provisional [1].'
    assert not conversation.faithful_rewrite(original, text)


def test_safe_rewrite_keeps_numbers_citations_and_caveats():
    assert conversation.faithful_rewrite('Known amount $100. Charges unknown, not zero; provisional [1].',
        'The known amount is $100. Charges are unknown, not zero. This is provisional [1].')


def test_narration_uses_local_bounded_call_and_falls_back_on_changed_amount(monkeypatch):
    original = 'The known amount is $100. It is provisional [1].'
    client = Mock()
    client.chat.return_value = {'message': {'content': json.dumps({'answer': 'The amount is $200 [1].'})}}
    factory = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, 'ollama', SimpleNamespace(Client=factory))
    assert conversation.rewrite_answer(original, 'simple') == (original, True)
    factory.assert_called_once_with(timeout=20)
    assert client.chat.call_args.kwargs['options']['num_predict'] == 600
    assert client.chat.call_args.kwargs['think'] is False


def test_model_failure_retains_original_answer(monkeypatch):
    client = Mock();client.chat.side_effect = TimeoutError()
    monkeypatch.setitem(sys.modules, 'ollama', SimpleNamespace(Client=lambda **_: client))
    assert conversation.rewrite_answer('Original answer', 'summary') == ('Original answer', True)


def test_only_forms_with_existing_official_urls_are_linked():
    links = form_links('Use the SSPR form and Federal Funds Checklist.')
    assert len(links) == 1
    assert links[0]['url'] == DOCUMENTS['sspr-form']['url']
    assert form_links('The SSPR FAQ explains the background.') == []
    assert form_links('The unrelated XSSPR form has a name.') == []


def test_unknown_url_is_not_accepted_from_answer_text():
    links = form_links('[SSPR](https://evil.example/form)')
    assert links[0]['url'] == DOCUMENTS['sspr-form']['url']
    assert all('evil.example' not in link['url'] for link in links)
