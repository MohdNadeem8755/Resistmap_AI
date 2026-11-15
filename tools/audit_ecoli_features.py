"""Feature-quality diagnostics for the fixed grouped development sample."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import load_npz

BASE=Path(__file__).resolve().parents[1]/'data/processed/multispecies/escherichia_coli/unsupervised_profiles'


def main():
    x=load_npz(BASE/'features.npz')
    names=json.loads((BASE/'feature_names.json').read_text())
    split=np.load(BASE/'grouped_representation_evaluation/sampled_rows.npz')
    train,val=split['train'],split['validation']
    freq=np.asarray(x[train].sum(axis=0)).ravel()
    vf=np.asarray(x[val].sum(axis=0)).ravel()
    status=[n.rsplit('=',1)[1] for n in names]
    out=BASE/'feature_quality_audit'
    out.mkdir(exist_ok=True)
    pd.DataFrame({'feature':names,'status':status,'train_count':freq,'validation_count':vf}).to_csv(out/'feature_support.csv',index=False)
    unseen=np.asarray(x[val][:,freq==0].sum(axis=1)).ravel()
    total=np.asarray(x[val].sum(axis=1)).ravel()
    retained=total-unseen
    partial=np.array(['PARTIAL' in s for s in status])
    count=np.asarray(x.sum(axis=1)).ravel()
    report={'total_features':x.shape[1],'training_sample_count':len(train),'validation_sample_count':len(val),'feature_status_counts':dict(Counter(status)),'features_absent_in_training':int((freq==0).sum()),'features_in_1_to_4_training_samples':int(((freq>0)&(freq<5)).sum()),'validation_samples_with_unseen_features':int((unseen>0).sum()),'validation_samples_with_no_training_seen_features':int((retained==0).sum()),'validation_unseen_call_fraction':float(unseen.sum()/total.sum()),'samples_with_partial_calls':int((np.asarray(x[:,partial].sum(axis=1)).ravel()>0).sum()),'profile_size_quantiles':{str(q):float(np.quantile(count,q)) for q in [0,.25,.5,.75,.95,.99,1]},'interpretation':'Rare and unseen calls can affect representation; partial calls are annotation evidence, not automatically errors. This audit alone does not establish the cause of weak cluster separation. Raw data and fixed partitions unchanged.'}
    assert len(names)==x.shape[1] and np.all(retained>=0)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__': main()
