import csv, json, hashlib
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
RUN = ROOT / 'results/ceftazidime_v2_20261001T202849_616568Z'
def rows(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))
split = rows(ROOT/'results/ceftazidime_clsi_split_v2.csv')
oof = [r for r in rows(RUN/'development_oof_probabilities.csv') if r['candidate']=='RF_leaf_4']
assert len(oof)==445 and len({r['BioSample'] for r in oof})==445
assert {r['BioSample'] for r in oof}=={r['BioSample'] for r in split if r['partition']=='train'}
folds=[]
for k in ('1','2','3'):
    rr=[r for r in oof if r['fold']==k]
    counts=Counter((int(r['actual']),int(float(r['probability_R'])>=0.4)) for r in rr)
    tn,fp,fn,tp=[counts[x] for x in ((0,0),(0,1),(1,0),(1,1))]
    s,r=tn/(tn+fp),tp/(tp+fn)
    folds.append(dict(fold=k,n=len(rr),TN=tn,FP=fp,FN=fn,TP=tp,BA=(s+r)/2,S_recall=s,R_recall=r,accuracy=(tn+tp)/len(rr)))
saved=rows(RUN/'selected_development_folds.csv')
for a,b in zip(folds,saved):
    assert abs(a['BA']-float(b['balanced_accuracy']))<1e-12
baseline=defaultdict(list)
for r in rows(ROOT/'results/ceftazidime_grouped_cv.csv'):
    baseline[r['model']].append(r)
means={name:{metric:mean(float(r[metric]) for r in rr) for metric in ('accuracy','balanced_accuracy','susceptible_recall','resistant_recall','roc_auc')} for name,rr in baseline.items()}
evidence=dict(partitions=dict(Counter(r['partition'] for r in split)),development_labels=dict(Counter(r['actual'] for r in oof)),development_projects=len({r['BioProject'] for r in split if r['partition']=='train'}),folds=folds,baseline_means=means)
sources=['results/ceftazidime_clsi_split_v2.csv','results/ceftazidime_grouped_cv.csv','results/ceftazidime_clsi_test_scores_v1.csv','results/ceftazidime_clsi_test_confusion_v1.csv','results/ceftazidime_sequence_scaleup/assembly_stage_status.json','notebooks/05_supervised_prediction.ipynb','retrain_ceftazidime_v2.py']
evidence['sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
projects={r['BioSample']:r['BioProject'] for r in split}
by_project=defaultdict(list)
for r in oof:
    by_project[projects[r['BioSample']]].append(r)
project_results=[]
for project,rr in by_project.items():
    c=Counter((int(r['actual']),int(float(r['probability_R'])>=.4)) for r in rr)
    tn,fp,fn,tp=[c[x] for x in ((0,0),(0,1),(1,0),(1,1))]
    project_results.append(dict(project=project,n=len(rr),S=tn+fp,R=tp+fn,FP=fp,FN=fn,errors=fp+fn))
evidence['v2_project_results']=sorted(project_results,key=lambda r:r['errors'],reverse=True)
selection=rows(RUN/'development_selection.csv')
evidence['v2_threshold_comparison']=[r for r in selection if r['candidate']=='RF_leaf_4' and float(r['threshold']) in (.3,.4,.5,.6)]
(OUT/'evidence_audit.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
