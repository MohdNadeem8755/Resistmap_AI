# TB Encoding Verification Report

## Artifact inventory (TB)

| Item | Count / Size | Notes |
|------|--------------|-------|
| Total TB files (all directories) | **54 files**, **636,590,454 bytes** (~607 MiB) | Includes raw data, unsupervised profiles, supervised model artifacts, feature files, reports. |
| Feature matrix size (from training log) | **51,012 samples × 1,850,698 mutation features** | Sparse matrix stored in mutation_features.npz; aggregate inventory size is separate. |
| Feature list (`feature_names.json`) | **80,643,140 bytes** (≈ 77 MiB) | 1,850,698 feature names. |
| Selected features (`selected_feature_cols.npy`) | **1,930,408 bytes** (≈ 1.8 MiB) | 241,285 features selected (frequency ≥ 5 in training rows). |
| Supervised model artifacts | **16 `*.joblib` files** (≈ 30.9 MiB total) | Logistic‑Regression models per drug (AMI, BDQ, …, STM). |
| Supervised model report (`supervised_models/report.json`) | **4,677 bytes** | Summarises training splits, metrics, and limitations. |
| Metrics CSV (`supervised_models/metrics.csv`) | **5,066 bytes** | Per‑drug test metrics. |

## Provenance evidence found

- **Training log**: `reports/tb_training_log.txt` – records full training pipeline, feature selection, split counts, per‑drug train/validation/test sample numbers, and which drugs were skipped due to insufficient class support. This log is a primary evidence of the training run.
- **Model report**: `data/processed/multispecies/tuberculosis/supervised_models/report.json` – contains summary of split policy, feature‑selection totals, per‑drug test metrics, and explicit limitations statement.
- **Feature list report**: `data/processed/multispecies/tuberculosis/features/report.json` – documents the feature extraction process and confirms the feature‑selection parameters used.
- **Unsupervised profile reports**: `unsupervised_profiles/clusters/report.json` and `unsupervised_profiles/svd/report.json` – provide evidence of the unsupervised pipelines that are publicly exposed.
- **Training script**: `tools/train_tb_supervised.py` – the code that generated the above artifacts (included for reference).
- **Git repository**: `.git` directory exists, but the relevant provenance files (`metadata.json`, original training manifests, input‑schema snapshots, checksum files) are not present in the history.

## Missing or unavailable records

| Record type | Expected location | Reason missing |
|------------|-------------------|----------------|
| Original training manifest (e.g., JSON/YAML describing dataset version, preprocessing steps, hyper‑parameters) | `data/processed/.../tuberculosis/train_manifest.json` (or similar) | Not found in repository or any backup directories. |
| Input‑schema snapshot (column definitions, type information used during feature extraction) | `data/processed/.../tuberculosis/input_schema.yaml` | No such file detected. |
| Preprocessing version tag (e.g., software version, parameter set used for generating mutation matrix) | `data/processed/.../tuberculosis/preprocess_version.txt` | Absent. |
| Checksums or cryptographic digests of the original mutation matrix (to certify that the stored matrix matches the training data) | `*.checksum` files alongside the Parquet matrices | No checksum files located. |
| Detailed provenance metadata (`metadata.json`) linking each model file to the exact feature ordering used at train time | `supervised_models/*.metadata.json` | None present. |

The absence of these records means that we cannot independently verify that the saved model coefficients correspond to the exact feature ordering that existed at training time. The available evidence (training log, model report, feature list) confirms that a training run was performed, but does not provide cryptographic proof of feature‑order integrity.

## Remaining uncertainties

- **Feature ordering certification**: Without a saved `metadata.json` or checksum of the original matrix, we cannot guarantee that the ordering of the 1,850,698 features at training matches the ordering used at inference time.
- **External validation**: No independent validation cohort is recorded; all metrics are internal test‑split results.
- **Reproducibility of the exact training environment**: No explicit record of library versions or environment snapshot used for this training run.

## Recommendations

1. Store a **manifest** capturing dataset version, preprocessing pipeline version, and hyper‑parameters alongside the model artifacts.
2. Generate and keep **checksums** (e.g., SHA‑256) of the mutation matrix and feature list used for training.
3. Record the **environment** (e.g., `conda env export`) at training time and version‑control it.
4. When future supervised TB models are trained, include the above provenance artifacts to enable full reproducibility and compatibility certification.

---
*This document was generated on 2026‑11‑17 by the Antigravity assistant.*

## Software integrity verification — 2026-11-17

Observed laboratory labels are not used as model predictions. The label-based
exception fallback and placeholder score were removed. TB supervised inference
remains disabled. Existing clustering and SVD images are served through
authenticated routes; missing image files return HTTP 404. Availability requires
both reports, assignments, embedding, and overview images.

The software checks completed with 29 passed and 2 skipped out of 31 tests.
Speech-engine availability and a missing audio fixture account for the skips.
The frontend build succeeded with dependency directive warnings. Logs are in
output/integrity_verification/. These software checks do not establish scientific
model compatibility or independent validation.
