"""Build a sparse TB mutation matrix by streaming the large mutation parquet."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from scipy.sparse import csr_matrix, save_npz

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/multispecies/tuberculosis'
OUT = BASE / 'features'


def main():
    OUT.mkdir(exist_ok=True)
    labels = pd.read_parquet(BASE / 'qc_labels.parquet')
    mapping = pd.read_parquet(BASE / 'feature_sample_map.parquet')
    mapping = mapping.dropna(subset=['sample_accession', 'UNIQUEID'])
    ambiguous = mapping.groupby('sample_accession').UNIQUEID.nunique()
    shared = mapping.groupby('UNIQUEID').sample_accession.nunique()
    rejected = mapping.sample_accession.isin(ambiguous[ambiguous.ne(1)].index) | mapping.UNIQUEID.isin(shared[shared.ne(1)].index)
    mapping.loc[rejected].to_parquet(OUT / 'quarantined_mappings.parquet', index=False)
    samples = mapping.loc[~rejected, ['sample_accession', 'UNIQUEID', 'LINEAGE', 'SUBLINEAGE', 'study_accession', 'dataset']].drop_duplicates('sample_accession').reset_index(drop=True)
    ids = set(samples.UNIQUEID)
    counts = Counter()
    dataset = ds.dataset(ROOT / 'data/multispecies/tuberculosis/MUTATIONS.parquet', format='parquet')
    scanner = dataset.scanner(columns=['UNIQUEID', 'MUTATION', 'GENE'], batch_size=250000)
    for batch_number, batch in enumerate(scanner.to_batches()):
        if batch_number % 40 == 0:
            print(f'Vocabulary pass: batch {batch_number}', flush=True)
        d = batch.to_pandas(ignore_metadata=True)
        d = d[d.UNIQUEID.isin(ids)]
        if d.empty: continue
        d = d.dropna(subset=['GENE', 'MUTATION'])
        d['feature'] = list(zip(d.GENE.astype(str), d.MUTATION.astype(str)))
        counts.update(d[['UNIQUEID', 'feature']].drop_duplicates().feature)
    vocab = sorted(counts)
    print(f'Vocabulary complete: {len(vocab)} features', flush=True)
    lookup = {v:i for i,v in enumerate(vocab)}
    row_lookup = {u:i for i,u in enumerate(samples.UNIQUEID)}
    rows, cols = [], []
    scanner = dataset.scanner(columns=['UNIQUEID', 'MUTATION', 'GENE'], batch_size=250000)
    for batch_number, batch in enumerate(scanner.to_batches()):
        if batch_number % 40 == 0:
            print(f'Matrix pass: batch {batch_number}', flush=True)
        d = batch.to_pandas(ignore_metadata=True)
        d = d[d.UNIQUEID.isin(ids)]
        if d.empty: continue
        d = d.dropna(subset=['GENE', 'MUTATION'])
        d['feature'] = list(zip(d.GENE.astype(str), d.MUTATION.astype(str)))
        d = d[['UNIQUEID', 'feature']].drop_duplicates()
        rows.append(d.UNIQUEID.map(row_lookup).to_numpy(dtype=np.int32))
        cols.append(np.fromiter((lookup[f] for f in d.feature), dtype=np.int32, count=len(d)))
    rows = np.concatenate(rows)
    cols = np.concatenate(cols)
    x = csr_matrix((np.ones(len(rows), dtype=np.uint32), (rows, cols)), shape=(len(samples), len(vocab)))
    x.data[:] = 1
    x = x.astype(np.uint8)
    del rows, cols
    present = np.diff(x.indptr) > 0
    samples.loc[~present].to_parquet(OUT / 'samples_without_features.parquet', index=False)
    samples = samples.loc[present].reset_index(drop=True)
    x = x[present]
    labels = labels.loc[labels.sample_accession.isin(samples.sample_accession)]
    assert samples.sample_accession.is_unique and samples.UNIQUEID.is_unique
    assert not labels.duplicated(['sample_accession', 'DRUG']).any()
    assert labels.target.isin([0, 1]).all() and np.all(x.data == 1)
    labels.to_parquet(OUT / 'labels.parquet', index=False)
    save_npz(OUT / 'mutation_features.npz', x)
    samples = samples.assign(matrix_row=np.arange(len(samples)))
    samples.to_parquet(OUT / 'samples.parquet', index=False)
    (OUT / 'feature_names.json').write_text(json.dumps(vocab, indent=2))
    label_counts = labels.groupby(['DRUG','target']).size().unstack(fill_value=0)
    label_counts.to_csv(OUT / 'label_counts.csv')
    report = {'samples': len(samples), 'features': len(vocab), 'nonzero_entries': int(x.nnz),
              'label_rows': len(labels), 'label_drugs': int(labels.DRUG.nunique()),
              'quarantined_mapping_rows': int(rejected.sum()), 'samples_without_features': int((~present).sum()),
              'validation': 'streamed two-pass mutation extraction; sparse matrix; one row per sample',
              'scope': 'TB genomic mutation feature construction; supervised split/model pending',
              'limitations': 'Descriptive all-sample vocabulary only. Predictive evaluation must derive vocabulary from training samples. No clinical prediction claim or external validation.'}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
