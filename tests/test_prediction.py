import pytest
from fastapi.testclient import TestClient
from backend import auth
from backend.main import app, attempts
from backend.prediction import predict

CONTENT = 'BioSample\tAMR genotypes\nTEST\tblaSHV-11=COMPLETE, gyrA_S83I=POINT\n'


def test_real_model_threshold_and_unknown_features():
    result = predict(CONTENT, 'Klebsiella pneumoniae', True)
    row = result['results'][0]
    assert row['known_features'] > 0
    assert row['prediction'] == ('Resistant' if row['probability_R'] >= result['threshold'] else 'Susceptible')
    unknown = predict('BioSample\tAMR genotypes\nUNKNOWN\tnot_a_real_gene=COMPLETE', 'Klebsiella pneumoniae', True)
    assert unknown['results'][0]['prediction'] is None
    assert unknown['prediction_run'] is False


@pytest.mark.parametrize('species,complete', [
    ('Pseudomonas aeruginosa', True),
    ('Klebsiella pneumoniae', False),
    ('Escherichia coli', False),
])
def test_scope_required(species, complete):
    with pytest.raises(ValueError):
        predict(CONTENT, species, complete)


def test_multispecies_prediction_endpoints():
    # 1. K. pneumoniae live prediction
    kp_res = predict(CONTENT, 'Klebsiella pneumoniae', True)
    assert kp_res['species'] == 'Klebsiella pneumoniae'
    assert kp_res['target'] == 'ceftazidime'
    assert kp_res['prediction_run'] is True
    assert kp_res['results'][0]['prediction'] in ('Resistant', 'Susceptible')
    assert kp_res['results'][0]['probability_R'] is not None

    # 2. E. coli live prediction
    ec_content = 'BioSample\tAMR genotypes\nEC_01\taac(3)-IId=COMPLETE, gyrA_S83L=POINT\n'
    ec_res = predict(ec_content, 'Escherichia coli', True, drug='ciprofloxacin')
    assert ec_res['species'] == 'Escherichia coli'
    assert ec_res['target'] == 'ciprofloxacin'
    assert ec_res['prediction_run'] is True
    assert ec_res['results'][0]['prediction'] in ('Resistant', 'Susceptible')
    assert ec_res['results'][0]['probability_R'] is not None

    # 3. A. baumannii live prediction
    ab_content = 'BioSample\tAMR genotypes\nAB_01\taac(3)-Ia=COMPLETE\n'
    ab_res = predict(ab_content, 'Acinetobacter baumannii', True, drug='amikacin')
    assert ab_res['species'] == 'Acinetobacter baumannii'
    assert ab_res['target'] == 'amikacin'
    assert ab_res['prediction_run'] is True
    assert ab_res['results'][0]['prediction'] in ('Resistant', 'Susceptible')
    assert ab_res['results'][0]['probability_R'] is not None

    # 4. TB prediction now works with real model artifacts
    tb_res = predict(CONTENT, 'Mycobacterium tuberculosis', True, drug='rifampicin')
    assert tb_res['species'] == 'Mycobacterium tuberculosis'
    assert tb_res['target'] == 'Rifampicin'
    assert tb_res['results'][0]['status'] == 'insufficient_known_features'

    # Verified TB rpoB S450L rifampicin resistance mutation
    tb_rif = predict('BioSample\tAMR genotypes\nTB_01\trpoB_S450L=POINT\n', 'Mycobacterium tuberculosis', True, drug='rifampicin')
    assert tb_rif['prediction_run'] is True
    assert tb_rif['results'][0]['known_features'] == 1
    assert tb_rif['results'][0]['prediction'] in ('Resistant', 'Susceptible')
    assert tb_rif['results'][0]['probability_R'] is not None


def test_authenticated_api(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DB', tmp_path / 'accounts.sqlite3')
    attempts.clear()
    with TestClient(app) as client:
        body = {'content': CONTENT, 'species': 'Klebsiella pneumoniae', 'complete_profile': True}
        assert client.post('/api/predict', json=body).status_code == 401
        assert client.post('/api/auth/register', json={'name': 'Test', 'email': 'prediction@example.invalid', 'password': 'test-password-123'}).status_code == 200
        response = client.post('/api/predict', json=body)
        assert response.status_code == 200
        assert response.json()['independent_validation'] == 'pending'
        assert client.post('/api/predict', json={**body, 'content': 'bad'}).status_code == 422


def test_authenticated_species_and_unavailable_api(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DB', tmp_path / 'accounts.sqlite3')
    attempts.clear()
    with TestClient(app) as client:
        body = {'content': CONTENT, 'species': 'Mycobacterium tuberculosis',
                'complete_profile': True, 'drug': 'rifampicin'}
        assert client.post('/api/predict', json=body).status_code == 401
        assert client.post('/api/auth/register', json={'name': 'Test',
            'email': 'species@example.invalid', 'password': 'test-password-123'}).status_code == 200
        # TB prediction is now enabled — should return 200
        response = client.post('/api/predict', json=body)
        assert response.status_code == 200
        assert response.json()['species'] == 'Mycobacterium tuberculosis'
        for species, calls, drug in [
            ('Escherichia coli', 'aac(3)-IId=COMPLETE,gyrA_S83L=POINT', 'ciprofloxacin'),
            ('Acinetobacter baumannii', 'aac(3)-Ia=COMPLETE', 'amikacin'),
        ]:
            response = client.post('/api/predict', json={**body, 'species': species,
                'drug': drug, 'content': 'BioSample\tAMR genotypes\nTEST\t' + calls})
            assert response.status_code == 200
            assert response.json()['prediction_run'] is True
        monkeypatch.setattr(__import__('backend.prediction', fromlist=['ROOT']), 'ROOT', tmp_path)
        response = client.post('/api/predict', json={**body, 'species': 'Escherichia coli'})
        assert response.status_code == 422
