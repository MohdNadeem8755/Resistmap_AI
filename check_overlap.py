import pathlib, pandas as pd, scipy.sparse as sp, numpy as np, sys

root = pathlib.Path(r'D:\ResistMap-AI')
features_dir = root / 'data' / 'processed' / 'multispecies' / 'tuberculosis' / 'features'
train_matrix = sp.load_npz(features_dir / 'mutation_features.npz')
train_labels = pd.read_parquet(features_dir / 'labels.parquet')

val_path = root / 'data' / 'external' / 'tb_independent' / 'validation_features.parquet'
val_df = pd.read_parquet(val_path)

# Use row indices as identifiers (the validation rows were randomly selected)
train_indices = set(range(train_matrix.shape[0]))
val_indices   = set(val_df.index.tolist())

overlap = train_indices.intersection(val_indices)
if overlap:
    print(f'⚠️ Overlap found: {len(overlap)} rows')
    sys.exit(1)
else:
    print('✅ No overlap between training set and validation set')
