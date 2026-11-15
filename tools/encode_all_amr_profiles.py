"""Encode all valid species-specific AMR profiles for descriptive unsupervised work.

No phenotype data are used. This all-data vocabulary must not be reused as a
fitted preprocessing step for held-out supervised evaluation.
"""
import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz, load_npz

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=200000)
def parse(value):
    tokens = value.split(',')
    if any('=' not in t or not all(x.strip() for x in t.rsplit('=', 1)) for t in tokens):
        return None
    return tuple(sorted({t.strip() for t in tokens}))


def run(folder, filename, species):
    source = ROOT / 'data/multispecies' / folder / filename
    out = ROOT / 'data/processed/multispecies' / folder / 'unsupervised_profiles'
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(source, sep='\t', dtype='string', keep_default_na=False)
    df.columns = df.columns.str.lstrip('#')
    required = {'BioSample', 'Scientific name', 'AMR genotypes', 'Assembly', 'SNP cluster'}
    assert required <= set(df.columns)
    for col in df:
        df[col] = df[col].str.strip()
    input_rows = len(df)
    duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()
    reason = pd.Series('', index=df.index, dtype='string')
    reason.loc[~df['Scientific name'].str.match('^' + species + r'(?:\s|$)')] = 'species_mismatch'
    reason.loc[df.BioSample.eq('')] = 'missing_biosample'
    reason.loc[df['AMR genotypes'].eq('')] = 'missing_amr_profile'
    profiles = df['AMR genotypes'].map(parse)
    reason.loc[profiles.isna() & reason.eq('')] = 'malformed_amr_profile'
    df['canonical_profile'] = profiles.map(lambda x: ','.join(x) if x else '')
    # Multiple entries with distinct genomic metadata are not silently collapsed.
    valid = df.loc[reason.eq('')]
    signature = ['canonical_profile', 'Assembly', 'SNP cluster', 'Scientific name']
    if 'AMRFinderPlus version' in valid:
        signature.append('AMRFinderPlus version')
    ambiguous = valid.groupby('BioSample')[signature].nunique().gt(1).any(axis=1)
    bad_ids = set(ambiguous[ambiguous].index)
    reason.loc[df.BioSample.isin(bad_ids) & reason.eq('')] = 'ambiguous_biosample'
    excluded = df.loc[reason.ne('')].copy()
    excluded['exclusion_reason'] = reason[reason.ne('')]
    excluded.to_parquet(out / 'excluded.parquet', index=False)
    clean = df.loc[reason.eq('')].drop_duplicates('BioSample').sort_values('BioSample').reset_index(drop=True)
    parsed = [parse(v) for v in clean.canonical_profile]
    counts = Counter(t for p in parsed for t in p)
    vocab = sorted(counts)
    lookup = {t: i for i, t in enumerate(vocab)}
    indices, indptr = [], [0]
    for profile in parsed:
        indices.extend(sorted(lookup[t] for t in profile))
        indptr.append(len(indices))
    matrix = csr_matrix((np.ones(len(indices), dtype=np.uint8), np.asarray(indices, dtype=np.int32), np.asarray(indptr, dtype=np.int64)), shape=(len(clean), len(vocab)))
    clean['matrix_row'] = np.arange(len(clean))
    clean['profile_hash'] = [hashlib.sha256(v.encode()).hexdigest() for v in clean.canonical_profile]
    clean.drop(columns=['canonical_profile']).to_parquet(out / 'samples.parquet', index=False)
    save_npz(out / 'features.npz', matrix)
    (out / 'feature_names.json').write_text(json.dumps(vocab, indent=2), encoding='utf-8')
    pd.DataFrame({'feature': vocab, 'sample_count': [counts[t] for t in vocab]}).to_csv(out / 'feature_counts.csv', index=False)
    restored = load_npz(out / 'features.npz')
    assert restored.shape == matrix.shape and (restored != matrix).nnz == 0
    assert clean.BioSample.is_unique and len(clean) == matrix.shape[0]
    assert np.array_equal(np.asarray(matrix.sum(axis=1)).ravel(), [len(p) for p in parsed])
    assert np.array_equal(np.asarray(matrix.sum(axis=0)).ravel(), [counts[t] for t in vocab])
    report = {'source': str(source), 'input_rows': input_rows, 'exact_duplicate_rows': duplicates, 'exclusion_rows': reason[reason.ne('')].value_counts().to_dict(), 'ambiguous_biosamples': len(bad_ids), 'encoded_samples': len(clean), 'features': len(vocab), 'nonzero_entries': matrix.nnz, 'unique_profiles': int(clean.profile_hash.nunique()), 'retained_constant_features': sum(v == len(clean) for v in counts.values()), 'validation': 'roundtrip, binary matrix, unique BioSamples, row and column sums passed', 'scope': 'descriptive all-data unsupervised encoding; no clustering or training performed', 'interpretation': 'Features preserve gene/mutation and detection status as separate tokens. Blank profiles excluded as unknown. Absence means not reported by this annotation, not proven biological absence.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
    parse.cache_clear()


if __name__ == '__main__':
    run('escherichia_coli', 'ecoli_isolates.tsv', 'Escherichia coli')
    run('acinetobacter_baumannii', 'abaumannii_isolates.tsv', 'Acinetobacter baumannii')
