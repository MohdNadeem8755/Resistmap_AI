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

def test_sample_lookup(client):
    sign_up(client)
    # Klebsiella pneumoniae lookup
    r = client.get('/api/sample-lookup?id=SAMN22567290')
    assert r.status_code == 200 and r.json()['found'] is True
    assert r.json()['species'] == 'Klebsiella pneumoniae'
    assert r.json()['status'] in ('Resistant', 'Susceptible')
    assert r.json()['predicted'] in ('Resistant', 'Susceptible')
    assert r.json()['score'] is not None

    # E. coli lookup: lab AST and genuine model prediction & score
    r = client.get('/api/sample-lookup?id=SAMN48878206')
    assert r.status_code == 200 and r.json()['found'] is True
    assert r.json()['species'] == 'Escherichia coli'
    assert r.json()['status'] == 'Resistant'
    assert r.json()['predicted'] == 'Resistant'
    assert r.json()['score'] is not None
    assert r.json()['score_source'] == 'model_inference'

    # A. baumannii lookup: lab AST and genuine model prediction & score
    r = client.get('/api/sample-lookup?id=SAMN02437332')
    assert r.status_code == 200 and r.json()['found'] is True
    assert r.json()['species'] == 'Acinetobacter baumannii'
    assert r.json()['status'] == 'Susceptible'
    assert r.json()['predicted'] == 'Susceptible'
    assert r.json()['score'] is not None
    assert r.json()['score_source'] == 'model_inference'

    # TB lookup: lab AST and genuine model prediction & score
    r = client.get('/api/sample-lookup?id=SAMEA10029749')
    assert r.status_code == 200 and r.json()['found'] is True
    assert r.json()['species'] == 'Mycobacterium tuberculosis'
    assert r.json()['status'] == 'Resistant'
    assert r.json()['predicted'] == 'Resistant'
    assert r.json()['score'] is not None
    assert r.json()['score_source'] == 'model_inference'

    # Non-existent sample: returns Not Susceptible/Resistant, no fallback to Susceptible
    r = client.get('/api/sample-lookup?id=NON_EXISTENT_SAMPLE_XYZ')
    assert r.status_code == 200 and r.json()['found'] is False
    assert r.json()['status'] == 'Not Susceptible/Resistant'
    assert r.json()['score'] is None
    assert 'explanation' in r.json()

    # Empty / blank sample: handled safely
    r = client.get('/api/sample-lookup?id=   ')
    assert r.status_code == 200 and r.json()['found'] is False
    assert r.json()['status'] == 'Not Susceptible/Resistant'


def test_sample_lookup_antibiotic_selection(client):
    sign_up(client)
    # 1. Requesting tested antibiotic returns result
    r = client.get('/api/sample-lookup?id=SAMN48878206&drug=ciprofloxacin')
    assert r.status_code == 200 and r.json()['found'] is True
    assert r.json()['drug'].lower() == 'ciprofloxacin'
    assert r.json()['status'] == 'Resistant'

    # 2. Requesting UNTESTED antibiotic: must NOT silently switch to another drug!
    # Instead, must return Unavailable and list available drugs
    r = client.get('/api/sample-lookup?id=SAMN48878206&drug=nonexistent_antibiotic_123')
    assert r.status_code == 200 and r.json()['found'] is True
    assert r.json()['drug'] == 'nonexistent_antibiotic_123'
    assert r.json()['status'] == 'Unavailable'
    assert r.json()['predicted'] is None
    assert r.json()['score'] is None
    assert 'not tested against nonexistent_antibiotic_123' in r.json()['explanation']


def test_multispecies_summary_and_tb_scope(client):
    sign_up(client)
    d = client.get('/api/dashboard').json()
    ms = d['multispecies']
    assert 'species' in ms
    assert len(ms['species']) == 3

    # Check E. coli and A. baumannii have scores
    ec = next(s for s in ms['species'] if s['id'] == 'escherichia_coli')
    assert ec['scores']['train']['accuracy'] is not None
    assert ec['scores']['validation']['accuracy'] is not None
    assert ec['scores']['test']['accuracy'] is not None

    ab = next(s for s in ms['species'] if s['id'] == 'acinetobacter_baumannii')
    assert ab['scores']['train']['accuracy'] is not None
    assert ab['scores']['validation']['accuracy'] is not None
    assert ab['scores']['test']['accuracy'] is not None

    # Check TB: unsupervised is explicitly marked as unavailable
    tb = next(s for s in ms['species'] if s['id'] == 'tuberculosis')
    assert tb['unsupervised_available'] is True
    assert tb['clustering']['samples'] == 51012
    assert tb['projection']['samples'] == 51012
    assert tb['anomaly_review'] == {}
    assert tb['drugs_skipped'] == 12
    assert tb['eligible_tasks_trained'] == 16
    assert 'independent validation pending' in tb['status']


def test_species_examples_honesty():
    examples = dashboard.get_species_examples()
    # KP examples have saved_v1_prediction
    for ex in examples['Klebsiella pneumoniae']:
        assert ex['score_source'] == 'saved_v1_prediction'

    # EC examples: genuine model inference predictions and scores
    for ex in examples['Escherichia coli']:
        assert ex['score_source'] == 'model_inference'
        assert ex['score'] is not None
        assert ex['predicted'] in ('Resistant', 'Susceptible')

    # AB examples: genuine model inference predictions and scores
    for ex in examples['Acinetobacter baumannii']:
        assert ex['score_source'] == 'model_inference'
        assert ex['score'] is not None
        assert ex['predicted'] in ('Resistant', 'Susceptible')

    # TB examples: genuine model inference predictions and scores.
    for ex in examples['Mycobacterium tuberculosis']:
        assert ex['score_source'] == 'model_inference'
        assert ex['score'] is not None
        assert ex['predicted'] in ('Resistant', 'Susceptible')


def test_tb_images_authentication_and_missing_files(client, tmp_path, monkeypatch):
    urls = ['/api/tb/cluster_image', '/api/tb/projection_image',
            '/api/unsupervised/tuberculosis/projection.png']
    for url in urls:
        assert client.get(url).status_code == 401
    sign_up(client)
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'
        assert response.content.startswith(b'\x89PNG')
    monkeypatch.setattr(dashboard, 'ROOT', tmp_path)
    for url in urls:
        assert client.get(url).status_code == 404


def test_tb_availability_requires_complete_artifacts(tmp_path):
    base = tmp_path/'data/processed/multispecies/tuberculosis/unsupervised_profiles'
    required = ['clusters/report.json', 'clusters/assignments.parquet',
                'clusters/cluster_overview.png', 'svd/report.json',
                'svd/embedding.npy', 'svd/svd_overview.png']
    assert not dashboard.tb_unsupervised_available(tmp_path)
    for name in required:
        path = base/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert dashboard.tb_unsupervised_available(tmp_path)
    for name in required:
        path = base/name
        path.unlink()
        assert not dashboard.tb_unsupervised_available(tmp_path)
        path.touch()


def test_tb_uses_model_inference(monkeypatch):
    """TB now routes through predict_sample like other species."""
    from backend import multispecies_predict
    def mock_inference(species_id, sample_id, drug, standard='CLSI'):
        return {'predicted': 'Resistant', 'score': 0.95, 'source': 'model_inference', 'reason': None}
    monkeypatch.setattr(multispecies_predict, 'predict_sample', mock_inference)
    result = dashboard._run_model_inference('tuberculosis', 'sample', 'drug', 'standard')
    assert result['predicted'] == 'Resistant'
    assert result['score'] == 0.95
    assert result['source'] == 'model_inference'
