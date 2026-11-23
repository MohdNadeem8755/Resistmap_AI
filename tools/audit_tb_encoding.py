"""Read-only TB encoding audit; never trains or writes model artifacts."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from scipy.sparse import csr_matrix, load_npz

ROOT = Path(__file__).resolve().parents[1]


def encode_pairs(pairs, vocabulary):
    """Binary exact (GENE, MUTATION) encoding, including duplicate raw records."""
    lookup = {tuple(pair): i for i, pair in enumerate(vocabulary)}
    if len(lookup) != len(vocabulary):
        raise ValueError('Duplicate vocabulary pairs')
    pairs = set(tuple(pair) for pair in pairs)
    unknown = pairs - lookup.keys()
    if unknown:
        raise ValueError(f'Raw mutations absent from vocabulary: {len(unknown)}')
    indices = sorted(lookup[pair] for pair in pairs)
    return csr_matrix((np.ones(len(indices), dtype=np.uint8),
                       ([0] * len(indices), indices)), shape=(1, len(vocabulary)))


def audit(root=ROOT, count=5):
    base = root / 'data/processed/multispecies/tuberculosis'
    features = base / 'features'
    vocabulary = json.loads((features / 'feature_names.json').read_text())
    samples = pd.read_parquet(features / 'samples.parquet')
    matrix = load_npz(features / 'mutation_features.npz').tocsr()
    assert matrix.shape == (len(samples), len(vocabulary))
    assert samples.sample_accession.is_unique and samples.UNIQUEID.is_unique
    assert sorted(samples.matrix_row) == list(range(len(samples)))
    # Spread deterministic samples across the saved index, not selected for outcome.
    selected = samples.iloc[np.linspace(0, len(samples)-1, count, dtype=int)]
    ids = selected.UNIQUEID.tolist()
    raw = {uid: set() for uid in ids}
    dataset = ds.dataset(root / 'data/multispecies/tuberculosis/MUTATIONS.parquet', format='parquet')
    scanner = dataset.scanner(columns=['UNIQUEID', 'GENE', 'MUTATION'],
                              filter=ds.field('UNIQUEID').isin(ids), batch_size=250000)
    for batch in scanner.to_batches():
        frame = batch.to_pandas(ignore_metadata=True).dropna(subset=['GENE', 'MUTATION'])
        for uid, gene, mutation in frame.itertuples(index=False, name=None):
            raw[uid].add((str(gene), str(mutation)))
    evidence = []
    cols = np.load(base / 'supervised_models/selected_feature_cols.npy', allow_pickle=False)
    assert cols.ndim == 1 and np.issubdtype(cols.dtype, np.integer)
    assert len(cols) and np.all(np.diff(cols) > 0) and cols.min() >= 0 and cols.max() < matrix.shape[1]
    for row in selected.itertuples():
        assert raw[row.UNIQUEID], f'No raw records: {row.UNIQUEID}'
        encoded = encode_pairs(raw[row.UNIQUEID], vocabulary)
        saved = matrix[int(row.matrix_row)]
        assert (encoded != saved).nnz == 0, f'Full encoding mismatch: {row.sample_accession}'
        assert (encoded[:, cols] != saved[:, cols]).nnz == 0
        evidence.append({'sample': row.sample_accession, 'UNIQUEID': row.UNIQUEID,
                         'matrix_row': int(row.matrix_row), 'raw_unique_pairs': len(raw[row.UNIQUEID]),
                         'selected_nonzero': int(encoded[:, cols].nnz)})
    return {'full_matrix_shape': list(matrix.shape), 'selected_columns': len(cols),
            'raw_record_comparisons': evidence, 'encoding_matches': True,
            'model_ordering_certified': False,
            'limitation': 'Five raw-record comparisons verify sampled encoding only. No training-time artifact fingerprint binds the reconstructed mask/vocabulary to model coefficients. External validation pending.'}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
