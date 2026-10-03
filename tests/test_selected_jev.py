import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest
from test_judge_preview import store
from helicon.selected_jev import prepare, execute, recorded


def fake(body, key):
    assert set(body['state']) == {'item_a', 'item_b'}
    return {'answers': {'contradicts': {'noul': .8}}, 'usage': {'cost': .001}}


def test_explicit_action_metadata_reload_and_source_refusal(tmp_path):
    db = store(tmp_path); output = tmp_path / 'result.json'; before = db.read_bytes()
    p = prepare(db, 'a', 'b', .01, output)
    assert not output.exists()
    assert p['request']['state']['item_a'].startswith('Orbit Wallet')
    r = execute(db, 'a', 'b', .01, output, p['acceptance'], send=fake)
    assert r['fixture'] and r['probability'] == .8 and r['source_matches']
    assert db.read_bytes() == before
    assert os.stat(output).st_mode & 0o777 == 0o600
    assert 'Orbit Wallet' not in output.read_text()
    saved = output.read_bytes()
    next_path = tmp_path / 'next.json'; proposal = prepare(db, 'a', 'b', .01, next_path)
    with sqlite3.connect(db) as c: c.execute("UPDATE helicon_cubes SET content='changed' WHERE id='a'")
    assert recorded(db, 'a', 'b', output)['probability'] is None
    with pytest.raises(ValueError, match='changed'):
        execute(db, 'a', 'b', .01, next_path, proposal['acceptance'], send=lambda *_: pytest.fail('sent'))
    assert not next_path.exists() and output.read_bytes() == saved


def test_output_and_cap_refusals_before_send(tmp_path):
    db = store(tmp_path)
    for cap in [math.nan, math.inf, -1, 0, True]:
        with pytest.raises(ValueError): prepare(db, 'a', 'b', cap, tmp_path/'new.json')
    link = tmp_path/'link.json'; link.symlink_to(db)
    for output in [db, link, tmp_path/'missing'/'new.json']:
        with pytest.raises((ValueError, OSError)): prepare(db, 'a', 'b', .01, output)
    p = prepare(db, 'a', 'b', .01, tmp_path/'new.json')
    (tmp_path/'new.json').write_text('preserve')
    with pytest.raises(ValueError): execute(db, 'a', 'b', .01, tmp_path/'new.json', p['acceptance'], send=lambda *_: pytest.fail('sent'))
    assert (tmp_path/'new.json').read_text() == 'preserve'


@pytest.mark.parametrize('probability', [float('nan'), float('inf'), -1, 2.5, True, '0.8', None])
def test_invalid_probability_remains_unknown(tmp_path, probability):
    db=store(tmp_path); out=tmp_path/'result.json'; p=prepare(db,'a','b',.01,out)
    r=execute(db,'a','b',.01,out,p['acceptance'],send=lambda *_: {'answers':{'contradicts':{'noul':probability}},'usage':{'cost':-4}})
    assert r['probability'] is None and r['status'].startswith('unknown')
    assert r['reported_cost_usd'] is None and r['billing_status']=='unknown'


def test_unsigned_readback_validates_all_fields(tmp_path):
    db=store(tmp_path);out=tmp_path/'result.json';p=prepare(db,'a','b',.01,out)
    execute(db,'a','b',.01,out,p['acceptance'],send=fake)
    v=json.loads(out.read_text()); v.update(probability=2.5, reported_cost_usd=-4, status='FAKE CONFIDENCE', model='PRIVATE RAW TEXT')
    v['sources'][0]['raw']='SECRET'
    out.write_text(json.dumps(v));r=recorded(db,'a','b',out)
    assert r['probability'] is None and r['reported_cost_usd'] is None
    assert r['status'].startswith('unknown') and r['model']=='unknown'
    assert 'SECRET' not in json.dumps(r) and 'PRIVATE RAW' not in json.dumps(r)


def test_key_privacy_and_cli_no_send(tmp_path, monkeypatch):
    db=store(tmp_path);out=tmp_path/'result.json';p=prepare(db,'a','b',.01,out)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with pytest.raises(ValueError,match='KEY'):execute(db,'a','b',.01,out,p['acceptance'])
    assert not out.exists()
    run=subprocess.run([sys.executable,'-m','helicon.cli','judge-compare','--db',str(db),'--item','a','--against','b','--output',str(out)],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['acceptance']==p['acceptance']
    with sqlite3.connect(db) as c:c.execute("UPDATE helicon_cubes SET content='email person@example.com' WHERE id='b'")
    with pytest.raises(ValueError,match='privacy'):prepare(db,'a','b',.01,out)


def test_api_guards_and_actual_selected_output(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from helicon.api import context_review
    app=FastAPI();app.include_router(context_review.router,prefix='/api')
    db=store(tmp_path);out=tmp_path/'result.json'
    request={'item':'a','against':'b','output':str(out),'max_usd':.01}
    with patch.object(context_review,'get_config',return_value={'db_path':str(db)}):
        client=TestClient(app,base_url='http://localhost')
        assert client.post('/api/judge-compare/preview',json=request).status_code==403
        headers={'X-Helicon-Local':'1'}
        assert client.post('/api/judge-compare/preview',json=request,headers={**headers,'Origin':'https://evil.example'}).status_code==403
        p=client.post('/api/judge-compare/preview',json=request,headers=headers)
        assert p.status_code==200
        assert client.post('/api/judge-compare/run',json=request,headers=headers).status_code==400
        request['acceptance']=p.json()['acceptance']
        # Inject only at the test call boundary; never via a production flag/env variable.
        import helicon.selected_jev as module
        actual=module.execute
        with patch.object(module,'execute',side_effect=lambda *a,**kw:actual(*a,**kw,send=fake)):
            r=client.post('/api/judge-compare/run',json=request,headers=headers)
        assert r.status_code==200 and r.json()['fixture']
        assert client.post('/api/judge-compare/read',json=request,headers=headers).json()['probability']==.8


@pytest.mark.parametrize('cost', [None, -1, float('nan'), float('inf'), True])
def test_unknown_billing_has_one_call_no_estimate(tmp_path, cost):
    db=store(tmp_path);out=tmp_path/'result.json';p=prepare(db,'a','b',.01,out);calls=[]
    def send(body,key):
        calls.append(1)
        return {'answers':{'contradicts':{'noul':.6}},'usage':{'cost':cost}}
    r=execute(db,'a','b',.01,out,p['acceptance'],send=send)
    assert len(calls)==1 and r['probability']==.6
    assert r['billing_status']=='unknown' and r['reported_cost_usd'] is None


def test_transport_error_not_raw_error_or_retry(tmp_path):
    db=store(tmp_path);out=tmp_path/'result.json';p=prepare(db,'a','b',.01,out);calls=[]
    def send(*_):
        calls.append(1);raise RuntimeError('PRIVATE RAW ERROR')
    r=execute(db,'a','b',.01,out,p['acceptance'],send=send)
    assert len(calls)==1 and r['probability'] is None
    assert 'PRIVATE RAW ERROR' not in out.read_text()
