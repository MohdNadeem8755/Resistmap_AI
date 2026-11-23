import json
from types import SimpleNamespace
import numpy as np
import pytest
from backend import prediction, multispecies_predict

CONTENT = 'BioSample\tAMR genotypes\nTEST\tgene=COMPLETE,gene=COMPLETE\n'


def setup_artifacts(tmp_path, monkeypatch, model):
    base = tmp_path / 'data/processed/multispecies/escherichia_coli/encoded'
    (base / 'supervised_models').mkdir(parents=True)
    (base / 'supervised_models/ciprofloxacin_CLSI.joblib').touch()
    (base / 'feature_names.json').write_text(json.dumps(['gene=COMPLETE']))
    monkeypatch.setattr(prediction, 'ROOT', tmp_path)
    prediction._load_multispecies_feature_names.cache_clear()
    monkeypatch.setattr(prediction, '_load_multispecies_model_file', lambda *args: model)
    return base


def test_missing_model_and_vocabulary(tmp_path, monkeypatch):
    base = setup_artifacts(tmp_path, monkeypatch, None)
    (base / 'feature_names.json').unlink()
    with pytest.raises(RuntimeError, match='vocabulary unavailable'):
        prediction.predict(CONTENT, 'Escherichia coli', True)
    (base / 'supervised_models/ciprofloxacin_CLSI.joblib').unlink()
    with pytest.raises(ValueError, match='No saved model'):
        prediction.predict(CONTENT, 'Escherichia coli', True)


@pytest.mark.parametrize('dimension,classes', [(2, [0, 1]), (1, [0, 2])])
def test_incompatible_models(tmp_path, monkeypatch, dimension, classes):
    setup_artifacts(tmp_path, monkeypatch, SimpleNamespace(n_features_in_=dimension, classes_=classes))
    with pytest.raises(RuntimeError, match='dimension mismatch|binary'):
        prediction.predict(CONTENT, 'Escherichia coli', True)


def test_binary_encoding_and_class_order(tmp_path, monkeypatch):
    class Model:
        n_features_in_ = 1
        classes_ = np.array([1, 0])
        def predict_proba(self, x):
            assert x.toarray().tolist() == [[1]]
            return np.array([[0.8, 0.2]])
        def predict(self, x):
            return [1]
    setup_artifacts(tmp_path, monkeypatch, Model())
    result = prediction.predict(CONTENT, 'Escherichia coli', True)
    assert result['results'][0]['probability_R'] == 0.8
    assert result['results'][0]['known_features'] == 1


def test_tb_fails_gracefully_without_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='feature vocabulary.*not available'):
        prediction.predict(CONTENT, 'Mycobacterium tuberculosis', True, 'rifampicin')
    # multispecies_predict should also fail gracefully when matrix files are missing
    monkeypatch.setattr(multispecies_predict, 'ROOT', tmp_path)
    multispecies_predict._load_matrix.cache_clear()
    result = multispecies_predict.predict_sample('tuberculosis', 'SAMEA13299636', 'rifampicin')
    assert result['score'] is None and result['source'] == 'not_integrated'


@pytest.fixture(autouse=True)
def clear_feature_cache():
    prediction._load_multispecies_feature_names.cache_clear()
    yield
    prediction._load_multispecies_feature_names.cache_clear()


def test_sample_lookup_rejects_other_standard_and_partial_drug(tmp_path, monkeypatch):
    models = tmp_path/'data/processed/multispecies/escherichia_coli/encoded/supervised_models'
    models.mkdir(parents=True)
    (models/'example_EUCAST.joblib').touch()
    (models/'example_extended_CLSI.joblib').touch()
    monkeypatch.setattr(multispecies_predict, 'ROOT', tmp_path)
    monkeypatch.setattr(multispecies_predict, '_load_matrix', lambda *a: (object(), object(), None))
    def unexpected_load(*args):
        raise AssertionError('A different model must not be loaded')
    monkeypatch.setattr(multispecies_predict, '_load_model', unexpected_load)
    result = multispecies_predict.predict_sample('escherichia_coli', 'sample', 'example', 'CLSI')
    assert result['source'] == 'not_integrated'
    assert result['predicted'] is None and result['score'] is None
