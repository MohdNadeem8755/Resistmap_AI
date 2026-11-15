"""Compare exploratory raw and L2-normalized profiles without using AST labels."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from scipy.sparse import load_npz
from sklearn.preprocessing import normalize
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]


def run(species):
    base = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
    out = base / 'normalized_comparison'
    out.mkdir(exist_ok=True)
    x = load_npz(base / 'features.npz').astype(np.float32)
    totals = np.asarray(x.sum(axis=1)).ravel()
    xn = normalize(x, norm='l2')
    assert np.allclose(np.asarray(xn.multiply(xn).sum(axis=1)).ravel(), 1, atol=1e-5)
    evaluation = np.load(base / 'clusters/selection_row_indices.npy')
    training = np.setdiff1d(np.arange(x.shape[0]), evaluation)
    baseline = pd.read_parquet(base / 'clusters/assignments.parquet')
    samples = pd.read_parquet(base / 'svd/sample_order.parquet')
    assert baseline.BioSample.equals(samples.BioSample)
    with threadpool_limits(limits=4):
        svd = TruncatedSVD(n_components=32, n_iter=7, random_state=42)
        z = svd.fit_transform(xn)
        assert np.isfinite(z).all()
        models, comparison = {}, []
        for k in [2, 4, 8, 12, 16]:
            model = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=5, batch_size=4096).fit(z[training])
            pred = model.predict(z[evaluation])
            score = float(silhouette_score(z[evaluation], pred))
            models[k] = model
            comparison.append({'k': k, 'svd_silhouette': score})
        best = max(comparison, key=lambda r: r['svd_silhouette'])
        model = models[best['k']]
        pred = model.predict(z[evaluation])
        stability = []
        for seed in [43, 44]:
            alt = MiniBatchKMeans(n_clusters=best['k'], random_state=seed, n_init=5, batch_size=4096).fit(z[training])
            stability.append(float(adjusted_rand_score(pred, alt.predict(z[evaluation]))))
        bootstrap = []
        for seed in [101, 102, 103, 104, 105]:
            draw = np.random.default_rng(seed).choice(training, len(training), replace=True)
            alt = MiniBatchKMeans(n_clusters=best['k'], random_state=42, n_init=5, batch_size=4096).fit(z[draw])
            bootstrap.append(float(adjusted_rand_score(pred, alt.predict(z[evaluation]))))
        # Compare both assignments using the SAME original normalized feature space.
        raw_cosine = float(silhouette_score(xn[evaluation], baseline.cluster.to_numpy()[evaluation], metric='cosine'))
        norm_cosine = float(silhouette_score(xn[evaluation], pred, metric='cosine'))
        labels = model.predict(z)
    samples['cluster'] = labels
    samples.to_parquet(out / 'assignments.parquet', index=False)
    np.save(out / 'embedding.npy', z)
    joblib.dump(svd, out / 'svd.joblib')
    joblib.dump(model, out / 'kmeans.joblib')
    pd.DataFrame(comparison).to_csv(out / 'k_comparison.csv', index=False)
    samples.cluster.value_counts().sort_index().to_csv(out / 'cluster_sizes.csv')
    report = {'samples': len(z), 'selected_k': best['k'], 'svd_silhouette': best['svd_silhouette'], 'variance_retained': float(svd.explained_variance_ratio_.sum()), 'seed_ari': stability, 'bootstrap_ari': bootstrap, 'bootstrap_ari_mean': float(np.mean(bootstrap)), 'same_space_cosine_silhouette': {'raw_baseline_assignments': raw_cosine, 'normalized_assignments': norm_cosine}, 'profile_size_correlation_svd1_svd2': [float(np.corrcoef(totals,z[:,i])[0,1]) for i in range(2)], 'limitations': 'Exploratory selection, not independent accuracy: all-data SVD, reused selection samples, and fixed representation in bootstrap. Normalization does not remove all annotation or profile-size effects. Original baseline preserved; no automatic promotion of a winner.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(species, json.dumps(report), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
