"""Reproducible exploratory SVD; not preprocessing for supervised test scores."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.decomposition import TruncatedSVD
from threadpoolctl import threadpool_limits
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def run(species):
    source = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
    out = source / 'svd'
    out.mkdir(exist_ok=True)
    x = load_npz(source / 'features.npz').astype(np.float32)
    samples = pd.read_parquet(source / 'samples.parquet', columns=['BioSample', 'matrix_row'])
    assert samples.matrix_row.tolist() == list(range(x.shape[0]))
    n = min(32, x.shape[1] - 1, x.shape[0] - 1)
    model = TruncatedSVD(n_components=n, n_iter=7, random_state=42)
    with threadpool_limits(limits=4):
        z = model.fit_transform(x)
    assert z.shape == (len(samples), n) and np.isfinite(z).all()
    np.save(out / 'embedding.npy', z)
    joblib.dump(model, out / 'svd.joblib')
    samples.to_parquet(out / 'sample_order.parquet', index=False)
    explained = model.explained_variance_ratio_
    pd.DataFrame({'component': np.arange(1, n + 1), 'explained_variance': explained, 'cumulative_variance': np.cumsum(explained)}).to_csv(out / 'explained_variance.csv', index=False)
    rng = np.random.default_rng(42)
    subset = np.sort(rng.choice(len(z), min(20000, len(z)), replace=False))
    np.save(out / 'plotted_row_indices.npy', subset)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].scatter(z[subset, 0], z[subset, 1], s=3, alpha=.15, rasterized=True)
    axes[0].set(xlabel=f'SVD 1 ({explained[0]:.1%} variance)', ylabel=f'SVD 2 ({explained[1]:.1%} variance)', title=f'{species.replace("_", " ")} — {len(subset):,} plotted samples')
    axes[1].plot(np.arange(1, n + 1), np.cumsum(explained), marker='.', markersize=3)
    axes[1].set(xlabel='Components', ylabel='Cumulative explained variance', ylim=(0, 1), title='All retained samples used for fitting')
    fig.savefig(out / 'svd_overview.png', dpi=180)
    plt.close(fig)
    report = {'samples': len(z), 'input_features': x.shape[1], 'components': n, 'explained_variance': float(explained.sum()), 'two_dimensional_variance': float(explained[:2].sum()), 'plot_samples': len(subset), 'seed': 42, 'purpose': 'Descriptive exploration fitted to all retained profiles, including labeled samples. Do not reuse for independent supervised evaluation.', 'limitations': 'No cluster labels or resistance inference. Uncentered sparse SVD may reflect profile size and annotation differences. Dimensionality is a fixed exploratory choice, not optimized using phenotypes.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(species, json.dumps(report), flush=True)


if __name__ == '__main__':
    for name in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(name)
