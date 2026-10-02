import hashlib
import pytest
from helicon.calendar_check import check_weekday_item
from helicon.context_review import context_review


@pytest.mark.parametrize('text', [
    'Deadline: Sunday April 27, 2026',
    'Deadline: Sunday, 27 April 2026',
    'Deadline: Sunday 2026-04-27',
    'Deadline: 2026-04-27 falls on Sunday',
    'Deadline: SunDAY 27th Apr. 2026',
])
def test_explicit_wrong_weekday(text):
    result = check_weekday_item(text)
    assert result['verdict'] == 'contradicted'
    assert result['date'] == '2026-04-27'
    assert result['calculated_weekday'] == 'Monday'
    assert result['claimed_weekday'] == 'Sunday'


@pytest.mark.parametrize('text', [
    'Monday April 27, 2026', 'Thursday February 29, 2024',
    'Saturday 2000-01-01', 'Monday January 1, 1900',
])
def test_known_calendar_controls(text):
    assert check_weekday_item(text)['verdict'] == 'upheld'


@pytest.mark.parametrize('text', [
    'Sunday April 27', 'Sunday 04/27/2026', 'Every Sunday April 27, 2026',
    'Next Sunday April 27, 2026', 'Before Sunday April 27, 2026',
    'Sunday or Monday April 27, 2026', 'Sunday April 27, 2026 and May 1, 2026',
    'Sunday April 27, 2026 and May 1', 'Sunday February 29, 2026',
    'Not Sunday April 27, 2026', 'Example: Sunday April 27, 2026',
    'The report says "Sunday April 27, 2026"', 'Sunday\nApril 27, 2026',
    'Monday meeting. Deadline April 27, 2026', 'Sunday review, release April 27, 2026',
    'If Sunday April 27, 2026 is chosen', 'Sunday April 27, 2026 might be wrong',
    'Sonntag 2026-04-27', 'April 27, 2026', 'Sunday',
])
def test_ambiguity_is_unchecked_not_upheld(text):
    assert check_weekday_item(text) is None


def project(tmp_path, text):
    home, repo = tmp_path / 'home', tmp_path / 'project'
    home.mkdir(); repo.mkdir(); (repo / '.git').mkdir()
    source = repo / 'AGENTS.md'; source.write_bytes(text.encode())
    return home, repo, source


def test_one_source_item_exact_bytes_no_neighbour_pairing_and_rerun(tmp_path):
    text = 'Résumé\r\nDeadline: Sunday April 27, 2026\r\nOther event: Monday May 4, 2026\r\n'
    home, repo, source = project(tmp_path, text)
    original = source.read_bytes()
    report = context_review(home, repo)
    assert source.read_bytes() == original
    assert len(report['findings']) == 1
    finding = report['findings'][0]
    assert finding['kind'] == 'calendar-weekday'
    assert len(finding['evidence']) == 1
    ev = finding['evidence'][0]
    assert ev['line_start'] == 2
    assert original[ev['start_byte']:ev['end_byte']].decode() == ev['quote']
    assert ev['sha256'] == hashlib.sha256(original).hexdigest()
    assert finding['probe']['command'] is None
    assert finding['probe']['output']['calculated_weekday'] == 'Monday'
    assert 'intended is not known' in finding['consequence']
    assert finding['harnesses'] == ['codex', 'cursor']  # one issue, candidate routes retained
    source.write_bytes(original.replace(b'Sunday April', b'Monday April'))
    assert context_review(home, repo)['findings'] == []


def test_existing_review_excludes_history_quotes_examples_and_conditions(tmp_path):
    home, repo, _ = project(tmp_path, '> Sunday April 27, 2026\n```\nSunday April 27, 2026\n```\n## History\nSunday April 27, 2026\n## Current\nIf Sunday April 27, 2026\n')
    assert not context_review(home, repo)['findings']


def test_date_finding_uses_existing_local_review_correction_and_history(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from helicon.api import context_review as api
    home, repo, source = project(tmp_path, 'Deadline: Sunday April 27, 2026\n')
    state = tmp_path / 'state'
    monkeypatch.setattr(api, 'get_config', lambda: {'context_review': {'home': str(home), 'projects': [{'id': 'sample', 'path': str(repo)}]}})
    monkeypatch.setattr(api, 'helicon_home', lambda: str(state))
    app = FastAPI(); app.include_router(api.router, prefix='/api')
    client = TestClient(app, base_url='http://127.0.0.1:8420')
    def post(action, **fields):
        response = client.post('/api/context-review/' + action, json={'project_id': 'sample', **fields}, headers={'X-Helicon-Local': '1'})
        assert response.status_code == 200, response.text
        return response.json()
    read = post('read')
    assert not state.exists(), 'Read must not write a review or memory'
    finding = read['report']['findings'][0]
    saved = post('snapshots', revision=read['revision'])
    preview = post('preview', snapshot_id=saved['id'], finding_id=finding['id'], evidence_index=0,
                   replacement='Deadline: Monday April 27, 2026\n', reason='Synthetic test correction only')
    assert 'Sunday' in source.read_text(), 'Preview cannot change source'
    applied = post('apply', preview_id=preview['id'], preview_hash=preview['hash'])
    assert not post('read')['report']['findings']
    comparison = post('compare', baseline_id=saved['id'])
    assert next(g for g in comparison['groups'] if g['label'] == 'Resolved by the checks run')['items']
    post('undo', correction_id=applied['correction_id'])
    assert len(post('read')['report']['findings']) == 1


def test_changed_calendar_source_invalidates_finding(monkeypatch, tmp_path):
    import helicon.context_review as module
    home, repo, source = project(tmp_path, 'Deadline: Sunday April 27, 2026\n')
    original, calls = module._read, 0
    def moving(path):
        nonlocal calls
        if path == source:
            calls += 1
            if calls >= 3:
                source.write_text('Deadline: Monday April 27, 2026\n')
        return original(path)
    monkeypatch.setattr(module, '_read', moving)
    report = context_review(home, repo)
    assert not report['findings']
    assert any(s['status'] == 'changed' for s in report['sources'])


def test_ambiguous_rewrite_is_unchecked_not_resolved_in_history(monkeypatch, tmp_path):
    from helicon.context_history import ContextHistory
    home, repo, source = project(tmp_path, 'Deadline: Sunday April 27, 2026\n')
    history = ContextHistory(tmp_path / 'reviews')
    before = context_review(home, repo)
    saved = history.save(before)
    source.write_text('Deadline: Sunday April 27\n')
    after = context_review(home, repo)
    assert not after['findings']  # No invented contradiction for a yearless date.
    calendar = [c for c in after['claims'] if c['predicate'] == 'calendar-weekday']
    assert calendar and all(c['probe']['verdict'] == 'unknown' for c in calendar)
    assert all(c['status'] == 'unknown' for c in after['coverage']['checks'] if c['id'] in before['findings'][0]['check_ids'])
    comparison = history.compare(saved['id'], after)
    assert not comparison['resolved']
    assert len(comparison['unchecked']) == 1
