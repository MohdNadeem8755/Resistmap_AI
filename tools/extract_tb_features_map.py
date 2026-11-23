import time
from pathlib import Path
import scipy.sparse
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
import joblib

t0 = time.time()
base = Path(r'd:\ResistMap-AI\data\processed\multispecies\tuberculosis')
feat_dir = base / 'features'
model_dir = base / 'supervised_models'

samples = pd.read_parquet(str(feat_dir / 'samples.parquet'))
labels = pd.read_parquet(str(feat_dir / 'labels.parquet'))

acc2row = dict(zip(samples['sample_accession'], samples['matrix_row']))
acc2study = dict(zip(samples['sample_accession'], samples['study_accession']))
labels['matrix_row'] = labels['sample_accession'].map(acc2row)
labels['study_accession'] = labels['sample_accession'].map(acc2study)
labels = labels.dropna(subset=['matrix_row', 'study_accession'])
labels['matrix_row'] = labels['matrix_row'].astype(int)

sample_ids = samples['sample_accession'].values
study_groups = samples['study_accession'].values

gss1 = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
train_idx, _ = next(gss1.split(sample_ids, groups=study_groups))
train_set = set(sample_ids[train_idx])

labels['split'] = labels['sample_accession'].map(lambda a: 'train' if a in train_set else 'other')
train_rows = labels[labels['split'] == 'train']['matrix_row'].unique()
print(f'Train rows: {len(train_rows):,}, elapsed: {time.time()-t0:.2f}s')

print('Loading mutation_features.npz...')
X_full = scipy.sparse.load_npz(str(feat_dir / 'mutation_features.npz')).tocsr()
print(f'Matrix loaded: {X_full.shape}, elapsed: {time.time()-t0:.2f}s')

X_train_full = X_full[train_rows]
col_freq = np.asarray(X_train_full.sum(axis=0)).ravel()
selected_cols = np.where(col_freq >= 5)[0]
print(f'Selected cols: {len(selected_cols):,} (expected 241,285), elapsed: {time.time()-t0:.2f}s')

rif_model = joblib.load(str(model_dir / 'rif_WHO.joblib'))
print(f'Rif model n_features_in_: {rif_model.n_features_in_}')

if len(selected_cols) == rif_model.n_features_in_:
    print('EXACT MATCH! Saving selected_cols.npy...')
    np.save(str(model_dir / 'selected_feature_cols.npy'), selected_cols)
    print('Saved successfully!')
    
    # Test inference on SAMEA10029749 and SAMEA13299636
    for sid in ['SAMEA10029749', 'SAMEA13299636']:
        idx = samples[samples['sample_accession'] == sid].index[0]
        row_vec = X_full[idx, selected_cols]
        prob = rif_model.predict_proba(row_vec)[0, 1]
        pred = 'Resistant' if rif_model.predict(row_vec)[0] == 1 else 'Susceptible'
        print(f'TB {sid}: prob={prob:.4f}, pred={pred}')
