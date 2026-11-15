"""Bootstrap stability of exploratory clusters, without phenotype labels."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]


def run(species):
    base = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
    out = base / 'clusters'
    z = np.load(base / 'svd/embedding.npy')
    eval_rows = np.load(out / 'selection_row_indices.npy')
    fit_rows = np.setdiff1d(np.arange(len(z)), eval_rows)
    model = joblib.load(out / 'kmeans.joblib')
    reference = model.predict(z[eval_rows])
    results, predictions = [], []
    with threadpool_limits(limits=4):
        for seed in [101, 102, 103, 104, 105]:
            rng = np.random.default_rng(seed)
            # Resample only the original fitting pool; leave evaluation fixed.
            rows = rng.choice(fit_rows, size=len(fit_rows), replace=True)
            candidate = MiniBatchKMeans(n_clusters=model.n_clusters, random_state=42, n_init=5, batch_size=4096).fit(z[rows])
            pred = candidate.predict(z[eval_rows])
            predictions.append(pred)
            results.append({'bootstrap_seed': seed, 'ari_vs_original': float(adjusted_rand_score(reference, pred)), 'nmi_vs_original': float(normalized_mutual_info_score(reference, pred)), 'evaluation_clusters_present': len(np.unique(pred))})
    pairwise = [float(adjusted_rand_score(predictions[i], predictions[j])) for i in range(len(predictions)) for j in range(i)]
    pd.DataFrame(results).to_csv(out / 'bootstrap_stability.csv', index=False)
    np.save(out / 'bootstrap_evaluation_assignments.npy', np.stack(predictions))
    values = [r['ari_vs_original'] for r in results]
    # Profile size can explain geometry unrelated to biology: record confounding.
    from scipy.sparse import load_npz
    x = load_npz(base / 'features.npz')
    totals = np.asarray(x.sum(axis=1)).ravel()
    correlations = [float(np.corrcoef(totals, z[:, i])[0, 1]) for i in range(2)]
    summary = {'species': species, 'k': model.n_clusters, 'bootstrap_runs': len(results), 'ari_vs_original_mean': float(np.mean(values)), 'ari_vs_original_range': [min(values), max(values)], 'pairwise_bootstrap_ari_mean': float(np.mean(pairwise)), 'profile_size_correlation_svd1_svd2': correlations, 'scope': 'Five bootstrap fits with fixed initialization seed, fixed SVD representation and fixed evaluation rows. Labels unused. Original models unchanged.', 'limitations': 'This tests sample-resampling sensitivity, not biological validation or stability of the entire SVD pipeline. Shared related isolates can affect this descriptive diagnostic. No confidence interval or significance claim.'}
    (out / 'robustness_report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
