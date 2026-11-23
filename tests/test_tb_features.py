import json

import numpy as np
import pandas as pd
from scipy.sparse import load_npz

from tools import build_tb_features as builder


def test_binary_features_quarantine_and_label_alignment(tmp_path, monkeypatch):
    base = tmp_path / 'data/processed/multispecies/tuberculosis'
    raw = tmp_path / 'data/multispecies/tuberculosis'
    base.mkdir(parents=True)
    raw.mkdir(parents=True)
    samples = pd.DataFrame({
        'sample_accession': ['a', 'b', 'b', 'c'],
        'UNIQUEID': ['g1', 'g2', 'g3', 'g4'],
        'LINEAGE': ['L'] * 4, 'SUBLINEAGE': ['L1'] * 4,
        'study_accession': ['study'] * 4, 'dataset': ['test'] * 4,
    })
    samples.to_parquet(base / 'feature_sample_map.parquet', index=False)
    pd.DataFrame({'sample_accession': ['a', 'b', 'c'], 'DRUG': ['D'] * 3,
                  'target': [0, 1, 0]}).to_parquet(base / 'qc_labels.parquet', index=False)
    # Named index exercises Arrow's pandas-index metadata handling.
    pd.DataFrame({'UNIQUEID': ['g1'] * 256 + ['g2', 'g4'],
                  'GENE': ['gene'] * 258,
                  'MUTATION': ['change'] * 257 + [None]}).set_index('UNIQUEID').to_parquet(raw / 'MUTATIONS.parquet')
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'BASE', base)
    monkeypatch.setattr(builder, 'OUT', base / 'features')
    builder.main()
    out = base / 'features'
    matrix = load_npz(out / 'mutation_features.npz')
    assert matrix.shape == (1, 1)
    np.testing.assert_array_equal(matrix.toarray(), [[1]])
    assert pd.read_parquet(out / 'samples.parquet').sample_accession.tolist() == ['a']
    assert pd.read_parquet(out / 'labels.parquet').sample_accession.tolist() == ['a']
    report = json.loads((out / 'report.json').read_text())
    assert report['quarantined_mapping_rows'] == 2
    assert report['samples_without_features'] == 1
