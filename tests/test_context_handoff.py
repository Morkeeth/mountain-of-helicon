import hashlib
import json
import os

import pytest

from helicon.context_handoff import HandoffError, prepare_handoff
from helicon.context_history import ContextHistory
from helicon.context_review import context_review


@pytest.fixture
def fixture(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    home.mkdir(); project.mkdir()
    source = project / 'AGENTS.md'
    source.write_bytes(b'Alpha phase = Build\r\nAlpha phase = Review\r\n')
    history = ContextHistory(tmp_path / 'state/reviews')
    saved = history.save(context_review(home, project))
    finding = saved['review']['findings'][0]
    outdir = tmp_path / 'state/handoffs'
    def prepare(**kw):
        args = dict(history_root=history.root, outdir=outdir, snapshot_id=saved['id'],
                    finding_id=finding['id'], zup_project_id='alpha')
        return prepare_handoff(**{**args, **kw})
    return prepare, source, saved, finding, history, outdir


def test_handoff_is_private_immutable_exact_origin_and_never_queues(fixture):
    prepare, source, saved, finding, history, outdir = fixture
    before = source.read_bytes()
    result = prepare()
    path = outdir / (result['sha256'] + '.json')
    assert result['status'] == 'prepared' and result['queued'] is False
    assert json.loads(path.read_bytes()) == result['payload']
    assert path.stat().st_mode & 0o077 == 0
    assert source.read_bytes() == before
    origin = result['payload']
    assert origin['snapshot']['sha256'] == hashlib.sha256((history.root / (saved['id'] + '.json')).read_bytes()).hexdigest()
    assert origin['findingID'] == finding['id']
    assert origin['evidenceRevision'] == finding['evidence_revision']
    assert {s['id'] for s in origin['sources']} == {e['source_id'] for e in finding['evidence']}
    modified = path.stat().st_mtime_ns
    assert prepare() == result
    assert path.stat().st_mtime_ns == modified


@pytest.mark.parametrize('change', ['edit', 'missing', 'fifo', 'link'])
def test_changed_or_unavailable_evidence_blocks_handoff_without_output(fixture, change):
    prepare, source, saved, finding, history, outdir = fixture
    original = source.read_bytes()
    source.unlink()
    if change == 'edit':
        source.write_text('A later human ruling')
    elif change == 'fifo':
        os.mkfifo(source)
    elif change == 'link':
        other = source.parent / 'other.md'
        other.write_bytes(original)
        source.symlink_to(other)
    with pytest.raises(HandoffError) as error:
        prepare()
    assert error.value.status == ('changed' if change == 'edit' else 'unknown')
    assert str(source) in str(error.value)
    assert not outdir.exists()


def test_wrong_identity_finding_and_private_destination_refused(fixture):
    prepare, source, saved, finding, history, outdir = fixture
    for kw in ({'finding_id': 'not-in-review'}, {'snapshot_id': '../escape'},
               {'zup_project_id': ''}, {'outdir': source.parent / 'handoffs'}):
        with pytest.raises(HandoffError):
            prepare(**kw)
    assert not outdir.exists()


def test_tampered_snapshot_and_existing_origin_refused(fixture):
    prepare, source, saved, finding, history, outdir = fixture
    result = prepare()
    path = outdir / (result['sha256'] + '.json')
    path.write_text('tampered')
    with pytest.raises(HandoffError, match='Existing handoff'):
        prepare()
    snapshot_path = history.root / (saved['id'] + '.json')
    raw = json.loads(snapshot_path.read_bytes())
    raw['review']['findings'][0]['evidence_revision'] = 'forged'
    snapshot_path.write_text(json.dumps(raw))
    with pytest.raises(HandoffError, match='pinned content'):
        prepare()


def test_resigned_bad_span_and_revision_still_refused(fixture):
    prepare, source, saved, finding, history, outdir = fixture
    for field, bad in [('quote', 'not the exact quote'), ('start_byte', 1)]:
        review = json.loads(json.dumps(saved['review']))
        review['findings'][0]['evidence'][0][field] = bad
        changed = history.save(review)
        with pytest.raises(HandoffError, match='byte span'):
            prepare(snapshot_id=changed['id'])
    review = json.loads(json.dumps(saved['review']))
    review['findings'][0]['evidence_revision'] = 'forged'
    changed = history.save(review)
    with pytest.raises(HandoffError, match='evidence revision'):
        prepare(snapshot_id=changed['id'])
