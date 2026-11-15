import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend import auth, dashboard
from backend.main import app, attempts

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth,'DB',tmp_path/'accounts.sqlite3')
    attempts.clear()
    with TestClient(app) as c:
        yield c

def sign_up(client):
    r=client.post('/api/auth/register',json={'name':'QA Researcher','email':'qa@example.invalid','password':'test-password-for-unit-tests'})
    assert r.status_code==200,r.text
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    return r.json()['user']

def test_session_and_protection(client):
    assert client.get('/api/dashboard').status_code==401
    user=sign_up(client)
    assert client.get('/api/auth/me').json()['user']==user
    with sqlite3.connect(auth.DB) as db:
        row=db.execute('SELECT salt,password_hash FROM users').fetchone()
        assert 'test-password' not in row[1]
        assert len(row[0])==32 and len(row[1])==64
    assert client.get('/api/dashboard').status_code==200
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/dashboard').status_code==401
    assert client.post('/api/auth/login',json={'email':'qa@example.invalid','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'qa@example.invalid','password':'test-password-for-unit-tests'}).status_code==200

def test_sources_and_scope(client):
    sign_up(client)
    d=client.get('/api/dashboard').json()
    assert d['cohort']['total']==445
    assert d['cohort']['susceptible']==83 and d['cohort']['resistant']==362
    assert d['cohort']['assembly_sources']==310 and d['cohort']['read_sources']==135
    assert len({r['id'] for r in d['samples']})==445
    assert d['model']['metrics']['accuracy']==pytest.approx(.9036561222)
    assert d['pipeline']['fresh_accuracy'] is None
    scores = d['model']['measured_scores']
    assert scores['train']['samples'] == 445
    assert scores['test']['samples'] == 114
    assert scores['train']['accuracy'] == pytest.approx(413/445)
    assert scores['test']['accuracy'] == pytest.approx(108/114)
    assert scores['independent_test'] is False
    e=client.get('/api/explore').json()
    assert e['total']==3000 and e['heatmap']['matched_samples']==3000
    assert all(0<=v<=100 for row in e['heatmap']['rows'] for v in row['values'])
    assert sum(c['count'] for c in e['clusters'])==e['total']

def test_input_and_reports(client):
    sign_up(client)
    content=client.get('/api/template').text
    r=client.post('/api/validate-input',json={'content':content})
    assert r.json()['samples']==1 and r.json()['prediction_run'] is False
    for content in ['','BioSample\tAMR genotypes\n','BioSample\tAMR genotypes\na\tbla=COMPLETE\na\tbla=COMPLETE\n','BioSample\tAMR genotypes\na\tmalformed\n']:
        assert client.post('/api/validate-input',json={'content':content}).status_code==422
    assert client.get('/api/reports/queue').status_code==200
    assert client.get('/api/reports/unknown-file').status_code==404
    assert client.get('/api/export/snapshot').json()['cohort']['total']==445

def test_origin_and_assistant(client):
    assert client.post('/api/auth/register',headers={'Origin':'https://unrelated.example'},json={'name':'x','email':'x@y.z','password':'password123'}).status_code==403
    sign_up(client)
    r=client.post('/api/chat',json={'message':'Explain accuracy','language':'en'})
    assert r.status_code==200 and '90.37' in r.json()['answer']
    r=client.post('/api/chat',json={'message':'अभी कितना काम पूरा हुआ?','language':'hi'})
    assert r.status_code==200 and any('\u0900'<=ch<='\u097f' for ch in r.json()['answer'])
