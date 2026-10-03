import json
import sqlite3
from pathlib import Path
import pytest
from test_judge_preview import store
from helicon.selected_jev import prepare as model_preview, execute
from helicon.jev_handoff import prepare, commit, tasks


def setup(tmp_path):
    db=store(tmp_path);receipt=tmp_path/'comparison.json'
    p=model_preview(db,'a','b',.01,receipt)
    execute(db,'a','b',.01,receipt,p['acceptance'],send=lambda *_:{'answers':{'contradicts':{'noul':.8}},'usage':{'cost':.001}})
    profile=tmp_path/'profile';profile.mkdir()
    (profile/'active-board.json').write_text(json.dumps({'projects':[{'id':'jev','title':'Jev','aliases':[]}]}))
    (profile/'zup-ledger.jsonl').write_text(json.dumps({'id':'task-1','at':'2026-10-03T00:00:00Z','kind':'dispatch','text':'Inspect the pair','project':'jev','by':'agent'})+'\n')
    return db,receipt,profile


def test_actual_return_contract_and_replay_refusal(tmp_path):
    db,r,profile=setup(tmp_path);args=(db,'a','b',r,profile,'task-1','2026-10-03T01:00:00Z')
    assert len(tasks(profile))==1
    p=prepare(*args);assert not (profile/'review-sources').exists()
    result=commit(*args,p['acceptance']);records=[json.loads(x) for x in (profile/'zup-ledger.jsonl').read_text().splitlines()]
    assert records[-1]==p['record'] and records[-1]['re']=='task-1'
    payload=Path(result['artifact']).read_text();assert 'Orbit Wallet' not in payload
    assert json.loads(payload)['observation']['fixture']
    saved=(profile/'zup-ledger.jsonl').read_bytes()
    with pytest.raises(ValueError,match='already'):commit(*args,p['acceptance'])
    assert (profile/'zup-ledger.jsonl').read_bytes()==saved


def test_source_receipt_task_drift_refuses_before_writes(tmp_path):
    db,r,profile=setup(tmp_path);args=(db,'a','b',r,profile,'task-1','2026-10-03T01:00:00Z');p=prepare(*args)
    before=(profile/'zup-ledger.jsonl').read_bytes()
    with sqlite3.connect(db) as c:c.execute("UPDATE helicon_cubes SET content='changed' WHERE id='a'")
    with pytest.raises(ValueError,match='changed'):commit(*args,p['acceptance'])
    assert not (profile/'review-sources').exists() and (profile/'zup-ledger.jsonl').read_bytes()==before


def test_receipt_bytes_and_destination_are_bound(tmp_path):
    db,r,profile=setup(tmp_path);args=(db,'a','b',r,profile,'task-1','2026-10-03T01:00:00Z');p=prepare(*args)
    r.write_text(r.read_text()+'\n')
    with pytest.raises(ValueError,match='changed'):commit(*args,p['acceptance'])
    p=prepare(*args); log=profile/'zup-ledger.jsonl';v=json.loads(log.read_text());v['text']='New task';log.write_text(json.dumps(v)+'\n')
    with pytest.raises(ValueError,match='changed'):commit(*args,p['acceptance'])
    assert not (profile/'review-sources').exists()


def test_superseded_task_is_not_reopened_and_replacement_is_selectable(tmp_path):
    _,_,profile=setup(tmp_path)
    with (profile/'zup-ledger.jsonl').open('a') as log:
        log.write(json.dumps({'id':'task-2','at':'2026-10-03T01:00:00Z','kind':'dispatch','project':'jev','by':'agent','text':'Replacement task','supersedes':'task-1'})+'\n')
    assert [t['id'] for t in tasks(profile)]==['task-2']
