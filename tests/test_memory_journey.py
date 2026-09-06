"""Actual saved review/correction/packet loop, with explicit synthetic sources."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helicon.api import context_review as api


def setup(monkeypatch, tmp_path):
    project=(tmp_path/'project').resolve(); project.mkdir()
    home=tmp_path/'home'; home.mkdir(); (project/'.git').mkdir()
    source=project/'AGENTS.md'
    source.write_text('Atlas phase = Build\nAtlas phase = Validate\nBirch phase = Validate\n')
    monkeypatch.setattr(api,'get_config',lambda:{'context_review':{'home':str(home),'projects':[{'id':'sample','path':str(project)}]}})
    monkeypatch.setattr(api,'helicon_home',lambda:str(tmp_path/'state'))
    app=FastAPI();app.include_router(api.router,prefix='/api')
    client=TestClient(app,base_url='http://127.0.0.1:8420'); headers={'X-Helicon-Local':'1'}
    def post(action,**fields):
        r=client.post('/api/context-review/'+action,headers=headers,json={'project_id':'sample',**fields})
        assert r.status_code==200,r.text
        return r.json()
    def get():
        r=client.get('/api/context-review/journey?project_id=sample',headers=headers)
        assert r.status_code==200,r.text
        return r.json()
    return project,source,client,post,get


def test_source_correction_delivery_behavior_and_return(monkeypatch,tmp_path):
    project,source,client,post,get=setup(monkeypatch,tmp_path)
    assert get()['journeys']==[]
    assert not (tmp_path/'state').exists()
    read=post('read');first=post('snapshots',revision=read['revision'])
    assert next(j for j in get()['journeys'] if j['subject']=='Atlas')['state']=='disagreement'
    finding=next(f for f in read['report']['findings'] if f['kind']=='source-disagreement')
    index=next(i for i,e in enumerate(finding['evidence']) if 'Build' in e['quote'])
    preview=post('preview',snapshot_id=first['id'],finding_id=finding['id'],evidence_index=index,replacement='Atlas phase = Validate\n',reason='Synthetic decision: validation is current.')
    applied=post('apply',preview_id=preview['id'],preview_hash=preview['hash'])
    read=post('read');second=post('snapshots',revision=read['revision'])
    sid=next(s['id'] for s in read['report']['sources'] if s['path']==str(source))
    packet=post('packets',snapshot_id=second['id'],source_ids=[sid],run_id='synthetic-consumer',provider='fixture')
    atlas=next(j for j in get()['journeys'] if j['subject']=='Atlas')
    assert atlas['current_values']==['Validate']
    assert atlas['corrections'][0]['status']=='applied'
    assert any(o['value']=='Build' and o['source_state']=='changed_since_observation' for o in atlas['observations'])
    assert atlas['consumers'][0]['read_state']=='not_observed'
    _,packets=api.packets('sample');packets.consume(packet['id'],packet['recipient'])
    atlas=next(j for j in get()['journeys'] if j['subject']=='Atlas')
    assert atlas['consumers'][0]['read_state']=='interface_returned_bytes'
    assert atlas['consumers'][0]['ack_state']=='not_recorded_by_this_contract'
    assert atlas['consumers'][0]['behavior']==[]
    artifact=project/'result.txt';artifact.write_text('Synthetic consumer: phase is Validate.\n')
    packets.attach_behavior(packet['id'],packet['recipient'],artifact,'fixture-reviewer','Synthetic review of exact output against the phase.','supported')
    atlas=next(j for j in get()['journeys'] if j['subject']=='Atlas')
    assert atlas['consumers'][0]['behavior'][0]['artifact_current'] is True
    assert 'phase is Validate' in atlas['consumers'][0]['behavior'][0]['artifact_preview']
    assert next(j for j in get()['journeys'] if j['subject']=='Birch')['corrections']==[]
    artifact.write_text('Changed later; earlier review no longer establishes this.\n')
    atlas=next(j for j in get()['journeys'] if j['subject']=='Atlas')
    assert atlas['consumers'][0]['behavior'][0]['artifact_current'] is False
    assert atlas['consumers'][0]['behavior'][0]['artifact_preview'] is None
    post('undo',correction_id=applied['correction_id'])
    atlas=next(j for j in get()['journeys'] if j['subject']=='Atlas')
    assert atlas['corrections'][0]['status']=='undone'
    assert atlas['state']=='disagreement'
    assert atlas['consumers'][0]['consumption'] is not None
    assert atlas['consumers'][0]['source_status']!='current'
    source.unlink()
    assert all(j['state']=='current_state_unverified' for j in get()['journeys'])


def test_local_boundary_and_unobserved_source_change(monkeypatch,tmp_path):
    project,source,client,post,get=setup(monkeypatch,tmp_path)
    url='/api/context-review/journey?project_id=sample'
    assert client.get(url).status_code==403
    assert client.get(url,headers={'X-Helicon-Local':'1','Origin':'https://attacker.example'}).status_code==403
    assert client.get('/api/context-review/journey?project_id=other',headers={'X-Helicon-Local':'1'}).status_code==404
    report=post('read');post('snapshots',revision=report['revision'])
    source.write_text('Atlas phase = Released\n')
    assert all(j['state']=='current_state_unverified' for j in get()['journeys'])
    assert all(j['consumers']==[] for j in get()['journeys'])
