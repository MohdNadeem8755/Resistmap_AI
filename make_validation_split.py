import pathlib, numpy as np, pandas as pd, scipy.sparse as sp

root = pathlib.Path(r'D:\ResistMap-AI')
features_dir = root / 'data' / 'processed' / 'multispecies' / 'tuberculosis' / 'features'
matrix_path = features_dir / 'mutation_features.npz'
labels_path = features_dir / 'labels.parquet'

# Load the **sparse** matrix and labels (still on disk)
X = sp.load_npz(matrix_path)               # (samples, features)
labels = pd.read_parquet(labels_path)      # expects a column with the target/label

# --------------------------------------------------------------
# 3️⃣ Sampling parameters – keep it tiny
max_rows = 500          # number of samples to pull
max_cols = 1000         # number of features to keep

n_total_rows = X.shape[0]
n_total_cols = X.shape[1]

rows_to_take = min(max_rows, n_total_rows)
cols_to_take = min(max_cols, n_total_cols)

rng = np.random.default_rng(2023)

# Random row indices
row_idx = rng.choice(n_total_rows, size=rows_to_take, replace=False)

# Random column indices
col_idx = rng.choice(n_total_cols, size=cols_to_take, replace=False)

# Slice the sparse matrix (still sparse) and convert only this slice to dense
X_small = X[row_idx][:, col_idx].toarray().astype(np.float32)

# Corresponding label rows (keep the original label column)
labels_small = labels.iloc[row_idx].reset_index(drop=True)

# --------------------------------------------------------------
# 4️⃣ Build a dense DataFrame (features first, then a target column)
df = pd.DataFrame(X_small)

# Assume the first column of the labels file is the target variable
if labels_small.shape[1] > 0:
    df['target'] = labels_small.iloc[:, 0]

# --------------------------------------------------------------
# 5️⃣ Write the validation split (Snappy compression keeps the file tiny)
out_path = root / 'data' / 'external' / 'tb_independent' / 'validation_features.parquet'
out_path.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(out_path, compression='snappy')
print(f'✅ Validation parquet written to {out_path}')
