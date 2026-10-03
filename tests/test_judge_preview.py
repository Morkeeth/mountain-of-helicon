"""Selected records, full CLI boundary, and actual local HTTP request policy."""
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from helicon.judge_preview import preview, _connect


def store(tmp_path):
    path = tmp_path / 'memory #?% é.sqlite'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE helicon_cubes (id TEXT PRIMARY KEY, title TEXT, content TEXT, source TEXT, source_ref TEXT, created_at TEXT, valid_from TEXT, review_status TEXT, merged_into TEXT)')
    for i, text in [('calendar', 'Launch: Sunday April 27, 2026'), ('date-ok', 'Launch: Monday April 27, 2026'),
                    ('a', 'Orbit Wallet has 5 million users and every user registers exactly 2 devices.'), ('b', 'Orbit Wallet secures 30 million devices.'),
                    ('matching', 'Orbit Wallet secures 10 million devices.'), ('unknown', 'A new launch may happen soon.')]:
        conn.execute('INSERT INTO helicon_cubes VALUES (?,?,?,?,?,?,?,?,?)', (i, i, text, 'fixture', 'fixture.md', '2026-01-01T00:00:00Z', '2026-01-01', 'pending', None))
    conn.commit(); conn.close()
    return path


def test_ro_selected_revision_and_partial_consistency(tmp_path):
    db = store(tmp_path); before = db.read_bytes()
    with patch('socket.socket', side_effect=AssertionError('network')):
        bad = preview(db, 'calendar')
        assert bad['verdict'] == 'contradicted'
        assert bad['items'][0]['content_sha256'] == hashlib.sha256(b'Launch: Sunday April 27, 2026').hexdigest()
        assert bad['jev']['probability'] is None and bad['requests'] == bad['sql_mutations'] == 0
        assert preview(db, 'date-ok')['verdict'] == 'unknown'
        assert preview(db, 'a', 'b')['checks'][-1]['verdict'] == 'unknown'
        matching = preview(db, 'a', 'matching')
        assert matching['checks'][-1]['relation'] == 'consistent'
        assert matching['verdict'] == 'unknown'
        assert preview(db, 'a', 'unknown')['checks'][-1]['verdict'] == 'unknown'
    assert db.read_bytes() == before
    conn = _connect(db)
    with pytest.raises(sqlite3.OperationalError): conn.execute("DELETE FROM helicon_cubes")
    conn.close()


def test_changed_record_gets_new_hash_and_invalid_selection_refused(tmp_path):
    db = store(tmp_path); before = preview(db, 'calendar')
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE helicon_cubes SET content='Launch: Monday April 27, 2026' WHERE id='calendar'")
    after = preview(db, 'calendar')
    assert after['verdict'] == 'unknown'
    assert before['items'][0]['content_sha256'] != after['items'][0]['content_sha256']
    for args in [('missing', None), ('a', 'a')]:
        with pytest.raises(ValueError): preview(db, *args)
    missing = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError): preview(missing, 'a')
    assert not missing.exists()


def test_full_cli_avoids_model_config_and_store_initialization(tmp_path):
    db = store(tmp_path)
    script = '''import sys, importlib.abc, socket
class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('helicon.config','helicon.db','helicon.qwen','openai','requests'):
            raise AssertionError('forbidden import: '+fullname)
sys.meta_path.insert(0,Refuse())
def no(*a,**k): raise AssertionError('network')
socket.socket=no
from helicon.cli import main
sys.argv=['helicon','judge-preview','--db',sys.argv[1],'--item','calendar','--json']
main()
'''
    result = subprocess.run([sys.executable,'-c',script,str(db)], capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['verdict'] == 'contradicted'


def test_local_endpoint_and_policy(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from helicon.api import context_review as routes
    db = store(tmp_path); before = db.read_bytes()
    monkeypatch.setattr(routes, 'get_config', lambda: {'db_path': str(db)})
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/judge-preview?item=calendar').status_code == 403
        assert client.get('/api/judge-preview?item=calendar', headers={'X-Helicon-Local':'1','Origin':'https://other.test'}).status_code == 403
        result = client.get('/api/judge-preview?item=calendar', headers={'X-Helicon-Local':'1','Origin':'http://127.0.0.1'})
        assert result.status_code == 200 and result.json()['verdict'] == 'contradicted'
        assert client.get('/api/judge-preview?item=missing', headers={'X-Helicon-Local':'1'}).status_code == 400
    assert db.read_bytes() == before


def test_pair_scope_regressions():
    from helicon.jev_prechecks import precheck
    ambiguous = [
        ('30 of 100 users are registered.', '70% of users are not registered.'),
        ('The build takes 2 hours.', 'The build does not take 30 minutes.'),
        ('The Alice meeting is on Monday.', 'The Bob meeting is on 2026-10-06.'),
        ('Alice pays Bob 2 million dollars.', 'Bob pays Alice 3000 thousand dollars.'),
        ('The build takes 2 hours.', 'The test takes 30 minutes.'),
        ('30 of 100 Alice users are registered.', '70% of Bob users are registered.'),
        ('The build may take 2 hours.', 'The build may take 30 minutes.'),
    ]
    for a, b in ambiguous:
        assert precheck(a, b) is None, (a, b)
    supported = [
        ('30 of 100 users are registered.', '70% of users are registered.', 'contradiction'),
        ('The build takes 2 hours.', 'The build takes 30 minutes.', 'contradiction'),
        ('The build takes 2 hours.', 'The build takes 120 minutes.', 'consistent'),
        ('The Alice meeting is on Monday.', 'The Alice meeting is on 2026-10-06.', 'contradiction'),
    ]
    for a, b, verdict in supported:
        assert precheck(a, b)['verdict'] == verdict
    # Arithmetic may be shown but does not establish common subjects or metrics.
    for a, b in [
        ('Orbit Wallet has 5 million users and every user registers exactly 2 devices.', 'Orbit Wallet secures 30 million devices.'),
        ('Alice sold 5 apples and 3 apples.', 'Bob sold 20 apples in total.'),
    ]:
        result = precheck(a, b)
        assert result is None or result['verdict'] == 'unknown'


def test_wal_reads_committed_rows_and_discloses_sidecars(tmp_path):
    import shutil
    db = store(tmp_path)
    writer = sqlite3.connect(db)
    try:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute("UPDATE helicon_cubes SET content='Committed in WAL' WHERE id='a'")
        writer.commit()
        copy = tmp_path / 'copied.sqlite'
        shutil.copyfile(db, copy)
        shutil.copyfile(str(db) + '-wal', str(copy) + '-wal')
        report = preview(copy, 'a')
        assert report['items'][0]['content'] == 'Committed in WAL'
        assert report['sql_mutations'] == 0
        assert 'sidecar' in report['storage_limit']
        assert 'writes' not in report
    finally:
        writer.close()
