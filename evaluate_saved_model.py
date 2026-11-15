"""Measure frozen V2 training and historical test scores without fitting/tuning."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from backend.dashboard import latest_model
from backend.prediction import load_model

ROOT = Path(__file__).resolve().parent


def rows(path, delimiter=','):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        reader.fieldnames = [v.lstrip('#').strip() for v in reader.fieldnames]
        return list(reader)


def main():
    path, metadata = latest_model(ROOT)
    model_file = path / 'model_with_threshold.joblib'
    model, _ = load_model(str(path), model_file.stat().st_mtime_ns)
    manifest = rows(ROOT / 'results/ceftazidime_clsi_split_v2.csv')
    partitions = {p: [r for r in manifest if r['partition'] == p] for p in ('train', 'test')}
    train_ids = {r['BioSample'] for r in partitions['train']}
    test_ids = {r['BioSample'] for r in partitions['test']}
    assert train_ids == set(metadata['training_biosamples'])
    assert train_ids.isdisjoint(test_ids)
    assert {r['BioProject'] for r in partitions['train']}.isdisjoint({r['BioProject'] for r in partitions['test']})
    genomes = rows(ROOT / 'data/raw/isolates_with_metadata.tsv', '\t')
    lookup = {}
    for row in genomes:
        key = (row['BioSample'].strip().upper(), row['Isolate'])
        features = {}
        for token in row.get('AMR genotypes', '').split(','):
            if '=' not in token:
                continue
            name, status = (s.strip() for s in token.rsplit('=', 1))
            prefix = {'COMPLETE': 'gene:', 'POINT': 'mutation:'}.get(status.upper())
            if prefix:
                features[prefix + name] = 1
        if key in lookup:
            assert lookup[key] == features, f'Conflicting genome rows: {key}'
        lookup[key] = features
    history = rows(ROOT / 'results/ceftazidime_clsi_test_predictions_v1.csv')
    labels = {r['BioSample']: int(r['actual']) for r in rows(ROOT / 'results/ceftazidime_rf_oof_predictions.csv') + history}
    assert test_ids == {r['BioSample'] for r in history}
    v1 = joblib.load(ROOT / 'models/ceftazidime_clsi_rf_v1.joblib')
    # Reproduce every archived V1 prediction as a feature-reconstruction check.
    expected = {r['BioSample']: int(r['predicted']) for r in history}
    test_x = [lookup[(r['BioSample'], r['Isolate'])] for r in partitions['test']]
    assert list(v1.predict(test_x)) == [expected[r['BioSample']] for r in partitions['test']]
    output = {'model_run': path.name, 'model_sha256': hashlib.sha256(model_file.read_bytes()).hexdigest(),
              'measured_at': datetime.now(timezone.utc).isoformat(), 'threshold': metadata['threshold'],
              'independent_test': False, 'v1_reproduction_verified': True,
              'note': 'Training is resubstitution. Testing reuses the historical cohort that informed redevelopment; not fresh independent validation.'}
    for partition, records in partitions.items():
        x = [lookup[(r['BioSample'], r['Isolate'])] for r in records]
        actual = [labels[r['BioSample']] for r in records]
        predictions = model.predict(x)
        output[partition] = {'samples': len(records), 'accuracy': float(accuracy_score(actual, predictions)),
                             'balanced_accuracy': float(balanced_accuracy_score(actual, predictions))}
    (path / 'measured_scores.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
