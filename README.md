# ResistMap AI

Local genomic AMR research dashboard. Primary focus: Klebsiella pneumoniae ceftazidime resistance.
Multispecies development baselines saved for E. coli, A. baumannii, and M. tuberculosis.

## Run
Install requirements-ui.txt in .venv-ui, run npm run build in frontend,
then run ./start_dashboard.ps1. Open http://127.0.0.1:8011 and create a local account.

## Implemented
- Saved V1/V2 ceftazidime models; V2 is a 600-tree Random Forest, threshold 0.40.
- Authenticated research inference: POST /api/predict and the input workspace.
- Input validation, manual entry, report exports, Hindi/English interface.
- Notebook experiments: K-Means, hierarchical clustering, PCA and Isolation Forest.
- Reusable src/analysis functions; optional UMAP requires umap-learn.
- Checkpointed sequence processing and feature inventory reconciliation.
- Multispecies development baselines: E. coli (21 tasks), A. baumannii (9 tasks),
  M. tuberculosis (16 tasks, 12 skipped). These are saved development baselines only;
  EC/AB profile inference is integrated; TB inference is unavailable pending certified
  feature ordering. Independent validation is pending for all species.

## Multispecies development summaries

- **K. pneumoniae** (Klebsiella pneumoniae): 445‑sample supervised cohort, V2 600‑tree RF, internal CV metrics shown.
- **E. coli** (Escherichia coli): 21 supervised tasks, Logistic‑Regression models, internal CV metrics shown.
- **A. baumannii** (Acinetobacter baumannii): 9 supervised tasks, Logistic‑Regression models, internal CV metrics shown.
- **M. tuberculosis** details are described in the dedicated **M. tuberculosis** section above; only unsupervised results are exposed, supervised inference is disabled pending provenance.


### K. pneumoniae (Klebsiella pneumoniae)
- 445-sample supervised cohort (310 assemblies + 135 reads); CLSI ceftazidime labels.
- V2: 600-tree RF, development CV accuracy 90.37%, balanced accuracy 83.66%.
- Independent validation pending; old 114-sample V1 test influenced development.

### E. coli (Escherichia coli)
- 523,625 encoded samples. Unsupervised: k=2 clusters, SVD (32 dims, 76.5% variance).
  Anomaly resampling stability: Spearman ρ 0.885–0.979 across 5 bootstrap runs.
- Supervised: 21 tasks; macro test accuracy 96.0%, balanced accuracy 94.0%. (CLSI/EUCAST)
- Provenance: PATRIC/BV-BRC isolate database, plus Alessandro Gerada (University of
  Liverpool) email data and manuscript (https://datacat.liverpool.ac.uk/3008/;
  PRJEB115520 — 100% sample overlap detected, excluded from independent validation).
  Accession crosswalk to development BioSamples is not complete; independence not established.

### A. baumannii (Acinetobacter baumannii)
- 64,033 encoded samples. Unsupervised: k=8 clusters, SVD.
  Anomaly resampling stability available (see reports/multispecies_validation_readiness/).
- Supervised: 9 tasks; macro test accuracy 74.3%, balanced accuracy 69.2%. (CLSI)
- Candidate external cohorts (PRJNA1286014, PRJNA573295) show 100% sample overlap
  with development data; independence not established.

### M. tuberculosis

- Features: **51,012 samples**, **1,850,698 mutation features** (sparse matrix; Nov 2026).
- Supervised: **16 drug models trained**, **12 drugs skipped** due to insufficient class support per split (see `reports/tb_training_log.txt`).
- Feature selection: **241,285 features** retained (frequency ≥ 5 in training rows).
- Model details: LogisticRegression (class_weight=balanced, solver=liblinear, max_iter=300).
- Saved clustering and SVD visualization are displayed when the required artifacts exist.
  TB anomaly-review results remain unavailable.
- Runtime inference: unavailable (HTTP 503 for TB profiles; no certified feature ordering).
- Training provenance: documented in `reports/tb_training_log.txt` and `reports/tb_encoding_verification.md`. No original manifest, input‑schema snapshot, or checksum files are present.
- Features: 51,012 samples, 1,850,698 mutation features (sparse matrix; Nov 2026).
- Supervised: 16 drug models trained (12 skipped — insufficient class support per split).
  Group-aware split by study_accession (train 75% / val 10% / test 15%).
  Macro test accuracy 88.7%, balanced accuracy 80.3%. Model: LogisticRegression
  (class_weight=balanced, solver=liblinear, max_iter=300).
- Saved clustering and SVD visualization are displayed when the required artifacts exist.
  TB anomaly-review results remain unavailable.
- Runtime inference: unavailable (HTTP 503 for profiles; no score for TB ID lookup).
  Five raw-record encoding comparisons match the saved matrix and existing mask;
  training-time ordering of model coefficients is not certified. No external validation cohort.

## Scope and limitations
All multispecies supervised results are development baselines. Metrics reflect the
internal test split of the same cohort used for training; they are not independent
accuracy. No candidate external validation cohort has been confirmed as non-overlapping.
The authenticated prediction endpoint (/api/predict) supports K. pneumoniae, E. coli,
and A. baumannii. TB fails closed while model compatibility remains uncertified.
Historical examples on the dashboard are saved V1 results, not live predictions.
This is a research prototype, not a clinically validated diagnostic system.

## Input and output
CSV/TSV columns: BioSample and AMR genotypes.
Calls: gene=COMPLETE or mutation=POINT, separated by commas.
Prediction requires a supported species and complete_profile=true. EC defaults to
ciprofloxacin and AB to amikacin; an optional drug selects a saved task.
Only complete annotated profiles should be submitted; missing calls are encoded
as absent. The response includes label, resistance score, threshold and unseen
features. Samples without recognized features receive no prediction.
This guard is not a validated OOD detector. Scores are not calibrated confidence.
Uploaded model artifacts are never loaded. Input is not persisted.

POST /api/validate-input still performs format checking only.
Raw FASTA/FASTQ processing uses curated command-line scripts, not the web input.

## Resume and reconcile
Run from the project root:
```powershell
.\.venv-ui\Scripts\python.exe resume_ceftazidime_reads_memory.py --preflight
.\.venv-ui\Scripts\python.exe resume_ceftazidime_reads_memory.py
.\.venv-ui\Scripts\python.exe reconcile_sequence_inventory.py
```
Requires existing WSL bioinformatics environments and network access.
Only run one read runner at a time. Completed checkpoints are preserved.
Status: results/ceftazidime_sequence_scaleup/reads/read_job_status.json.
Reconciled features and missing-sample inventory:
results/ceftazidime_sequence_scaleup/reconciled/.
Reconciliation does not certify biological QC or train a model.

## Remaining research work
- Finish read processing, comprehensive contamination screening and QC review.
- Train an expanded-feature K. pneumoniae model after cohort and inclusion decisions.
- Evaluate on a fresh independent cohort: the old 114-sample test influenced development.
- Establish a genuinely non-overlapping external cohort for E. coli / A. baumannii.
  Current candidate projects (PRJEB115520, PRJNA1286014, PRJNA573295) all show 100%
  sample overlap. Liverpool E. coli cohort blocked on accession crosswalk.
- TB: compatibility provenance and independent validation remain unresolved;
  supervised inference stays disabled. Anomaly review remains pending.
- Validate biological relevance of anomalies; outliers do not prove new resistance.
- Implement resource-controlled raw genome upload and annotation integration.

V2 development scores are not independent accuracy. Conformal prediction,
genomic familiarity checks and outbreak alerts remain proposed future work.
This is a research prototype, not a clinically validated diagnostic system.

## Verify
Use the verified local Python from the project root:
```powershell
& D:\AncondaAPP\python.exe -m pytest tests -q
& D:\AncondaAPP\python.exe tools/audit_tb_encoding.py
```
The audit reads original MUTATIONS.parquet records for five deterministic samples,
compares exact (GENE, MUTATION) pairs to full and masked saved rows, and never
writes models or masks. This is sampled encoding verification, not external validation.
See reports/tb_encoding_verification.md for the verified scope and blockers.
Build frontend with npm run build in frontend.
