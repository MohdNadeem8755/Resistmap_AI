import pandas as pd, pyarrow as pa, pyarrow.parquet as pq, sys, os
src = r'D:\ResistMap-AI\data\processed\multispecies\tuberculosis\features\samples.parquet'
if not os.path.isfile(src):
    sys.exit('source samples not found')
df = pd.read_parquet(src)
# rename column to BioSample
if 'sample_accession' in df.columns:
    df = df.rename(columns={'sample_accession': 'BioSample'})
# ensure matrix_row sequential
if 'matrix_row' not in df.columns:
    df['matrix_row'] = range(len(df))
# select needed columns
out_df = df[['BioSample', 'matrix_row']]
out_path = r'D:\ResistMap-AI\data\processed\multispecies\tuberculosis\unsupervised_profiles\samples.parquet'
out_df.to_parquet(out_path, index=False)
print('Written', out_path, len(out_df))
