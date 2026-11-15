"""Development-only Isolation Forest stability and annotation-quality audit.

No phenotype labels, resistance inference, or removal of unusual records.
Fit vocabulary, SVD and forests only on the fixed grouped training sample.
"""
import hashlib
import itertools
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from scipy.stats import spearmanr
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import normalize
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [42, 43, 44]


def correlation(a, b):
    if len(np.unique(a)) < 2 or len(np.unique(b)) < 2:
        return None
    return float(spearmanr(a, b).statistic)


def run(species):
    base = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
    source = base / 'grouped_representation_evaluation'
    out = base / 'anomaly_stability'
    out.mkdir(exist_ok=True)
    split_path = source / 'sampled_rows.npz'
    split = np.load(split_path)
    train, val = split['train'], split['validation']
    samples = pd.read_parquet(base / 'samples.parquet')
    partition = pd.read_parquet(source / 'group_partition.parquet')
    assert samples.BioSample.equals(partition.BioSample)
    assert samples.matrix_row.tolist() == list(range(len(samples)))
    assert set(train).isdisjoint(val)
    assert set(partition.iloc[train].group).isdisjoint(partition.iloc[val].group)
    x = load_npz(base / 'features.npz').astype(np.float32)
    names = json.loads((base / 'feature_names.json').read_text())
    assert x.shape == (len(samples), len(names))
    freq = np.asarray(x[train].sum(axis=0)).ravel()
    mask = (freq > 0) & (freq < len(train))
    assert np.array_equal(mask, split['training_feature_mask'])
    a, b = normalize(x[train][:, mask]), normalize(x[val][:, mask])
    with threadpool_limits(limits=4):
        svd = TruncatedSVD(n_components=min(32, a.shape[1]-1), n_iter=7, random_state=42)
        ztr = svd.fit_transform(a)
        zv = svd.transform(b)
        assert np.isfinite(ztr).all() and np.isfinite(zv).all()
        scores = []
        for seed in SEEDS:
            forest = IsolationForest(n_estimators=200, max_samples=256, contamination='auto', random_state=seed, n_jobs=4)
            forest.fit(ztr)
            # Larger values mean more unusual; no binary anomaly threshold used.
            scores.append(-forest.score_samples(zv))
            joblib.dump(forest, out / f'forest_seed_{seed}.joblib')
    scores = np.asarray(scores)
    assert scores.shape == (len(SEEDS), len(val)) and np.isfinite(scores).all()
    pairs = []
    for i, j in itertools.combinations(range(len(SEEDS)), 2):
        item = {'seed_a': SEEDS[i], 'seed_b': SEEDS[j], 'spearman': correlation(scores[i], scores[j])}
        for pct in [1, 5]:
            count = max(1, int(np.ceil(len(val)*pct/100)))
            # Stable row-order tie breaking; rank fractions are diagnostics only.
            left = set(np.argsort(-scores[i], kind='stable')[:count])
            right = set(np.argsort(-scores[j], kind='stable')[:count])
            item[f'top_{pct}pct_jaccard'] = len(left & right)/len(left | right)
        pairs.append(item)
    mean = scores.mean(axis=0)
    size = np.asarray(x[val].sum(axis=1)).ravel()
    partial_mask = np.array(['PARTIAL' in n.rsplit('=', 1)[1] for n in names])
    partial = np.asarray(x[val][:, partial_mask].sum(axis=1)).ravel()
    unseen = np.asarray(x[val][:, freq == 0].sum(axis=1)).ravel()
    audit = samples.iloc[val][['BioSample', 'matrix_row', 'AMRFinderPlus version', 'BioProject']].reset_index(drop=True)
    for i, seed in enumerate(SEEDS):
        audit[f'score_seed_{seed}'] = scores[i]
    audit['mean_unusualness_score'] = mean
    audit['score_std_across_seeds'] = scores.std(axis=0)
    audit['profile_size'] = size
    audit['partial_call_fraction'] = partial/np.maximum(size, 1)
    audit['unseen_training_calls'] = unseen
    audit['zero_retained_features'] = b.getnnz(axis=1) == 0
    audit.to_parquet(out / 'validation_score_audit.parquet', index=False)
    for col in ['AMRFinderPlus version', 'BioProject']:
        audit.groupby(col, dropna=False).mean_unusualness_score.agg(['count', 'mean', 'median']).to_csv(out / (col.replace(' ', '_') + '_score_summary.csv'))
    pd.DataFrame(pairs).to_csv(out / 'seed_stability.csv', index=False)
    joblib.dump(svd, out / 'train_only_svd.joblib')
    np.save(out / 'training_feature_mask.npy', mask)
    # Reload verifies artifacts and preserves row mapping.
    check = pd.read_parquet(out / 'validation_score_audit.parquet')
    assert check.BioSample.tolist() == samples.iloc[val].BioSample.tolist()
    restored = joblib.load(out / 'forest_seed_42.joblib')
    assert np.allclose(-restored.score_samples(zv[:20]), scores[0, :20])
    report = {'species': species, 'training_samples': len(train), 'evaluated_samples': len(val), 'training_features': int(mask.sum()), 'known_group_overlap': 0, 'seed_pairs': pairs, 'annotation_associations_spearman': {'profile_size': correlation(mean, size), 'partial_call_fraction': correlation(mean, partial/np.maximum(size, 1)), 'unseen_training_calls': correlation(mean, unseen)}, 'zero_retained_feature_samples': int(audit.zero_retained_features.sum()), 'partition_sha256': hashlib.sha256(split_path.read_bytes()).hexdigest(), 'validation_checks': 'group isolation, train-only feature mask, finite scores, row mapping and model reload passed', 'limitations': 'Previously explored grouped development data, not a fresh test. Seed agreement is repeatability, not anomaly accuracy. SVD is fixed across forests and may discard rare variation. Version/project summaries are descriptive. Top 1%/5% sets are only stability diagnostics, not biological thresholds. No phenotype interpretation, alerts or sample deletion.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
