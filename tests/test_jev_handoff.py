import json
import sqlite3
import tempfile
from pathlib import Path
import pytest
from test_judge_preview import store
from helicon.selected_jev import prepare as model_preview, execute
from helicon.jev_handoff import prepare, commit, tasks, local_file


@pytest.fixture
def home_tmp_path():
    # Exercise the real production home boundary. pytest's platform-default
    # temp directory is outside home on macOS and Linux CI.
    with tempfile.TemporaryDirectory(prefix=".helicon-handoff-test-", dir=Path.home()) as directory:
        yield Path(directory)


def setup(home_tmp_path):
    db=store(home_tmp_path);receipt=home_tmp_path/'comparison.json'
    p=model_preview(db,'a','b',.01,receipt)
    execute(db,'a','b',.01,receipt,p['acceptance'],send=lambda *_:{'answers':{'contradicts':{'noul':.8}},'usage':{'cost':.001}})
    profile=home_tmp_path/'profile';profile.mkdir()
    (profile/'active-board.json').write_text(json.dumps({'projects':[{'id':'jev','title':'Jev','aliases':[]}]}))
    (profile/'zup-ledger.jsonl').write_text(json.dumps({'id':'task-1','at':'2026-10-03T00:00:00Z','kind':'dispatch','text':'Inspect the pair','project':'jev','by':'agent'})+'\n')
    return db,receipt,profile


def test_actual_return_contract_and_replay_refusal(home_tmp_path):
    db,r,profile=setup(home_tmp_path);args=(db,'a','b',r,profile,'task-1','2026-10-03T01:00:00Z')
    assert len(tasks(profile))==1
    p=prepare(*args);assert not (profile/'review-sources').exists()
    result=commit(*args,p['acceptance']);records=[json.loads(x) for x in (profile/'zup-ledger.jsonl').read_text().splitlines()]
    assert records[-1]==p['record'] and records[-1]['re']=='task-1'
    payload=Path(result['artifact']).read_text();assert 'Orbit Wallet' not in payload
    assert json.loads(payload)['observation']['fixture']
    saved=(profile/'zup-ledger.jsonl').read_bytes()
    with pytest.raises(ValueError,match='already'):commit(*args,p['acceptance'])
    assert (profile/'zup-ledger.jsonl').read_bytes()==saved


def test_source_receipt_task_drift_refuses_before_writes(home_tmp_path):
    db,r,profile=setup(home_tmp_path);args=(db,'a','b',r,profile,'task-1','2026-10-03T01:00:00Z');p=prepare(*args)
    before=(profile/'zup-ledger.jsonl').read_bytes()
    with sqlite3.connect(db) as c:c.execute("UPDATE helicon_cubes SET content='changed' WHERE id='a'")
    with pytest.raises(ValueError,match='changed'):commit(*args,p['acceptance'])
    assert not (profile/'review-sources').exists() and (profile/'zup-ledger.jsonl').read_bytes()==before


def test_receipt_bytes_and_destination_are_bound(home_tmp_path):
    db,r,profile=setup(home_tmp_path);args=(db,'a','b',r,profile,'task-1','2026-10-03T01:00:00Z');p=prepare(*args)
    r.write_text(r.read_text()+'\n')
    with pytest.raises(ValueError,match='changed'):commit(*args,p['acceptance'])
    p=prepare(*args); log=profile/'zup-ledger.jsonl';v=json.loads(log.read_text());v['text']='New task';log.write_text(json.dumps(v)+'\n')
    with pytest.raises(ValueError,match='changed'):commit(*args,p['acceptance'])
    assert not (profile/'review-sources').exists()


def test_superseded_task_is_not_reopened_and_replacement_is_selectable(home_tmp_path):
    _,_,profile=setup(home_tmp_path)
    with (profile/'zup-ledger.jsonl').open('a') as log:
        log.write(json.dumps({'id':'task-2','at':'2026-10-03T01:00:00Z','kind':'dispatch','project':'jev','by':'agent','text':'Replacement task','supersedes':'task-1'})+'\n')
    assert [t['id'] for t in tasks(profile)]==['task-2']


def test_outside_home_file_and_profile_are_refused():
    # Supported platforms are macOS/Linux; /tmp is outside the user's home.
    # Keep this negative independent of TMPDIR and pytest's --basetemp.
    with tempfile.TemporaryDirectory(prefix="helicon-outside-home-", dir="/tmp") as directory:
        outside = Path(directory)
        assert not outside.resolve().is_relative_to(Path.home().resolve())
        source = outside / "source.json"
        source.write_text("{}")
        with pytest.raises(ValueError, match="inside your home"):
            local_file(source)
        with pytest.raises(ValueError, match="inside your home"):
            tasks(outside)
        assert source.read_text() == "{}"


@pytest.mark.parametrize('at', ['2026-10-03T01:00:00Z', '2026-10-03T01:00:00.123Z', '2026-10-03T03:00:00+02:00'])
def test_browser_utc_and_offset_times_preserve_confirmed_bytes(home_tmp_path, at):
    db, receipt, profile = setup(home_tmp_path)
    args = (db, 'a', 'b', receipt, profile, 'task-1', at)
    proposal = prepare(*args)
    assert proposal['record']['at'] == at
    result = commit(*args, proposal['acceptance'])
    stored = json.loads((profile / 'zup-ledger.jsonl').read_text().splitlines()[-1])
    assert stored['at'] == at and stored['id'] == result['id']


def test_timezone_less_handoff_is_refused(home_tmp_path):
    db, receipt, profile = setup(home_tmp_path)
    with pytest.raises(ValueError, match='timezone'):
        prepare(db, 'a', 'b', receipt, profile, 'task-1', '2026-10-03T01:00:00')
