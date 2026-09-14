import hashlib
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from helicon.context_corrections import CorrectionConflict, CorrectionError, CorrectionScopeError, CorrectionStore


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    path = root / 'AGENTS.md'
    path.write_bytes('Human prose café.\r\nStatus: old\r\nKeep my words.\r\n'.encode())
    store = CorrectionStore(tmp_path / 'state', [root])
    return store, root, path


def preview(store, path, replacement='new'):
    before = path.read_bytes()
    start = before.index(b'old')
    return store.preview(path, digest(before), start, start + 3, 'old', replacement,
                         'agent:fixture', 'Synthetic test correction', 'finding-fixture')


def test_preview_apply_history_undo_exact_bytes(setup):
    store, root, path = setup
    original = path.read_bytes()
    path.chmod(0o640)
    p = preview(store, path)
    assert path.read_bytes() == original
    assert p['status'] == 'proposed'
    assert p['before_sha256'] == digest(original)
    result = store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    assert result['status'] == 'applied'
    assert path.read_bytes() == original.replace(b'old', b'new')
    assert path.stat().st_mode & 0o777 == 0o640
    assert store.apply(p['id'], p['preview_hash'], 'local-reviewer')['status'] == 'applied'
    assert store.undo(p['id'], 'local-reviewer')['status'] == 'undone'
    assert path.read_bytes() == original
    assert [e['status'] for e in store.history(path)[0]['events']] == [
        'proposed', 'applying', 'applied', 'undoing', 'undone']
    with pytest.raises(CorrectionConflict):
        store.apply(p['id'], p['preview_hash'], 'local-reviewer')


def test_source_revision_span_and_preview_hash_are_bound(setup):
    store, _, path = setup
    p = preview(store, path)
    with pytest.raises(CorrectionConflict):
        store.apply(p['id'], 'forged-hash', 'local-reviewer')
    original = path.read_bytes()
    path.write_bytes(original + b'Later human prose')
    with pytest.raises(CorrectionConflict):
        store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    assert path.read_bytes() == original + b'Later human prose'
    with pytest.raises(CorrectionConflict):
        store.preview(path, digest(original), 0, 1, 'H', 'X', 'agent:test', 'test')
    with pytest.raises(CorrectionConflict):
        store.preview(path, digest(path.read_bytes()), 0, 1, 'wrong', 'X', 'agent:test', 'test')


def test_undo_does_not_erase_later_human_edit(setup):
    store, _, path = setup
    p = preview(store, path)
    store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    later = path.read_bytes() + b'New human decision\n'
    path.write_bytes(later)
    with pytest.raises(CorrectionConflict):
        store.undo(p['id'], 'local-reviewer')
    assert path.read_bytes() == later


def test_scope_links_and_nonregular_sources_are_rejected(setup, tmp_path):
    store, root, path = setup
    outside = tmp_path / 'outside.md'
    outside.write_text('old')
    for candidate in [outside, root / 'link.md']:
        if candidate != outside:
            candidate.symlink_to(outside)
        with pytest.raises(CorrectionScopeError):
            preview(store, candidate)
    linkdir = root / 'linked'
    linkdir.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CorrectionScopeError):
        preview(store, linkdir / 'outside.md')
    hardlink = root / 'hard.md'
    os.link(outside, hardlink)
    with pytest.raises(CorrectionScopeError):
        preview(store, hardlink)
    assert outside.read_text() == 'old'


def test_symlink_swap_after_preview_refused(setup, tmp_path):
    store, _, path = setup
    p = preview(store, path)
    outside = tmp_path / 'outside'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CorrectionScopeError):
        store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    assert b'old' in outside.read_bytes()


def test_two_previews_cannot_overwrite_each_other(setup):
    store, _, path = setup
    a, b = preview(store, path, 'first'), preview(store, path, 'second')
    def apply(p):
        try:
            return store.apply(p['id'], p['preview_hash'], 'agent:concurrency')['status']
        except CorrectionConflict:
            return 'refused'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(apply, [a, b]))
    assert sorted(outcomes) == ['applied', 'refused']


@pytest.mark.parametrize('changed', [False, True])
def test_interrupted_apply_reconciles_without_replaying(setup, monkeypatch, changed):
    store, _, path = setup
    p = preview(store, path)
    original = store._replace
    def crash(*args):
        if changed:
            original(*args)
        raise RuntimeError('Synthetic interruption')
    monkeypatch.setattr(store, '_replace', crash)
    with pytest.raises(RuntimeError):
        store.apply(p['id'], p['preview_hash'], 'agent:fixture')
    restarted = CorrectionStore(store.state_dir, store.roots)
    assert restarted.history()[0]['status'] == 'applying'
    restarted.recover(p['id'])
    history = restarted.history()
    assert history[0]['status'] == ('applied' if changed else 'proposed')
    assert history[0]['events'][-1]['actor'] == 'service:recovery'
    assert (b'new' in path.read_bytes()) == changed


def test_recovery_conflict_never_writes_source(setup):
    store, _, path = setup
    p = preview(store, path)
    store._transition(p['id'], 'applying', 'agent:fixture')
    path.write_text('Independent later human content')
    assert store.recover(p['id'])['status'] == 'conflict'
    assert path.read_text() == 'Independent later human content'


def test_history_does_not_expose_other_root(setup, tmp_path):
    store, _, path = setup
    preview(store, path)
    other = tmp_path / 'other'
    other.mkdir()
    assert CorrectionStore(store.state_dir, [other]).history() == []


@pytest.mark.parametrize('start,end,text', [(True, 1, 'H'), (-1, 1, 'H'), (0, 999, 'H')])
def test_invalid_spans(setup, start, end, text):
    store, _, path = setup
    with pytest.raises(CorrectionError):
        store.preview(path, digest(path.read_bytes()), start, end, text, 'X', 'agent:test', 'test')


def test_noop_and_missing_actor_rejected(setup):
    store, _, path = setup
    with pytest.raises(CorrectionError):
        preview(store, path, 'old')
    p = preview(store, path)
    with pytest.raises(CorrectionError):
        store.apply(p['id'], p['preview_hash'], '')


def test_constructor_and_history_are_read_only(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    state = tmp_path / 'missing-state'
    store = CorrectionStore(state, [root])
    assert store.history() == []
    assert not state.exists()


def test_preview_can_delete_only_reviewed_line_preserving_crlf(setup):
    store, _, path = setup
    original = path.read_bytes()
    span = b'Status: old\r\n'
    start = original.index(span)
    p = store.preview(path, digest(original), start, start + len(span), span.decode(), '',
                      'local-reviewer', 'Retire obsolete instruction')
    store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    assert path.read_bytes() == original.replace(span, b'')
    store.undo(p['id'], 'local-reviewer')
    assert path.read_bytes() == original


def test_concurrent_human_edit_inside_write_window_is_refused(setup, monkeypatch):
    store, _, path = setup
    p = preview(store, path)
    original_replace = store._replace
    human = b'A new human revision\n'
    def change_before_replace(*args):
        path.write_bytes(human)
        return original_replace(*args)
    monkeypatch.setattr(store, '_replace', change_before_replace)
    with pytest.raises(CorrectionConflict):
        store.apply(p['id'], p['preview_hash'], 'agent:fixture')
    assert path.read_bytes() == human
    assert not list(path.parent.glob('.helicon-correction-*'))
    assert store.recover(p['id'])['status'] == 'conflict'


@pytest.mark.parametrize('changed', [False, True])
def test_interrupted_undo_recovery(setup, monkeypatch, changed):
    store, _, path = setup
    p = preview(store, path)
    store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    original = store._replace
    def crash(*args):
        if changed:
            original(*args)
        raise RuntimeError('Synthetic interruption')
    monkeypatch.setattr(store, '_replace', crash)
    with pytest.raises(RuntimeError):
        store.undo(p['id'], 'local-reviewer')
    assert store.history()[0]['status'] == 'undoing'
    assert store.recover(p['id'])['status'] == ('undone' if changed else 'applied')
    assert (b'old' in path.read_bytes()) == changed


def test_scoped_store_cannot_apply_or_undo_other_project(setup, tmp_path):
    store, _, path = setup
    p = preview(store, path)
    root = tmp_path / 'other'
    root.mkdir()
    restricted = CorrectionStore(store.state_dir, [root])
    with pytest.raises(CorrectionScopeError):
        restricted.apply(p['id'], p['preview_hash'], 'local-reviewer')
    store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    with pytest.raises(CorrectionScopeError):
        restricted.undo(p['id'], 'local-reviewer')


def test_read_only_history_does_not_change_existing_store(setup):
    store, _, path = setup
    preview(store, path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in store.state_dir.iterdir()}
    assert len(store.history(path)) == 1
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in store.state_dir.iterdir()}
    assert before == after


def test_binary_file_and_directory_are_refused(setup):
    store, root, path = setup
    path.write_bytes(b'old\x00')
    with pytest.raises(CorrectionError):
        preview(store, path)
    (root / 'directory').mkdir()
    with pytest.raises(CorrectionScopeError):
        store.preview(root / 'directory', digest(b''), 0, 0, '', 'new', 'agent:test', 'test')


def test_duplicate_text_changes_only_selected_occurrence(setup):
    store, _, path = setup
    original = b'old\nold\nold\n'
    path.write_bytes(original)
    p = store.preview(path, digest(original), 4, 7, 'old', 'new', 'agent:test', 'test')
    store.apply(p['id'], p['preview_hash'], 'local-reviewer')
    assert path.read_bytes() == b'old\nnew\nold\n'


def test_configured_root_ancestor_link_swap_is_refused(tmp_path):
    container = tmp_path / 'container'
    root = container / 'project'
    root.mkdir(parents=True)
    path = root / 'AGENTS.md'
    path.write_text('old')
    store = CorrectionStore(tmp_path / 'state', [root])
    p = preview(store, path)
    moved = tmp_path / 'moved'
    container.rename(moved)
    container.symlink_to(moved, target_is_directory=True)
    with pytest.raises(CorrectionScopeError):
        store.apply(p['id'], p['preview_hash'], 'agent:test')
    assert (moved / 'project' / 'AGENTS.md').read_text() == 'old'


def test_disconnected_project_history_remains_readable_but_apply_refuses(setup, tmp_path):
    store, root, path = setup
    p = preview(store, path)
    root.rename(tmp_path / 'disconnected-project')
    restarted = CorrectionStore(store.state_dir, [root])
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in store.state_dir.iterdir()}
    assert restarted.history()[0]['id'] == p['id']
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in store.state_dir.iterdir()}
    assert before == after
    with pytest.raises(CorrectionScopeError):
        restarted.apply(p['id'], p['preview_hash'], 'local-reviewer')
    assert not root.exists()


def test_missing_root_empty_history_does_not_create_source_or_state(tmp_path):
    root, state = tmp_path / 'missing-project', tmp_path / 'missing-state'
    assert CorrectionStore(state, [root]).history() == []
    assert not root.exists()
    assert not state.exists()
