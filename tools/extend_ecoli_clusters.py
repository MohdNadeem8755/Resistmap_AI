"""Extend exploratory k search and audit group-resampling stability."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/multispecies/escherichia_coli/unsupervised_profiles'


def main():
    out = BASE / 'extended_cluster_audit'
    out.mkdir(exist_ok=True)
    z = np.load(BASE / 'normalized_comparison/embedding.npy')
    samples = pd.read_parquet(BASE / 'samples.parquet')
    assert samples.matrix_row.tolist() == list(range(len(z)))
    evaluation = np.load(BASE / 'clusters/selection_row_indices.npy')
    training = np.setdiff1d(np.arange(len(z)), evaluation)
    scores, models = [], {}
    with threadpool_limits(limits=4):
        for k in [8, 12, 16, 24, 32, 48, 64]:
            model = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=5, batch_size=4096).fit(z[training])
            pred = model.predict(z[evaluation])
            scores.append({'k': k, 'silhouette': float(silhouette_score(z[evaluation], pred)), 'evaluation_clusters': len(np.unique(pred))})
            models[k] = model
        best = max(scores, key=lambda r: r['silhouette'])
        model = models[best['k']]
        reference = model.predict(z[evaluation])
        # Components connect known SNP clusters, shared assemblies and identical
        # profiles. Missing clusters are not claims of biological independence.
        parent = np.arange(len(samples))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return int(i)
        for column in ['SNP cluster', 'Assembly', 'profile_hash']:
            seen = {}
            for i, value in enumerate(samples[column]):
                if pd.isna(value) or value == '':
                    continue
                if value in seen:
                    a, b = find(i), find(seen[value])
                    parent[max(a,b)] = min(a,b)
                else:
                    seen[value] = i
        groups = np.array([find(i) for i in range(len(samples))])
        # Exclude every group touching evaluation from group-resampling fits.
        eval_groups = np.unique(groups[evaluation])
        eligible = np.flatnonzero(~np.isin(groups, eval_groups))
        pool = np.unique(groups[eligible])
        stability = []
        if len(pool) >= 5 and len(eligible) > best['k']:
            for seed in [201, 202, 203, 204, 205]:
                chosen = np.random.default_rng(seed).choice(pool, max(1,int(.8*len(pool))), replace=False)
                rows = eligible[np.isin(groups[eligible], chosen)]
                assert not set(groups[rows]) & set(eval_groups)
                alt = MiniBatchKMeans(n_clusters=best['k'], random_state=42, n_init=5, batch_size=4096).fit(z[rows])
                stability.append({'seed': seed, 'fit_rows': len(rows), 'ari_vs_exploratory_reference': float(adjusted_rand_score(reference, alt.predict(z[evaluation])))})
        assignments = model.predict(z)
    pd.DataFrame(scores).to_csv(out / 'k_comparison.csv', index=False)
    pd.DataFrame(stability).to_csv(out / 'group_stability.csv', index=False)
    samples[['BioSample','matrix_row']].assign(cluster=assignments, audit_group=groups).to_parquet(out / 'assignments.parquet', index=False)
    joblib.dump(model, out / 'kmeans.joblib')
    # Descriptive metadata diagnostics: these are not causality tests.
    for col in ['AMRFinderPlus version', 'BioProject']:
        if col in samples:
            pd.crosstab(samples[col].fillna('missing'), assignments).to_csv(out / (col.replace(' ','_') + '_by_cluster.csv'))
    size = samples['AMR genotypes'].str.count(',').add(1)
    pd.DataFrame({'cluster': assignments, 'profile_size': size}).groupby('cluster').profile_size.agg(['count','mean','median','min','max']).to_csv(out / 'profile_size_by_cluster.csv')
    report = {'selected_k': best['k'], 'silhouette': best['silhouette'], 'search_boundary_selected': best['k']==max(r['k'] for r in scores), 'group_count': len(np.unique(groups)), 'group_resampling_pool_samples': len(eligible), 'evaluation_samples': len(evaluation), 'group_stability': stability, 'limitations': 'Exploratory all-data SVD retained; group resampling excludes known evaluation relatives but cannot certify phylogenetic independence. Reference k selected on reused evaluation rows. ARI also reflects the changed fitting population. Metadata cross-tabs require interpretation; no accuracy or causal claim.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
