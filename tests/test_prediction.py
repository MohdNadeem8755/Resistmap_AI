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


@pytest.mark.parametrize('species,complete', [('E. coli', True), ('Klebsiella pneumoniae', False)])
def test_scope_required(species, complete):
    with pytest.raises(ValueError):
        predict(CONTENT, species, complete)


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
