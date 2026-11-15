"""Inference from trusted local V2 artifacts; no uploaded pickle loading."""
import csv
import io
import json
from functools import lru_cache

from backend import dashboard


@lru_cache(maxsize=2)
def load_model(directory, modified):
    import joblib
    import sklearn
    from pathlib import Path
    path = Path(directory)
    metadata = json.loads((path / 'metadata.json').read_text())
    if sklearn.__version__ != metadata['sklearn_version']:
        raise RuntimeError('Model runtime version does not match its training version.')
    model = joblib.load(path / 'model_with_threshold.joblib')
    if float(model.threshold) != float(metadata['threshold']):
        raise RuntimeError('Saved model threshold and metadata disagree.')
    return model, metadata


def predict(content, species, complete_profile):
    if species != 'Klebsiella pneumoniae' or not complete_profile:
        raise ValueError('Confirm Klebsiella pneumoniae and a complete annotated AMR profile.')
    dashboard.validate_input(content)
    first = content.lstrip('\ufeff').splitlines()[0]
    rows = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff')),
                               delimiter='\t' if '\t' in first else ','))
    path, _ = dashboard.latest_model(dashboard.ROOT)
    if path is None or not (path / 'model_with_threshold.joblib').is_file():
        raise RuntimeError('Saved V2 model is unavailable.')
    model, metadata = load_model(str(path), (path / 'model_with_threshold.joblib').stat().st_mtime_ns)
    vocabulary = model.estimator_.named_steps['features'].vocabulary_
    prepared = []
    for row in rows:
        features = {}
        ignored = 0
        for token in row['AMR genotypes'].split(','):
            if not token.strip():
                continue
            name, status = (part.strip() for part in token.rsplit('=', 1))
            prefix = {'COMPLETE': 'gene:', 'POINT': 'mutation:'}.get(status)
            if prefix:
                features[prefix + name] = 1
            else:
                ignored += 1
        known = sum(key in vocabulary for key in features)
        prepared.append((row['BioSample'].strip(), features, known, ignored))
    eligible = [item for item in prepared if item[2]]
    predictions = {}
    if eligible:
        inputs = [item[1] for item in eligible]
        probabilities = model.predict_proba(inputs)[:, list(model.classes_).index(1)]
        labels = model.predict(inputs)
        predictions = {item[0]: (float(prob), int(label))
                       for item, prob, label in zip(eligible, probabilities, labels)}
    results = []
    for sample, features, known, ignored in prepared:
        probability, label = predictions.get(sample, (None, None))
        results.append({'sample': sample,
                        'prediction': None if label is None else ('Resistant' if label else 'Susceptible'),
                        'probability_R': probability, 'known_features': known,
                        'unseen_features': sorted(set(features) - set(vocabulary)),
                        'ignored_entries': ignored,
                        'status': 'research_prediction' if known else 'insufficient_known_features'})
    return {'target': 'ceftazidime', 'species': species, 'model': metadata['candidate'],
            'version': 'V2', 'threshold': metadata['threshold'], 'samples': len(rows),
            'prediction_run': bool(eligible), 'results': results,
            'independent_validation': 'pending',
            'notice': 'Research baseline only. Probability is a model score, not calibrated confidence. '
                      'Missing calls are encoded as absent; incomplete profiles can produce misleading results. '
                      'No uncertainty or genomic novelty guarantee is provided.'}
