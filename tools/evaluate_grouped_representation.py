"""Group-disjoint development comparison with train-only SVD.

Existing data have been explored previously: this is not a fresh external test.
"""
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.preprocessing import normalize
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]/'data/processed/multispecies'


def run(species):
    base=ROOT/species/'unsupervised_profiles'
    out=base/'grouped_representation_evaluation'
    out.mkdir(exist_ok=True)
    samples=pd.read_parquet(base/'samples.parquet')
    x=load_npz(base/'features.npz').astype(np.float32)
    assert len(samples)==x.shape[0]
    parent=list(range(len(samples)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    for col in ['SNP cluster','Assembly','profile_hash']:
        seen={}
        for i,v in enumerate(samples[col]):
            if pd.isna(v) or v=='': continue
            if v in seen:
                a,b=find(i),find(seen[v]); parent[max(a,b)]=min(a,b)
            else: seen[v]=i
    groups=np.array([find(i) for i in range(len(samples))])
    unique=np.unique(groups)
    valgroups={int(g) for g in unique if int(hashlib.sha256(('group-dev-v1|'+species+'|'+str(samples.iloc[g].BioSample)).encode()).hexdigest()[:8],16)/2**32>=.8}
    held=np.array([g in valgroups for g in groups])
    rng=np.random.default_rng(73)
    trpool=np.flatnonzero(~held); vapool=np.flatnonzero(held)
    train=np.sort(rng.choice(trpool,min(30000,len(trpool)),replace=False))
    val=np.sort(rng.choice(vapool,min(1500,len(vapool)),replace=False))
    assert not set(groups[train]) & set(groups[val])
    # Vocabulary restriction is derived from training rows only.
    freq=np.asarray(x[train].sum(axis=0)).ravel()
    mask=(freq>0)&(freq<len(train))
    xx=x[:,mask]
    xv=xx[val]
    intersections=(xv@xv.T).toarray()
    sizes=np.asarray(xv.sum(axis=1)).ravel()
    unions=sizes[:,None]+sizes[None,:]-intersections
    distances=1-np.divide(intersections,unions,out=np.ones_like(intersections),where=unions>0)
    distances=np.clip(distances,0,1); np.fill_diagonal(distances,0)
    results=[]
    with threadpool_limits(limits=4):
        for representation in ['binary','l2_normalized']:
            a=xx[train]; b=xx[val]
            if representation=='l2_normalized': a,b=normalize(a),normalize(b)
            svd=TruncatedSVD(n_components=min(32,a.shape[1]-1),n_iter=7,random_state=42)
            ztr=svd.fit_transform(a); zv=svd.transform(b)
            assert np.isfinite(zv).all()
            for k in [8,16,32,64]:
                model=MiniBatchKMeans(n_clusters=k,n_init=5,batch_size=4096,random_state=42).fit(ztr)
                labels=model.predict(zv)
                score=float(silhouette_score(distances,labels,metric='precomputed')) if 1<len(np.unique(labels))<len(labels) else None
                results.append({'representation':representation,'k':k,'validation_jaccard_silhouette':score,'clusters_present':len(np.unique(labels))})
    pd.DataFrame(results).to_csv(out/'comparison.csv',index=False)
    samples[['BioSample','matrix_row']].assign(group=groups,development_partition=np.where(held,'validation','train')).to_parquet(out/'group_partition.parquet',index=False)
    np.savez(out/'sampled_rows.npz',train=train,validation=val,training_feature_mask=mask)
    report={'species':species,'training_samples_used':len(train),'validation_samples_used':len(val),'features_seen_in_training':int(mask.sum()),'known_group_overlap':0,'results':results,'limitations':'Previously explored data; development comparison only. Subsampled for bounded computation. Group links cover known SNP clusters, shared assemblies and identical profiles, not all phylogenetic relationships. Same Jaccard geometry used to compare all assignments. No model promoted or final accuracy claimed.'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    for species in ['escherichia_coli','acinetobacter_baumannii']: run(species)
