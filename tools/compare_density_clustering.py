"""Bounded exploratory HDBSCAN audit on training-only profiles.

No prediction or independent validation claim; coverage reported with silhouette.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.preprocessing import normalize
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import HDBSCAN
from sklearn.metrics import silhouette_score
from threadpoolctl import threadpool_limits

BASE=Path(__file__).resolve().parents[1]/'data/processed/multispecies/escherichia_coli/unsupervised_profiles'


def main():
    x=load_npz(BASE/'features.npz').astype(np.float32)
    rows=np.load(BASE/'grouped_representation_evaluation/sampled_rows.npz')['train']
    # Unique profiles reduce repeated clone sampling effects in density estimation.
    meta=pd.read_parquet(BASE/'samples.parquet').iloc[rows]
    unique=meta.drop_duplicates('profile_hash')
    rng=np.random.default_rng(57)
    if len(unique)>8000:
        unique=unique.iloc[np.sort(rng.choice(len(unique),8000,replace=False))]
    selected=unique.matrix_row.to_numpy()
    a=x[selected]
    freq=np.asarray(a.sum(axis=0)).ravel()
    mask=(freq>0)&(freq<len(selected))
    a=a[:,mask]
    out=BASE/'density_comparison'
    out.mkdir(exist_ok=True)
    audit=np.sort(rng.choice(len(selected),min(1500,len(selected)),replace=False))
    v=a[audit]; dot=(v@v.T).toarray(); n=np.asarray(v.sum(axis=1)).ravel()
    union=n[:,None]+n[None,:]-dot
    dist=1-np.divide(dot,union,out=np.ones_like(dot),where=union>0)
    dist=np.clip(dist,0,1); np.fill_diagonal(dist,0)
    summaries=[]
    with threadpool_limits(limits=4):
        model=TruncatedSVD(n_components=min(32,a.shape[1]-1),random_state=42,n_iter=7)
        z=model.fit_transform(normalize(a))
        assignments=unique[['BioSample','matrix_row','profile_hash']].reset_index(drop=True)
        for minimum in [20,50,100]:
            h=HDBSCAN(min_cluster_size=minimum,min_samples=10,n_jobs=4)
            labels=h.fit_predict(z)
            chosen=labels[audit]; clustered=chosen>=0
            score=None
            if 1<len(np.unique(chosen[clustered]))<int(clustered.sum()):
                score=float(silhouette_score(dist[np.ix_(clustered,clustered)],chosen[clustered],metric='precomputed'))
            assignments['cluster_min_'+str(minimum)]=labels
            summaries.append({'min_cluster_size':minimum,'clusters':len(set(labels)-{-1}),'noise_fraction':float(np.mean(labels<0)),'audit_clustered_samples':int(clustered.sum()),'jaccard_silhouette_clustered_only':score})
    assert assignments.BioSample.is_unique and np.isfinite(z).all()
    assignments.to_parquet(out/'assignments.parquet',index=False)
    np.savez(out/'audit_rows.npz',source_rows=selected,audit_positions=audit)
    report={'profiles_used':len(selected),'unique_training_profiles_available':int(meta.profile_hash.nunique()),'results':summaries,'scope':'Density clustering feasibility on up to 8000 unique training profiles. All held-out validation rows excluded. Clustered-only silhouette is an internal diagnostic and must be interpreted alongside noise coverage.','limitations':'Different subset and weighting from prior KMeans; scores are not a controlled head-to-head improvement estimate. SVD can distort density. No held-out predictions, full-data labels, resistance claims or production model.'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__': main()
