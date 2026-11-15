# ResistMap AI

Local genomic AMR research dashboard for Klebsiella pneumoniae.

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

## Input and output
CSV/TSV columns: BioSample and AMR genotypes.
Calls: gene=COMPLETE or mutation=POINT, separated by commas.
Prediction requires species="Klebsiella pneumoniae" and complete_profile=true.
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
- Train an expanded-feature model after cohort and inclusion decisions.
- Evaluate on a fresh independent cohort: the old 114-sample test influenced development.
- Validate biological relevance of anomalies; outliers do not prove new resistance.
- Implement resource-controlled raw genome upload and annotation integration.

V2 development scores are not independent accuracy. Conformal prediction,
genomic familiarity checks and outbreak alerts remain proposed future work.
This is a research prototype, not a clinically validated diagnostic system.

## Verify
Run .venv-ui/Scripts/python.exe -m pytest tests/test_prediction.py tests/test_dashboard.py -q.
Build frontend with npm run build in frontend.
