"""Descriptive cluster resolution and confounding audit; no phenotype tuning."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score, adjusted_mutual_info_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1] / 'data/processed/multispecies'


def bias(species, assignment_dir):
    base = ROOT / species / 'unsupervised_profiles'
    samples = pd.read_parquet(base / 'samples.parquet')
    assignments = pd.read_parquet(base / assignment_dir / 'assignments.parquet')
    assert samples.BioSample.equals(assignments.BioSample)
    labels = assignments.cluster.to_numpy()
    size = np.asarray(load_npz(base / 'features.npz').sum(axis=1)).ravel().astype(float)
    table = pd.DataFrame({'cluster':labels,'size':size})
    stats = table.groupby('cluster')['size'].agg(['size','mean'])
    total = float(np.sum((size-size.mean())**2))
    eta = float(np.sum(stats['size']*(stats['mean']-size.mean())**2)/total) if total else 0.0
    # Fixed sample limits high-cardinality metadata computations.
    idx = np.sort(np.random.default_rng(73).choice(len(labels),min(20000,len(labels)),replace=False))
    meta = {}
    for col in ['AMRFinderPlus version','BioProject']:
        if col not in samples:
            continue
        values = samples[col].fillna('').astype(str)
        good = idx[values.iloc[idx].ne('').to_numpy()]
        n = values.iloc[good].nunique()
        meta[col] = {'known_sampled_rows':len(good),'distinct_values':int(n),'adjusted_mutual_information':float(adjusted_mutual_info_score(labels[good],values.iloc[good])) if len(good)>1 and n>1 else None}
    report = {'species':species,'profile_size_eta_squared':eta,'metadata_association':meta,'interpretation':'Eta squared is the fraction of reported profile-size variance between clusters, not a causal effect. AMI assesses association with metadata categories; multi-project strings are treated as categories. A constant version cannot test batch effects.'}
    out = base / 'bias_audit'
    out.mkdir(exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


def extend():
    base = ROOT/'escherichia_coli/unsupervised_profiles'
    z = np.load(base/'normalized_comparison/embedding.npy')
    evaluation = np.load(base/'clusters/selection_row_indices.npy')
    training = np.setdiff1d(np.arange(len(z)),evaluation)
    records = []
    with threadpool_limits(limits=4):
        for k in [64,96,128]:
            model=MiniBatchKMeans(n_clusters=k,random_state=42,n_init=5,batch_size=4096).fit(z[training])
            pred=model.predict(z[evaluation])
            sizes=np.bincount(model.predict(z),minlength=k)
            records.append({'k':k,'silhouette':float(silhouette_score(z[evaluation],pred)),'clusters_represented_in_evaluation':len(np.unique(pred)),'smallest_cluster':int(sizes.min()),'largest_cluster':int(sizes.max()),'clusters_below_100_samples':int((sizes<100).sum())})
    out=base/'resolution_audit'
    out.mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv(out/'k_comparison.csv',index=False)
    (out/'report.json').write_text(json.dumps({'results':records,'limitations':'Same reused selection rows and all-data SVD. Higher silhouette at larger k does not establish biological clusters. No automatic replacement of existing assignments; an untouched grouped evaluation is still required.'},indent=2),encoding='utf-8')
    print(json.dumps(records),flush=True)


if __name__=='__main__':
    extend()
    bias('escherichia_coli','extended_cluster_audit')
    bias('acinetobacter_baumannii','normalized_comparison')
