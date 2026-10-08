"""A judge abstention is not evidence that an identity fork is resolved."""
import pytest
from helicon.identity import _judge_confirm


@pytest.mark.parametrize('reply', [None, {}, {'contradicts': None}, {'contradicts': 'false'}])
def test_abstention_preserves_candidate_without_fabricated_judgment(monkeypatch, reply):
    import helicon.llm
    monkeypatch.setattr(helicon.llm, 'detect_contradictions', lambda *a, **kw: reply)
    forks = [{'name': 'sample', 'gloss_a': 'a parser', 'gloss_b': 'a database'}]
    assert _judge_confirm(forks, object(), 'test') == forks
    assert 'judge' not in forks[0]


def test_explicit_consistency_can_remove_candidate(monkeypatch):
    import helicon.llm
    monkeypatch.setattr(helicon.llm, 'detect_contradictions', lambda *a, **kw: {'contradicts': False})
    forks = [{'name': 'sample', 'gloss_a': 'a parser', 'gloss_b': 'a parser'}]
    assert _judge_confirm(forks, object(), 'test') == []
