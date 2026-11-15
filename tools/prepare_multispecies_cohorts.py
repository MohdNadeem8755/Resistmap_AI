"""Prepare QC-reviewed label cohorts and explicit feature acquisition queues.

No accuracy-based split search; no MIC or catalogue predictions as features.
Final splits require genome-relatedness groups, which are not supplied here.
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/multispecies'


def main():
    summary = {}
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        out = BASE / species
        df = pd.read_parquet(out / 'candidate_labels.parquet')
        # Preserve standards as separate strata: cutoffs are not interchangeable.
        df['Testing standard'] = df['Testing standard'].str.upper()
        known = df['Testing standard'].isin(['CLSI', 'EUCAST'])
        df.loc[~known].to_parquet(out / 'unknown_standard_review.parquet', index=False)
        labels = df.loc[known, ['#BioSample', 'Antibiotic', 'Testing standard', 'target']].drop_duplicates()
        labels.to_parquet(out / 'labels_by_standard.parquet', index=False)
        ids = df[['#BioSample']].drop_duplicates().rename(columns={'#BioSample': 'BioSample'})
        ids.to_csv(out / 'genome_metadata_needed.csv', index=False)
        summary[species] = {'label_rows_known_standard': len(labels), 'unknown_standard_rows': int((~known).sum()), 'genomes_needed': len(ids), 'status': 'awaiting_genotypes_assemblies_and_relatedness_groups'}

    out = BASE / 'tuberculosis'
    raw = ROOT / 'data/multispecies/tuberculosis'
    df = pd.read_parquet(out / 'candidate_labels.parquet')
    genomes = pd.read_parquet(raw / 'GENOMES.parquet').reset_index()
    wgs = pd.read_parquet(raw / 'WGS_SAMPLES.parquet').reset_index()
    assert not genomes.UNIQUEID.duplicated().any(), 'Ambiguous genome join'
    assert not wgs.UNIQUEID.duplicated().any(), 'Ambiguous WGS join'
    # Thresholds are explicit project QC choices, not clinical breakpoints.
    joined = df.merge(genomes[['UNIQUEID', 'SPECIES', 'N_LINEAGES', 'LINEAGE', 'SUBLINEAGE', 'TB_COVERAGE', 'TB_DEPTH']], on='UNIQUEID', how='left', validate='many_to_one')
    joined = joined.merge(wgs[['UNIQUEID', 'sample_accession', 'run_accession', 'study_accession', 'status', 'has_mutations', 'dataset', 'group']], on='UNIQUEID', how='left', validate='many_to_one')
    checks = {
        'phenotype_quality': joined.QUALITY.isin(['HIGH', 'MEDIUM']),
        'exact_species': joined.SPECIES.eq('M. tuberculosis'),
        'complete_wgs': joined.status.eq('complete'),
        'coverage_ge_95_percent': joined.TB_COVERAGE.ge(95),
        'depth_ge_20': joined.TB_DEPTH.ge(20),
        'single_lineage': pd.to_numeric(joined.N_LINEAGES, errors='coerce').eq(1),
        'mutation_table_available': joined.has_mutations.eq(True),
        'sample_accession_present': joined.sample_accession.fillna('').ne(''),
    }
    flags = pd.DataFrame(checks).fillna(False)
    keep = flags.all(axis=1)
    rejected = joined.loc[~keep].copy()
    rejected['qc_failures'] = flags.loc[~keep].apply(lambda r: ';'.join(r.index[~r]), axis=1)
    rejected.to_parquet(out / 'qc_excluded.parquet', index=False)
    accepted = joined.loc[keep].copy()
    # A biological sample can have multiple UNIQUEIDs: quarantine discordance.
    conflicts = accepted.groupby(['sample_accession', 'DRUG']).target.nunique()
    bad = set(conflicts[conflicts > 1].index)
    mask = pd.Series(list(zip(accepted.sample_accession, accepted.DRUG)), index=accepted.index).isin(bad)
    accepted.loc[mask].to_parquet(out / 'accession_label_conflicts.parquet', index=False)
    accepted = accepted.loc[~mask]
    accepted.to_parquet(out / 'qc_matched_measurements.parquet', index=False)
    labels = accepted[['sample_accession', 'DRUG', 'target']].drop_duplicates()
    assert not labels.duplicated(['sample_accession', 'DRUG']).any()
    labels.to_parquet(out / 'qc_labels.parquet', index=False)
    accepted[['UNIQUEID', 'sample_accession', 'run_accession', 'study_accession', 'LINEAGE', 'SUBLINEAGE', 'dataset', 'group']].drop_duplicates().to_parquet(out / 'feature_sample_map.parquet', index=False)
    labels.groupby(['DRUG', 'target']).size().unstack(fill_value=0).to_csv(out / 'qc_class_counts.csv')
    summary['tuberculosis'] = {'matched_measurements': len(accepted), 'unique_sample_drug_labels': len(labels), 'unique_samples': labels.sample_accession.nunique(), 'failed_checks_overlapping': {k: int((~v).sum()) for k, v in flags.items()}, 'accession_conflict_rows': int(mask.sum()), 'status': 'QC_join_complete_mutation_matrix_and_relatedness_pending'}
    (BASE / 'cohort_status.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
