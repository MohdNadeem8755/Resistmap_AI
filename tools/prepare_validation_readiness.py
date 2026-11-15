"""Record previously seen IDs and freeze audit artifacts for future validation."""
import hashlib
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/multispecies_validation_readiness'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reports, artifacts = [], []
    for species, prefix in [('escherichia_coli', 'ecoli'), ('acinetobacter_baumannii', 'abaumannii')]:
        raw = ROOT / 'data/multispecies' / species
        frame = pd.read_csv(raw / (prefix + '_isolates.tsv'), sep='\t', dtype=str, keep_default_na=False)
        frame.columns = frame.columns.str.lstrip('#')
        keys = frame[['BioSample', 'Assembly', 'SNP cluster', 'BioProject']].apply(lambda col: col.str.strip()).drop_duplicates()
        keys.to_parquet(OUT / (species + '_previously_seen_keys.parquet'), index=False)
        ast = pd.read_csv(raw / (prefix + '_ast.tsv'), sep='\t', dtype=str, keep_default_na=False)
        ast.columns = ast.columns.str.lstrip('#')
        ids = set(ast.BioSample.str.strip()) - {''}
        seen = set(keys.BioSample) - {''}
        reports.append({'species': species, 'raw_isolate_biosamples': len(seen),
            'raw_ast_biosamples': len(ids), 'ast_biosamples_in_existing_isolates': len(ids & seen),
            'ast_biosamples_not_in_existing_isolates': len(ids - seen),
            'independent_validation_cohort_established': False})
        base = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
        paths = [base / 'samples.parquet', base / 'feature_names.json',
                 base / 'grouped_representation_evaluation/group_partition.parquet',
                 base / 'grouped_representation_evaluation/sampled_rows.npz']
        paths += sorted((base / 'anomaly_stability').glob('*.joblib'))
        paths += sorted((base / 'anomaly_stability').glob('*.npy'))
        for path in paths:
            artifacts.append({'path': str(path.relative_to(ROOT)), 'sha256': digest(path)})
    (OUT / 'readiness.json').write_text(json.dumps({'cohorts': reports, 'artifact_snapshot': artifacts}, indent=2))
    (OUT / 'validation_protocol.md').write_text('''# Independent validation readiness

No independent E. coli or A. baumannii cohort has been established by this audit.
The existing data have been explored; another split cannot be described as an untouched external test.
Previously seen keys include all raw isolate records, including excluded records.
Artifact hashes preserve current development provenance; they do not select or certify a final model.

## Required before evaluation

1. Obtain a separately sourced cohort with documented sampling, species, dates, BioSample, assembly version, annotation pipeline/database, and available quality evidence.
2. Check BioSample, assembly (including paired/version aliases), known SNP cluster, and exact profile overlap against all development data. Review project overlap and lineage relationships; identifier separation alone does not prove independence.
3. Confirm the assembly underlying each annotation. A newly retrieved assembly for an old BioSample is neither a new sample nor proof of annotation provenance.
4. Predeclare quality exclusions, missing-data handling, the model, preprocessing, and endpoints before examining new outcomes. Do not remove unusual profiles merely because they are unusual.
5. Fit vocabulary/scaling/reduction on development data only; freeze them for validation. Report unseen features and zero-retained-feature records separately.
6. For unsupervised evaluation, report stability and blinded independent review with an explicit reference standard. Without that standard, do not report anomaly accuracy, sensitivity, or specificity.
7. Where phenotype labels support a separate supervised endpoint, retain the natural test distribution, restrict balancing to training, and report per-drug support and group-aware uncertainty. Do not tune on the external cohort.

Missing quality fields remain unknown. Current lookup results and metadata audits do not establish raw-read QC or biological validity.
''', encoding='utf-8')
    print(json.dumps(reports))


if __name__ == '__main__':
    main()
