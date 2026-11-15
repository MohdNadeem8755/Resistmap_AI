"""Direct sparse L2 clustering vs existing SVD, on fixed development groups."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.preprocessing import normalize
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score
from threadpoolctl import threadpool_limits

BASE=Path(__file__).resolve().parents[1]/'data/processed/multispecies/escherichia_coli/unsupervised_profiles'


def main():
    x=load_npz(BASE/'features.npz').astype(np.float32)
    split=np.load(BASE/'grouped_representation_evaluation/sampled_rows.npz')
    tr,va=split['train'],split['validation']
    freq=np.asarray(x[tr].sum(axis=0)).ravel()
    common=(freq>0)&(freq<len(tr))
    # Keep evaluation geometry fixed across filtering variants.
    v=x[va][:,common]
    dot=(v@v.T).toarray(); sizes=np.asarray(v.sum(axis=1)).ravel()
    union=sizes[:,None]+sizes[None,:]-dot
    distance=1-np.divide(dot,union,out=np.ones_like(dot),where=union>0)
    distance=np.clip(distance,0,1); np.fill_diagonal(distance,0)
    out=BASE/'sparse_clustering_comparison'
    out.mkdir(exist_ok=True)
    records=[]
    with threadpool_limits(limits=4):
        for minimum in [1,5,10]:
            mask=(freq>=minimum)&(freq<len(tr))
            a,b=normalize(x[tr][:,mask]),normalize(x[va][:,mask])
            zero=int((b.getnnz(axis=1)==0).sum())
            for k in [8,16,32,64]:
                model=MiniBatchKMeans(n_clusters=k,n_init=5,batch_size=4096,random_state=42).fit(a)
                labels=model.predict(b)
                score=float(silhouette_score(distance,labels,metric='precomputed')) if 1<len(np.unique(labels))<len(labels) else None
                stability=[]
                for seed in [43,44]:
                    alt=MiniBatchKMeans(n_clusters=k,n_init=5,batch_size=4096,random_state=seed).fit(a)
                    stability.append(float(adjusted_rand_score(labels,alt.predict(b))))
                records.append({'min_training_frequency':minimum,'features':int(mask.sum()),'k':k,'jaccard_silhouette':score,'seed_ari_mean':float(np.mean(stability)),'zero_validation_rows':zero,'evaluation_clusters':len(np.unique(labels))})
    pd.DataFrame(records).to_csv(out/'comparison.csv',index=False)
    best=max((r for r in records if r['jaccard_silhouette'] is not None and r['zero_validation_rows']==0),key=lambda r:r['jaccard_silhouette'])
    prior=pd.read_csv(BASE/'grouped_representation_evaluation/comparison.csv')
    report={'best_tested_direct_sparse':best,'previous_best_svd_jaccard_silhouette':float(prior.validation_jaccard_silhouette.max()),'train_rows':len(tr),'validation_rows':len(va),'selection_rule':'Maximum development Jaccard silhouette among variants with no zero validation rows. No automatic final-model promotion.','limitations':'Reused development validation samples; no independent test accuracy. MiniBatchKMeans on L2 rows is Euclidean clustering, not spherical k-means. Seed ARI measures initialization sensitivity only. Filtering may remove meaningful rare calls; raw matrix unchanged.'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__': main()
