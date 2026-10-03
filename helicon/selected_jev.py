"""Explicit one-request comparison of two selected stored revisions.

No automatic invocation, fallback, memory mutation or raw-text result storage.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
from datetime import datetime, timezone

from .judge_preview import _connect, _item

ENDPOINT = 'https://openrouter.ai/api/alpha/decisions'
QUESTION = {'contradicts': {'type': 'noul',
    'instructions': 'Do these two memory items contradict each other?',
    'criteria': {'true': 'Both items cannot be true at the same time: they assert different values for the same fact.',
                 'false': 'Both items can be true together: they agree, restate each other, or describe different facts.'}}}
LIMIT = 'One request maximum. The cap stops further requests after reported cost; it is not a price guarantee. No retry or fallback. A model estimate is not memory truth.'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def sources(db, item, against):
    if not item or not against or item == against:
        raise ValueError('Explicitly choose two different stored items.')
    conn = _connect(db)
    try:
        return [_item(conn, item), _item(conn, against)]
    finally:
        conn.close()


def destination(output):
    path = Path(output).expanduser()
    if not path.is_absolute() or path.suffix != '.json':
        raise ValueError('Choose an absolute path to a NEW .json result file.')
    if path.exists() or path.is_symlink():
        raise ValueError('Output already exists; existing files are never overwritten.')
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('Output directory must already exist.')
    return parent / path.name


def prepare(db, item, against, max_usd, output):
    if not number(max_usd) or max_usd <= 0:
        raise ValueError('Cap must be a finite positive number.')
    path = destination(output)
    rows = sources(db, item, against)
    texts = [row['content'] for row in rows]
    if any(len(text.encode()) > 16000 for text in texts):
        raise ValueError('Each selected item must be at most 16 KB; no silent clipping.')
    # Conservative screen, not a guarantee that arbitrary private data is recognized.
    if any(re.search(r'(?i)(sk-[a-z0-9_-]{12,}|-----BEGIN .*PRIVATE KEY|password\s*[:=]|api[_ -]?key\s*[:=]|[\w.+-]+@[\w.-]+\.[a-z]{2,}|/Users/|/home/|\b(?:medical|passport|social security|bank account)\b)', text) for text in texts):
        raise ValueError('Selected text is excluded by the local privacy screen. No request was sent.')
    body = {'model': 'typesafe/jev-1.13', 'state': {'item_a': texts[0], 'item_b': texts[1]}, 'questions': QUESTION}
    binding = {'schema': 'helicon.selected-jev/1', 'database_path_sha256': digest(str(Path(db).expanduser().resolve(strict=True))),
               'sources': [{'id': row['id'], 'content_sha256': row['content_sha256']} for row in rows],
               'request_sha256': digest(body), 'question_sha256': digest(QUESTION), 'max_usd': max_usd,
               'output_sha256': digest(str(path)), 'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return {'acceptance': digest(binding), 'binding': binding, 'request': body, 'output': str(path),
            'endpoint': ENDPOINT, 'limit': LIMIT, 'privacy': 'Both complete stored texts go to OpenRouter and its model provider only after confirmation. Titles, source paths and review verdicts are excluded. The local privacy screen is incomplete; inspect every byte below.',
            'key_available': bool(os.environ.get('OPENROUTER_API_KEY'))}


def transport(body, key):
    import requests
    response = requests.post(ENDPOINT, json=body, headers={'Authorization': 'Bearer ' + key}, timeout=60, allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("Provider did not return a successful decision")
    response.raise_for_status()
    return response.json()


def execute(db, item, against, max_usd, output, acceptance, *, send=None):
    proposed = prepare(db, item, against, max_usd, output)
    if acceptance != proposed['acceptance']:
        raise ValueError('Selected source or request changed. Inspect a fresh preview; nothing was sent or saved.')
    key = os.environ.get('OPENROUTER_API_KEY')
    if send is None and not key:
        raise ValueError('OPENROUTER_API_KEY is required for explicit execution. Nothing was sent or saved.')
    # Reserve new output before sending. O_EXCL refuses symlink/existing-file races.
    fd = os.open(proposed['output'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    result = dict(proposed['binding'], observed_at=datetime.now(timezone.utc).isoformat(),
                  model=proposed['request']['model'], fixture=send is not None, requests=1,
                  probability=None, reported_cost_usd=None, billing_status='unknown', status='unknown', limit=LIMIT)
    try:
        try:
            raw = (send or transport)(proposed['request'], key)
            p = raw.get('answers', {}).get('contradicts')
            if isinstance(p, dict):
                p = p.get('noul')
            if number(p) and 0 <= p <= 1:
                result['probability'] = p
                result['status'] = 'recorded model estimate'
            cost = raw.get('usage', {}).get('cost')
            if number(cost) and cost >= 0:
                result['reported_cost_usd'] = cost
                result['billing_status'] = 'reported above cap' if cost > max_usd else 'reported within cap'
        except Exception:
            # Raw provider errors can contain private request text or credentials.
            result['status'] = 'unknown: request or response failed; no retry'
        with os.fdopen(fd, 'w') as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write('\n')
        return recorded(db, item, against, proposed['output'])
    except BaseException:
        # Retain reserved file on disk failure: never retry an ambiguously billed call.
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def recorded(db, item, against, output):
    path = Path(output).expanduser()
    if path.stat().st_size > 32000:
        raise ValueError('Not a bounded comparison result.')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('schema') != 'helicon.selected-jev/1':
        raise ValueError('Not a selected Jev comparison result.')
    current = [{'id': row['id'], 'content_sha256': row['content_sha256']} for row in sources(db, item, against)]
    matches = value.get('sources') == current and value.get('database_path_sha256') == digest(str(Path(db).expanduser().resolve(strict=True)))
    valid_p = number(value.get('probability')) and 0 <= value['probability'] <= 1
    valid_cost = number(value.get('reported_cost_usd')) and value['reported_cost_usd'] >= 0
    cap = value.get('max_usd')
    valid_cap = number(cap) and cap > 0
    def hash_field(name):
        field = value.get(name)
        return field if isinstance(field, str) and re.fullmatch(r'[0-9a-f]{64}', field) else None
    valid_provenance = all(hash_field(k) for k in ('request_sha256', 'question_sha256', 'checker_sha256'))
    at = value.get('observed_at')
    try:
        if not isinstance(at, str) or len(at) > 64 or datetime.fromisoformat(at).tzinfo is None:
            at = None
    except ValueError:
        at = None
    supported = matches and valid_p and valid_cap and valid_provenance and at is not None and value.get('model') == 'typesafe/jev-1.13' and value.get('requests') == 1 and type(value.get('fixture')) is bool
    # Reconstruct every returned field. Never echo unknown/nested fields from a file.
    safe = {'schema': 'helicon.selected-jev/1', 'sources': current if matches else [],
            'observed_at': at, 'model': 'typesafe/jev-1.13' if value.get('model') == 'typesafe/jev-1.13' else 'unknown',
            'fixture': value.get('fixture') is True, 'requests': 1 if value.get('requests') == 1 else None,
            'probability': value['probability'] if supported else None,
            'reported_cost_usd': value['reported_cost_usd'] if valid_cost else None,
            'billing_status': ('reported above cap' if value['reported_cost_usd'] > cap else 'reported within cap') if valid_cost and valid_cap else 'unknown',
            'status': 'recorded model estimate' if supported else 'unknown: source mismatch or invalid/incomplete recorded result',
            'limit': LIMIT, 'max_usd': cap if valid_cap else None, 'source_matches': matches,
            'authenticity': 'Local historical file; no signature or independent provider verification. Model names the requested model; served model identity is unverified.'}
    for name in ('request_sha256', 'question_sha256', 'checker_sha256'):
        safe[name] = hash_field(name)
    return safe
