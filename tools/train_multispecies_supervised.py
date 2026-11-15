"""Train leakage-safe development baselines for eligible species/drug tasks."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1] / 'data/processed/multispecies'


def run(species):
    base = ROOT / species / 'encoded'
    out = base / 'supervised_models'
    out.mkdir(exist_ok=True)
    x = load_npz(base / 'genomic_features.npz').tocsr()
    samples = pd.read_csv(base / 'samples.csv')
    targets = pd.read_parquet(base / 'targets.parquet')
    rows = []
    trained = 0
    for (drug, standard), task in targets.groupby(['Antibiotic', 'Testing standard']):
        counts = task.groupby(['split', 'target']).size()
        if not all(counts.get((split, y), 0) >= 10 for split in ['train', 'validation', 'test'] for y in [0, 1]):
            continue
        safe = ''.join(ch if ch.isalnum() else '_' for ch in f'{drug}_{standard}')
        tr = task[task.split.eq('train')]; va = task[task.split.eq('validation')]; te = task[task.split.eq('test')]
        model = LogisticRegression(max_iter=300, class_weight='balanced', solver='liblinear', random_state=42)
        model.fit(x[tr.matrix_row], tr.target.astype(int))
        for name, part in [('train', tr), ('validation', va), ('test', te)]:
            pred = model.predict(x[part.matrix_row]); prob = model.predict_proba(x[part.matrix_row])[:, 1]
            row = {'species': species, 'antibiotic': drug, 'standard': standard, 'split': name,
                   'samples': len(part), 'accuracy': accuracy_score(part.target, pred),
                   'balanced_accuracy': balanced_accuracy_score(part.target, pred),
                   'f1_resistant': f1_score(part.target, pred, zero_division=0),
                   'roc_auc': roc_auc_score(part.target, prob)}
            rows.append(row)
        joblib.dump(model, out / f'{safe}.joblib')
        trained += 1
    metrics = pd.DataFrame(rows)
    metrics.to_csv(out / 'metrics.csv', index=False)
    summary = []
    for split, d in metrics.groupby('split'):
        summary.append({'split': split, 'tasks': len(d), 'macro_accuracy': d.accuracy.mean(),
                        'macro_balanced_accuracy': d.balanced_accuracy.mean(), 'macro_f1_resistant': d.f1_resistant.mean(),
                        'macro_roc_auc': d.roc_auc.mean()})
    report = {'species': species, 'eligible_tasks_trained': trained, 'metrics_rows': len(metrics),
              'summary': summary,
              'model': 'LogisticRegression(class_weight=balanced, solver=liblinear)',
              'split_policy': 'Existing group-aware train/validation/test split from encoded cohort; no external validation.',
              'limitations': 'Development baselines only. Tasks with sparse class support were excluded. Metrics are not clinical accuracy and no hyperparameter tuning was performed.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
