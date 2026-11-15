"""Group-bootstrap sensitivity of an anomaly-score ensemble.

The SVD representation stays fixed: this is not full-pipeline validation.
"""
import itertools
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from scipy.stats import spearmanr, rankdata
from sklearn.preprocessing import normalize
from sklearn.ensemble import IsolationForest
from threadpoolctl import threadpool_limits

BASE=Path(__file__).resolve().parents[1]/'data/processed/multispecies'


def main(species):
    base=BASE/species/'unsupervised_profiles'
    source=base/'anomaly_stability'
    out=base/'anomaly_resampling'
    out.mkdir(exist_ok=True)
    split=np.load(base/'grouped_representation_evaluation/sampled_rows.npz')
    tr,va=split['train'],split['validation']
    partition=pd.read_parquet(base/'grouped_representation_evaluation/group_partition.parquet')
    assert set(partition.iloc[tr].group).isdisjoint(partition.iloc[va].group)
    mask=np.load(source/'training_feature_mask.npy')
    x=load_npz(base/'features.npz').astype(np.float32)
    svd=joblib.load(source/'train_only_svd.joblib')
    a=svd.transform(normalize(x[tr][:,mask])); b=svd.transform(normalize(x[va][:,mask]))
    groups=partition.iloc[tr].group.to_numpy()
    unique=np.unique(groups)
    members={g:np.flatnonzero(groups==g) for g in unique}
    predictions=[]; sizes=[]
    with threadpool_limits(limits=4):
        for seed in [301,302,303,304,305]:
            chosen=np.random.default_rng(seed).choice(unique,len(unique),replace=True)
            rows=np.concatenate([members[g] for g in chosen])
            sizes.append(len(rows))
            forest=IsolationForest(n_estimators=500,max_samples=256,random_state=42,n_jobs=4,contamination='auto')
            forest.fit(a[rows])
            predictions.append(-forest.score_samples(b))
    scores=np.asarray(predictions)
    assert scores.shape==(5,len(va)) and np.isfinite(scores).all()
    pairs=[]
    for i,j in itertools.combinations(range(5),2):
        record={'run_a':i,'run_b':j,'spearman':float(spearmanr(scores[i],scores[j]).statistic)}
        for percent in [1,5]:
            n=max(1,int(np.ceil(len(va)*percent/100)))
            left=set(np.argsort(-scores[i],kind='stable')[:n]); right=set(np.argsort(-scores[j],kind='stable')[:n])
            record[f'top_{percent}pct_jaccard']=len(left&right)/len(left|right)
        pairs.append(record)
    ranks=np.asarray([rankdata(v,method='average')/len(v) for v in scores])
    audit=partition.iloc[va][['BioSample','matrix_row']].reset_index(drop=True)
    audit['mean_unusualness_score']=scores.mean(axis=0)
    audit['mean_percentile_rank']=ranks.mean(axis=0)
    audit['min_percentile_rank']=ranks.min(axis=0)
    audit['max_percentile_rank']=ranks.max(axis=0)
    audit['rank_range']=ranks.max(axis=0)-ranks.min(axis=0)
    audit.to_parquet(out/'sample_uncertainty.parquet',index=False)
    np.save(out/'bootstrap_scores.npy',scores)
    pd.DataFrame(pairs).to_csv(out/'pairwise_stability.csv',index=False)
    report={'species':species,'bootstrap_runs':5,'trees_per_run':500,'training_groups':len(unique),'resampled_training_row_counts':sizes,'validation_samples':len(va),'pairwise_spearman_range':[min(p['spearman'] for p in pairs),max(p['spearman'] for p in pairs)],'mean_top_1pct_jaccard':float(np.mean([p['top_1pct_jaccard'] for p in pairs])),'mean_top_5pct_jaccard':float(np.mean([p['top_5pct_jaccard'] for p in pairs])),'median_percentile_rank_range':float(np.median(audit.rank_range)),'limitations':'Five group-bootstrap development runs with fixed SVD and fixed forest seed. Rank ranges are empirical sensitivity ranges, not confidence intervals or anomaly probabilities. Training-only groups are resampled with replacement, including all sampled members. Full-pipeline uncertainty and biological validation remain unmeasured. No automatic anomaly threshold.'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    for name in ['escherichia_coli','acinetobacter_baumannii']: main(name)
