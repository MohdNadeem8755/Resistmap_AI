import pandas as pd, sys, os, json

PYTHON  = "/home/Mohd_Sami/.local/share/resistmap-contamination-qc/env/bin/python"
BASE    = "/mnt/d/ResistMap-AI/data/processed/multispecies/tuberculosis/features"
OUT     = "/mnt/d/ResistMap-AI/tmp/tb_inspect_out.json"
ERR     = "/mnt/d/ResistMap-AI/tmp/tb_err.txt"

try:
    labels  = pd.read_parquet(os.path.join(BASE, "labels.parquet"))
    samples = pd.read_parquet(os.path.join(BASE, "samples.parquet"))

    info = {}
    info["labels_shape"]  = list(labels.shape)
    info["labels_cols"]   = labels.columns.tolist()
    info["labels_dtypes"] = {c: str(t) for c, t in labels.dtypes.items()}
    info["labels_head"]   = labels.head(5).to_dict(orient="records")

    # find drug column
    for col in labels.columns:
        if 'drug' in col.lower():
            info["drug_col"] = col
            info["drug_vals"] = sorted(str(x) for x in labels[col].dropna().unique().tolist())
            break

    # find target/phenotype column
    for col in labels.columns:
        if any(k in col.lower() for k in ['phenotype','target','label','dst','suscept','resist','pheno']):
            info["target_col"] = col
            info["target_vals"] = {str(k): int(v) for k, v in labels[col].value_counts().items()}
            break

    # find sample id column
    for col in labels.columns:
        if any(k in col.lower() for k in ['sample','accession','biosample','wgs_id','id']):
            info["sample_id_col_in_labels"] = col
            info["n_unique_samples_in_labels"] = int(labels[col].nunique())
            break

    info["samples_shape"] = list(samples.shape)
    info["samples_cols"]  = samples.columns.tolist()
    info["samples_head"]  = samples.head(5).to_dict(orient="records")

    group_cols = {}
    for col in samples.columns:
        if any(k in col.lower() for k in ['lineage','group','cluster','study','strain','accession','sample']):
            group_cols[col] = int(samples[col].nunique())
    info["potential_group_cols"] = group_cols

    # check if matrix row mapping exists
    info["samples_has_matrix_row"] = 'matrix_row' in samples.columns
    info["labels_has_matrix_row"]  = 'matrix_row' in labels.columns

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, default=str)
    print("DONE:", OUT)

except Exception:
    import traceback
    tb = traceback.format_exc()
    with open(ERR, 'w', encoding='utf-8') as f:
        f.write(tb)
    print("ERROR:", tb)
