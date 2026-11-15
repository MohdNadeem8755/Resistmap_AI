"""Deterministic development splits and sparse genomic encoding.

Known SNP clusters, shared assemblies and identical AMR profiles stay together.
These controls do not prove absence of broader phylogenetic relationships.
"""
import hashlib
import json
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz

ROOT = Path(__file__).resolve().parents[1] / 'data/processed/multispecies'


def calls(value):
    tokens = set()
    for token in value.split(','):
        token = token.strip()
        if '=' not in token:
            raise ValueError('Unrecognized AMR token: ' + token)
        tokens.add(token)
    return tuple(sorted(tokens))


def process(species):
    base = ROOT / species
    out = base / 'encoded'
    out.mkdir(exist_ok=True)
    labels = pd.read_parquet(base / 'feature_candidates.parquet')
    samples = labels.drop_duplicates('BioSample').sort_values('BioSample').reset_index(drop=True)
    assert labels.groupby('BioSample')['AMR genotypes'].nunique().max() == 1
    profiles = [calls(v) for v in samples['AMR genotypes']]
    parent = list(range(len(samples)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    seen = {}
    for i, row in samples.iterrows():
        keys = [('cluster', row['SNP cluster']), ('profile', profiles[i])]
        if pd.notna(row.Assembly):
            keys.append(('assembly', row.Assembly))
        for key in keys:
            if key in seen:
                union(i, seen[key])
            else:
                seen[key] = i
    groups = [str(samples.iloc[find(i)].BioSample) for i in range(len(samples))]

    def assign(group):
        value = int(hashlib.sha256(('resistmap-v1|' + species + '|' + group).encode()).hexdigest()[:8], 16) / 2**32
        return 'train' if value < .7 else ('validation' if value < .85 else 'test')

    samples['group_id'] = groups
    samples['split'] = [assign(g) for g in groups]
    samples['matrix_row'] = np.arange(len(samples))
    counts = Counter(t for i, tokens in enumerate(profiles) if samples.iloc[i]['split'] == 'train' for t in tokens)
    ntrain = int(samples.split.eq('train').sum())
    assert ntrain > 0
    vocab = sorted(t for t, n in counts.items() if 0 < n < ntrain)
    lookup = {t: i for i, t in enumerate(vocab)}
    rows, cols, unknown = [], [], []
    for i, tokens in enumerate(profiles):
        unknown.append(sum(t not in counts for t in tokens))
        for token in tokens:
            if token in lookup:
                rows.append(i)
                cols.append(lookup[token])
    matrix = csr_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(len(samples), len(vocab)))
    save_npz(out / 'genomic_features.npz', matrix)
    samples['unseen_train_tokens'] = unknown
    samples[['BioSample', 'group_id', 'split', 'matrix_row', 'unseen_train_tokens']].to_csv(out / 'samples.csv', index=False)
    (out / 'feature_names.json').write_text(json.dumps(vocab, indent=2), encoding='utf-8')
    targets = labels[['BioSample', 'Antibiotic', 'Testing standard', 'target']].drop_duplicates().merge(samples[['BioSample', 'split', 'matrix_row', 'group_id']], on='BioSample', validate='many_to_one')
    assert not targets.duplicated(['BioSample', 'Antibiotic', 'Testing standard']).any()
    targets.to_parquet(out / 'targets.parquet', index=False)
    balance = targets.groupby(['Antibiotic', 'Testing standard', 'split', 'target']).size().unstack(fill_value=0).reindex(columns=[0, 1], fill_value=0)
    balance.columns = ['susceptible', 'resistant']
    balance.to_csv(out / 'split_class_counts.csv')
    weights = []
    for (drug, standard), d in targets.loc[targets.split.eq('train')].groupby(['Antibiotic', 'Testing standard']):
        c = d.target.value_counts()
        weights.append({'antibiotic': drug, 'standard': standard, 'both_classes_in_training': len(c) == 2, 'weight_s': len(d)/(2*c[0]) if 0 in c else None, 'weight_r': len(d)/(2*c[1]) if 1 in c else None})
    pd.DataFrame(weights).to_csv(out / 'training_class_weights.csv', index=False)
    for col in ['SNP cluster', 'Assembly']:
        assert samples.dropna(subset=[col]).groupby(col).split.nunique().max() == 1
    assert samples.groupby('group_id').split.nunique().max() == 1
    eligible = []
    for (drug, standard), d in targets.groupby(['Antibiotic', 'Testing standard']):
        c = d.groupby(['split', 'target']).size()
        enough = all(c.get((s, y), 0) >= 10 for s in ['train', 'validation', 'test'] for y in [0, 1])
        eligible.append({'antibiotic': drug, 'standard': standard, 'at_least_10_per_class_each_split': enough})
    pd.DataFrame(eligible).to_csv(out / 'task_eligibility.csv', index=False)
    report = {'samples': len(samples), 'features': len(vocab), 'groups': len(set(groups)), 'split_samples': samples.split.value_counts().to_dict(), 'largest_group': int(samples.groupby('group_id').size().max()), 'eligible_drug_standard_tasks': sum(x['at_least_10_per_class_each_split'] for x in eligible), 'checks': 'BioSample, known cluster, assembly and identical-profile separation passed', 'limitations': 'Cluster-missing samples excluded from this development subset; no full phylogenetic independence certification. Sparse binary features need no scaling or PCA. Validation/test were not resampled. No model trained.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(species, json.dumps(report))


if __name__ == '__main__':
    for name in ['escherichia_coli', 'acinetobacter_baumannii']:
        process(name)
