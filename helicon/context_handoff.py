"""Prepare an explicit private ZUP origin reference; never queue or send work.

The caller resolves the canonical ZUP project ID. This service pins a reviewed
finding and rechecks its cited files, not the finding's truth or current probes.
The origin contains local private paths and must not be published.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .context_history import HistoryError, SCHEMA, _bytes, _validate, read_source_bytes


class HandoffError(ValueError):
    def __init__(self, status, reason):
        self.status = status
        super().__init__(f"{status}: {reason}")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    try:
        return read_source_bytes(path)
    except HistoryError as exc:
        raise HandoffError('unknown', f'Source unavailable or unsafe: {path}: {exc}') from exc


def prepare_handoff(history_root, outdir, snapshot_id, finding_id, zup_project_id):
    """Return {path, payload, sha256, status, queued}; write only the origin file.

    sources is exactly the distinct source set cited by the selected finding,
    not unrelated check populations. No title, task, or new decision is invented.
    """
    if not isinstance(snapshot_id, str) or not re.fullmatch(r'[0-9a-f]{64}', snapshot_id):
        raise HandoffError('invalid', 'Invalid snapshot ID')
    if not isinstance(finding_id, str) or not finding_id:
        raise HandoffError('invalid', 'An exact finding ID is required')
    if (not isinstance(zup_project_id, str) or not zup_project_id.strip()
            or zup_project_id != zup_project_id.strip() or len(zup_project_id) > 200
            or any(ord(c) < 32 for c in zup_project_id)):
        raise HandoffError('invalid', 'An explicit canonical ZUP project ID is required')
    snapshot_path = Path(history_root).expanduser().absolute() / f'{snapshot_id}.json'
    raw = _read(snapshot_path)
    try:
        saved = json.loads(raw)
        payload = {k: v for k, v in saved.items() if k not in ('id', 'sha256')}
        if (saved.get('id') != snapshot_id or saved.get('sha256') != snapshot_id
                or saved.get('schema') != SCHEMA or _sha(_bytes(payload)) != snapshot_id):
            raise HandoffError('invalid', 'Snapshot does not match its pinned content ID')
        review = saved['review']
        _validate(review)
        finding = next((f for f in review['findings'] if f['id'] == finding_id), None)
        if finding is None:
            raise HandoffError('invalid', 'Finding does not belong to this snapshot')
        evidence = finding.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise HandoffError('invalid', 'Finding has no exact source evidence')
        spans = set()
        sources = {}
        current = {}
        for span in evidence:
            sid, path, sha = span['source_id'], span['path'], span['sha256']
            if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
                raise HandoffError('unknown', f'Cited source has no verified revision: {path}')
            if path not in current:
                current[path] = _read(path)
            data = current[path]
            if _sha(data) != sha:
                raise HandoffError('changed', f'Cited source changed since review: {path}')
            start, end, quote = span['start_byte'], span['end_byte'], span['quote']
            if (type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(data)
                    or not isinstance(quote, str) or data[start:end] != quote.encode('utf-8')):
                raise HandoffError('invalid', f'Reviewed quote does not match its exact byte span: {path}')
            spans.add((path, sha, start, end))
            sources[sid] = dict(id=sid, path=path, sha256=sha)
        revision = _sha(json.dumps([sorted(spans)], ensure_ascii=False).encode())[:24]
        if finding.get('evidence_revision') != revision:
            raise HandoffError('invalid', 'Finding evidence revision does not match its pinned spans')
        workspace = review['project']
        if not isinstance(workspace, str) or not Path(workspace).is_absolute():
            raise HandoffError('invalid', 'Snapshot project must be an absolute workspace')
    except (HistoryError, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffError('invalid', f'Invalid saved evidence: {exc}') from exc

    origin = dict(schema='zup.helicon-origin/1', findingID=finding_id, snapshotID=snapshot_id,
                  evidenceRevision=revision, project=dict(id=zup_project_id, workspace=workspace),
                  snapshot=dict(path=str(snapshot_path), sha256=_sha(raw)),
                  sources=sorted(sources.values(), key=lambda s: s['id']))
    encoded = _bytes(origin)
    identity = _sha(encoded)
    directory = Path(outdir).expanduser().absolute()
    if directory != directory.resolve():
        raise HandoffError('invalid', 'Handoff output directory must not traverse a symlink')
    if (directory == Path(workspace) or Path(workspace) in directory.parents
            or any((p / '.git').exists() for p in (directory, *directory.parents))):
        raise HandoffError('invalid', 'Keep private handoffs in project state, outside source repositories')
    # Recheck immediately before publication. External uncooperative file changes
    # after this check remain possible; ZUP must validate again when consuming.
    if _read(snapshot_path) != raw:
        raise HandoffError('changed', 'Saved snapshot bytes changed during handoff preparation')
    for path, expected in current.items():
        if _read(path) != expected:
            raise HandoffError('changed', f'Cited source changed during handoff preparation: {path}')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / f'{identity}.json'
    fd, temporary = tempfile.mkstemp(prefix='.origin-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if _read(destination) != encoded:
                raise HandoffError('invalid', 'Existing handoff file differs from its pinned content')
    finally:
        os.unlink(temporary)
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return dict(path=str(destination), payload=origin, sha256=identity, status='prepared', queued=False)
