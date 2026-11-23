"""
Train leakage-safe TB supervised baselines.

Group-aware stratified splitting: samples from the same study_accession
are kept together (never split across train/val/test). This prevents
data leakage from related isolates collected in the same study.

Vocabulary (feature selection) is derived from training rows only
to avoid leakage from the full 1.85M-feature matrix.

Saves per-drug .joblib models + consolidated report.json consistent
with the E. coli / A. baumannii format.
"""
import json
import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit

warnings.filterwarnings("ignore", category=UserWarning)

# ── Paths ────────────────────────────────────────────────────────────────────
BASE   = Path(r"D:\ResistMap-AI\data\processed\multispecies\tuberculosis\features")
OUT    = BASE.parent / "supervised_models"
LOG    = Path(r"D:\ResistMap-AI\reports\tb_training_log.txt")
OUT.mkdir(exist_ok=True)
LOG.parent.mkdir(exist_ok=True)

PYTHON_USED = r"D:\AncondaAPP\python.exe"

# ── Split parameters ─────────────────────────────────────────────────────────
VAL_FRAC  = 0.10   # fraction of samples for validation
TEST_FRAC = 0.15   # fraction of samples for test
MIN_CLASS_PER_SPLIT = 10  # minimum samples per class per split to train a task

# ── Feature selection from training data only ────────────────────────────────
# We select only columns (mutations) that appear in at least MIN_TRAIN_FREQ
# training samples. This avoids using full 1.85M-feature vocabulary.
MIN_TRAIN_FREQ = 5

log_lines = []


def log(msg):
    print(msg, flush=True)
    log_lines.append(msg)


def save_log():
    LOG.write_text("\n".join(log_lines), encoding="utf-8")


log("=" * 70)
log("TB Supervised Baseline Training")
log("=" * 70)

# ── Load data ────────────────────────────────────────────────────────────────
log("\n[1/5] Loading feature matrix and labels...")
X_full   = load_npz(str(BASE / "mutation_features.npz")).tocsr()
labels   = pd.read_parquet(str(BASE / "labels.parquet"))
samples  = pd.read_parquet(str(BASE / "samples.parquet"))

log(f"  Feature matrix : {X_full.shape[0]:,} samples × {X_full.shape[1]:,} features")
log(f"  Labels         : {labels.shape[0]:,} rows, drugs: {sorted(labels['DRUG'].unique())}")
log(f"  Samples        : {samples.shape[0]:,} rows")

# ── Build sample → matrix_row mapping ────────────────────────────────────────
acc2row   = dict(zip(samples["sample_accession"], samples["matrix_row"]))
acc2study = dict(zip(samples["sample_accession"], samples["study_accession"]))

# Merge study into labels
labels["matrix_row"]    = labels["sample_accession"].map(acc2row)
labels["study_accession"] = labels["sample_accession"].map(acc2study)
labels = labels.dropna(subset=["matrix_row", "study_accession"])
labels["matrix_row"] = labels["matrix_row"].astype(int)

log(f"  Labels with valid matrix_row: {len(labels):,}")

# ── Group-aware split at sample level (not label level) ──────────────────────
log("\n[2/5] Performing group-aware stratified split on samples...")

all_samples = samples.copy()
all_samples["study_group"] = all_samples["study_accession"]

sample_ids   = all_samples["sample_accession"].values
study_groups = all_samples["study_group"].values

# First split: train vs (val + test)
gss1 = GroupShuffleSplit(n_splits=1, test_size=VAL_FRAC + TEST_FRAC, random_state=42)
train_idx, valtest_idx = next(gss1.split(sample_ids, groups=study_groups))

train_samples   = sample_ids[train_idx]
valtest_samples = sample_ids[valtest_idx]
valtest_groups  = study_groups[valtest_idx]

# Second split: val vs test
relative_test_frac = TEST_FRAC / (VAL_FRAC + TEST_FRAC)
gss2 = GroupShuffleSplit(n_splits=1, test_size=relative_test_frac, random_state=42)
val_idx, test_idx = next(gss2.split(valtest_samples, groups=valtest_groups))

val_samples  = valtest_samples[val_idx]
test_samples = valtest_samples[test_idx]

train_set = set(train_samples)
val_set   = set(val_samples)
test_set  = set(test_samples)

log(f"  Train samples  : {len(train_set):,}")
log(f"  Val samples    : {len(val_set):,}")
log(f"  Test samples   : {len(test_set):,}")

# Assign split to labels
def assign_split(acc):
    if acc in train_set:
        return "train"
    if acc in val_set:
        return "validation"
    if acc in test_set:
        return "test"
    return None

labels["split"] = labels["sample_accession"].map(assign_split)
labels = labels.dropna(subset=["split"])

# Save split assignment
split_summary = labels.groupby("split")["sample_accession"].nunique().to_dict()
log(f"  Split unique samples in labels: {split_summary}")

# ── Feature selection from training data only ─────────────────────────────────
log("\n[3/5] Selecting features from training rows only...")
train_rows   = labels[labels["split"] == "train"]["matrix_row"].unique()
X_train_full = X_full[train_rows]
col_freq     = np.asarray(X_train_full.sum(axis=0)).ravel()
selected_cols = np.where(col_freq >= MIN_TRAIN_FREQ)[0]

log(f"  Features with freq ≥ {MIN_TRAIN_FREQ} in training: {len(selected_cols):,} / {X_full.shape[1]:,}")

X_sel = X_full[:, selected_cols]  # still full-sample view, columns filtered

# ── Per-drug training ─────────────────────────────────────────────────────────
log("\n[4/5] Training per-drug models...")

rows      = []
trained   = 0
skipped   = 0

for drug, task in labels.groupby("DRUG"):
    splits = {}
    eligible = True
    for split_name in ["train", "validation", "test"]:
        part = task[task["split"] == split_name]
        counts = part["target"].value_counts()
        c0 = counts.get(0, 0)
        c1 = counts.get(1, 0)
        splits[split_name] = part
        if c0 < MIN_CLASS_PER_SPLIT or c1 < MIN_CLASS_PER_SPLIT:
            eligible = False
            log(f"  SKIP  {drug:6s} | {split_name:12s} | S={c0} R={c1} (below min {MIN_CLASS_PER_SPLIT})")
            break

    if not eligible:
        skipped += 1
        continue

    tr = splits["train"]
    va = splits["validation"]
    te = splits["test"]

    log(f"  TRAIN {drug:6s} | tr={len(tr)} va={len(va)} te={len(te)}")

    model = LogisticRegression(
        max_iter=300,
        class_weight="balanced",
        solver="liblinear",
        random_state=42,
    )
    model.fit(X_sel[tr["matrix_row"]], tr["target"].astype(int))

    for name, part in [("train", tr), ("validation", va), ("test", te)]:
        mrows = part["matrix_row"].values
        y     = part["target"].astype(int).values
        pred  = model.predict(X_sel[mrows])
        prob  = model.predict_proba(X_sel[mrows])[:, 1]
        row   = {
            "species":           "tuberculosis",
            "antibiotic":        drug,
            "standard":          "WHO",
            "split":             name,
            "samples":           len(part),
            "accuracy":          accuracy_score(y, pred),
            "balanced_accuracy": balanced_accuracy_score(y, pred),
            "f1_resistant":      f1_score(y, pred, zero_division=0),
            "roc_auc":           roc_auc_score(y, prob),
        }
        rows.append(row)

    safe_name = "".join(ch if ch.isalnum() else "_" for ch in f"{drug}_WHO")
    joblib.dump(model, OUT / f"{safe_name}.joblib")
    trained += 1

log(f"\n  Trained: {trained} drugs | Skipped: {skipped} drugs")

# ── Save results ──────────────────────────────────────────────────────────────
log("\n[5/5] Saving metrics and report...")

metrics = pd.DataFrame(rows)
metrics.to_csv(OUT / "metrics.csv", index=False)

summary = []
for split_name, d in metrics.groupby("split"):
    summary.append({
        "split":                  split_name,
        "tasks":                  len(d),
        "macro_accuracy":         round(d["accuracy"].mean(), 6),
        "macro_balanced_accuracy": round(d["balanced_accuracy"].mean(), 6),
        "macro_f1_resistant":     round(d["f1_resistant"].mean(), 6),
        "macro_roc_auc":          round(d["roc_auc"].mean(), 6),
    })

# Per-drug test summary
per_drug = []
test_df = metrics[metrics["split"] == "test"]
for _, r in test_df.iterrows():
    per_drug.append({
        "drug":               r["antibiotic"],
        "test_accuracy":      round(r["accuracy"], 4),
        "test_balanced_acc":  round(r["balanced_accuracy"], 4),
        "test_f1_resistant":  round(r["f1_resistant"], 4),
        "test_roc_auc":       round(r["roc_auc"], 4),
        "test_samples":       int(r["samples"]),
    })

report = {
    "species":                "tuberculosis",
    "eligible_tasks_trained": trained,
    "drugs_skipped":          skipped,
    "metrics_rows":           len(metrics),
    "split_counts":           {
        "train":      len(train_set),
        "validation": len(val_set),
        "test":       len(test_set),
    },
    "feature_selection": {
        "total_features":     int(X_full.shape[1]),
        "selected_features":  int(len(selected_cols)),
        "min_train_freq":     MIN_TRAIN_FREQ,
        "note":               "Vocabulary derived from training rows only to prevent leakage.",
    },
    "summary":        summary,
    "per_drug_test":  per_drug,
    "model":          "LogisticRegression(class_weight=balanced, solver=liblinear, max_iter=300)",
    "split_policy":   (
        "Group-aware GroupShuffleSplit by study_accession. "
        f"Train {100*(1-VAL_FRAC-TEST_FRAC):.0f}% / "
        f"Val {100*VAL_FRAC:.0f}% / Test {100*TEST_FRAC:.0f}%."
    ),
    "limitations": (
        "Development baselines only. Drugs with <10 samples per class per split excluded. "
        "Metrics are not clinical accuracy. No hyperparameter tuning performed. "
        "No external validation cohort used."
    ),
}

(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
save_log()

log("\n" + "=" * 70)
log("DONE. Report saved to: " + str(OUT / "report.json"))
log("=" * 70)
log("\nSUMMARY BY SPLIT:")
for s in summary:
    log(f"  {s['split']:12s} | tasks={s['tasks']:2d} | "
        f"acc={s['macro_accuracy']:.4f} | "
        f"bal_acc={s['macro_balanced_accuracy']:.4f} | "
        f"roc_auc={s['macro_roc_auc']:.4f}")

log("\nPER-DRUG TEST RESULTS:")
for d in sorted(per_drug, key=lambda x: -x["test_balanced_acc"]):
    log(f"  {d['drug']:6s} | acc={d['test_accuracy']:.4f} | "
        f"bal_acc={d['test_balanced_acc']:.4f} | "
        f"f1_r={d['test_f1_resistant']:.4f} | "
        f"roc={d['test_roc_auc']:.4f} | n={d['test_samples']}")
