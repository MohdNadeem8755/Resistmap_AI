"""Exploratory MiniBatchKMeans with label-free model selection and stability."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from threadpoolctl import threadpool_limits
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def run(species):
    base = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
    out = base / 'clusters'
    out.mkdir(exist_ok=True)
    z = np.load(base / 'svd/embedding.npy')
    samples = pd.read_parquet(base / 'svd/sample_order.parquet')
    assert len(samples) == len(z) and np.isfinite(z).all()
    rng = np.random.default_rng(42)
    # A reproducible independent sample for choosing k; no AST labels used.
    order = rng.permutation(len(z))
    eval_rows = order[:min(2000, len(z)//5)]
    fit_rows = order[len(eval_rows):]
    models, scores = {}, []
    with threadpool_limits(limits=4):
        for k in [2, 4, 8, 12, 16]:
            model = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=5, batch_size=4096)
            model.fit(z[fit_rows])
            pred = model.predict(z[eval_rows])
            score = float(silhouette_score(z[eval_rows], pred)) if 1 < len(np.unique(pred)) < len(pred) else None
            scores.append({'k': k, 'validation_silhouette': score})
            models[k] = model
        best = max((s for s in scores if s['validation_silhouette'] is not None), key=lambda s: s['validation_silhouette'])
        model = models[best['k']]
        reference = model.predict(z[eval_rows])
        stability = []
        for seed in [43, 44]:
            alt = MiniBatchKMeans(n_clusters=best['k'], random_state=seed, n_init=5, batch_size=4096).fit(z[fit_rows])
            stability.append({'seed': seed, 'adjusted_rand_index': float(adjusted_rand_score(reference, alt.predict(z[eval_rows])))})
        labels = model.predict(z)
    assignments = samples.copy()
    assignments['cluster'] = labels
    assignments.to_parquet(out / 'assignments.parquet', index=False)
    assert assignments.BioSample.is_unique and len(assignments) == len(z)
    assignments.cluster.value_counts().sort_index().rename_axis('cluster').rename('samples').to_csv(out / 'cluster_sizes.csv')
    pd.DataFrame(scores).to_csv(out / 'k_comparison.csv', index=False)
    np.save(out / 'selection_row_indices.npy', eval_rows)
    joblib.dump(model, out / 'kmeans.joblib')
    plotted = np.load(base / 'svd/plotted_row_indices.npy')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].scatter(z[plotted, 0], z[plotted, 1], c=labels[plotted], cmap='tab20', s=3, alpha=.35, vmin=0, vmax=max(1,best['k']-1))
    axes[0].set(xlabel='SVD 1', ylabel='SVD 2', title=f'{species.replace("_", " ")}: k={best["k"]}')
    sizes = np.bincount(labels, minlength=best['k'])
    axes[1].bar(np.arange(best['k']), sizes)
    axes[1].set(xlabel='Cluster', ylabel='Samples', title='All retained samples')
    fig.savefig(out / 'cluster_overview.png', dpi=180)
    plt.close(fig)
    report = {'samples': len(z), 'selected_k': best['k'], 'selection_silhouette': best['validation_silhouette'], 'seed_stability': stability, 'cluster_sizes': sizes.tolist(), 'fit_samples': len(fit_rows), 'selection_samples': len(eval_rows), 'scope': 'Exploratory clustering in 32-dimensional SVD space; no phenotype labels used.', 'limitations': 'SVD was fitted to all data; silhouette is a model-selection diagnostic, not independent generalization accuracy. Stability checks seed sensitivity only, not bootstrap robustness. Clusters are AMR-profile groups, not proven transmission chains or resistance classes.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(species, json.dumps(report), flush=True)


if __name__ == '__main__':
    for name in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(name)
