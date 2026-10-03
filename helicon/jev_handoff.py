"""Explicit local comparison return to an existing ZUP profile/task."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import uuid
from datetime import datetime
from .selected_jev import recorded, digest


def local_file(value):
    p = Path(value).expanduser().resolve(strict=True)
    if not p.is_relative_to(Path.home().resolve()) or not p.is_file():
        raise ValueError('Choose an existing local file inside your home directory.')
    return p


def rows(profile):
    home = Path(profile).expanduser().resolve(strict=True)
    if not home.is_relative_to(Path.home().resolve()) or not home.is_dir():
        raise ValueError('Choose an existing ZUP profile inside your home directory.')
    log = local_file(home / 'zup-ledger.jsonl')
    if log.parent != home or log.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Profile log must be bounded and directly inside the profile.')
    result = []
    for line in log.read_text().splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('Invalid profile log record.')
            result.append(value)
    return home, log, result


def tasks(profile):
    home, _, records = rows(profile)
    board = local_file(home / 'active-board.json')
    if board.parent != home or board.stat().st_size > 1024 * 1024:
        raise ValueError('Profile requires its existing bounded active board.')
    projects = json.loads(board.read_text()).get('projects', [])
    aliases = {}
    for project in projects:
        if not isinstance(project, dict) or not isinstance(project.get('id'), str):
            raise ValueError('Invalid active project definition.')
        for name in [project['id'], project.get('title', ''), *project.get('aliases', [])]:
            if isinstance(name, str) and name.strip():
                aliases[name.strip().lower()] = project['id']
    latest = {}
    retired = {r["supersedes"] for r in records if isinstance(r.get("supersedes"), str)}
    for r in sorted(records, key=lambda row: row.get('at', '')):
        if isinstance(r.get('id'), str):
            latest[r['id']] = {**latest.get(r['id'], {}), **r}
    return [{'id': r['id'], 'project': aliases[r['project'].strip().lower()], 'text': r['text']} for r in latest.values()
            if isinstance(r.get('id'), str) and isinstance(r.get('project'), str)
            and r['project'].strip().lower() in aliases
            and isinstance(r.get('text'), str) and len(r['text']) <= 4000 and len(r['id']) <= 256
            and r.get('kind') in ('dispatch', 'request', 'conclusion')
            and not r.get('re') and not r.get('doneAt') and r['id'] not in retired][-200:]


def prepare(db, item, against, receipt, profile, task_id, prepared_at):
    # datetime.fromisoformat learned the ISO UTC Z suffix in Python 3.11.
    # Browsers send Z; preserve those exact preview bytes while parsing an
    # equivalent offset on every supported Python (including 3.10).
    iso_time = prepared_at[:-1] + '+00:00' if prepared_at.endswith('Z') else prepared_at
    timestamp = datetime.fromisoformat(iso_time)
    if timestamp.tzinfo is None:
        raise ValueError('Preview requires an explicit timestamp with timezone.')
    home, log, _ = rows(profile)
    target = next((r for r in tasks(profile) if r['id'] == task_id), None)
    if target is None:
        raise ValueError('Choose an existing active task from this profile.')
    original = local_file(receipt)
    dbpath = local_file(db)
    if original.stat().st_size > 32000:
        raise ValueError('Comparison receipt is too large.')
    raw = original.read_bytes()
    observation = recorded(dbpath, item, against, original)
    if not observation['source_matches']:
        raise ValueError('Selected comparison sources changed. No handoff is allowed.')
    content = {'schema': 'zup.helicon-comparison/1', 'database': str(dbpath),
               'receipt': str(original), 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
               'observation': observation}
    payload = json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    snapshot_hash = hashlib.sha256(payload.encode()).hexdigest()
    identity = digest({'snapshot': snapshot_hash, 'task': target, 'profile': str(home), 'at': prepared_at})
    identifier = str(uuid.UUID(identity[:32]))
    artifact = home / 'review-sources' / ('helicon-' + identifier + '.json')
    record = {'id': identifier, 'at': prepared_at, 'kind': 'conclusion', 'by': 'agent',
              'project': target['project'], 're': target['id'],
              'text': 'Helicon comparison returned for review: ' + target['text'],
              'artifact': str(artifact), 'reviewSources': [{'kind': 'comparison', 'artifact': str(artifact),
              'sha256': snapshot_hash, 'observedAt': prepared_at, 'originalArtifact': str(original),
              'originalSHA256': content['receipt_sha256']}]}
    plan = {'profile': str(home), 'log': str(log), 'task': target, 'record': record,
            'snapshot': content, 'snapshot_bytes': payload,
            'limit': 'Local metadata/reference handoff only. Pair probability is not done-claim support or a human verdict. No model call. SQLite may use sidecar locks.'}
    plan['acceptance'] = digest(plan)
    return plan


def commit(db, item, against, receipt, profile, task_id, prepared_at, acceptance):
    plan = prepare(db, item, against, receipt, profile, task_id, prepared_at)
    if plan['acceptance'] != acceptance:
        raise ValueError('Source, task or destination changed; inspect a fresh handoff.')
    log = Path(plan['log'])
    fd = os.open(log, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
    with os.fdopen(fd, 'a+') as handle:
        handle.seek(0)
        fcntl.flock(handle, fcntl.LOCK_EX)
        fresh = prepare(db, item, against, receipt, profile, task_id, prepared_at)
        if fresh['acceptance'] != acceptance:
            raise ValueError('Source or task changed before handoff.')
        if any(json.loads(line).get('id') == plan['record']['id'] for line in handle if line.strip()):
            raise ValueError('This handoff was already returned; open its existing record.')
        artifact = Path(plan['record']['artifact'])
        folder = artifact.parent
        if folder.exists() and (folder.is_symlink() or not folder.is_dir()):
            raise ValueError('Unsafe review source directory.')
        folder.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(artifact, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as snapshot:
                snapshot.write(plan['snapshot_bytes'])
                snapshot.flush(); os.fsync(snapshot.fileno())
            handle.seek(0, 2)
            handle.write(json.dumps(plan['record'], ensure_ascii=False, allow_nan=False) + '\n')
            handle.flush(); os.fsync(handle.fileno())
        except Exception:
            # Preserve an artifact after an ambiguous append; never overwrite/retry.
            raise
    return {'id': plan['record']['id'], 'profile': plan['profile'], 'task': plan['task'],
            'log': plan['log'], 'artifact': plan['record']['artifact'], 'status': 'Returned to ZUP For review', 'limit': plan['limit']}
