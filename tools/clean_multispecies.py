"""Auditable label-table cleaning. Raw files are never modified.

Outputs are candidate labels, not model features or final evaluation splits.
Genomic grouping and TB quality interpretation must precede final splits.
"""
import json
import hashlib
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/multispecies'
OUT = ROOT / 'data/processed/multispecies'


def clean(df, sample, drug, phenotype, species, out):
    if sample not in df.columns or drug not in df.columns:
        df = df.reset_index()
    out.mkdir(parents=True, exist_ok=True)
    report = {'input_rows': len(df), 'status': 'candidate_labels_not_training_ready'}
    for col in df.select_dtypes(include=['object', 'str', 'string']).columns:
        df[col] = df[col].astype('string').str.strip().replace('', pd.NA)
    report['empty_columns'] = df.columns[df.isna().all()].tolist()
    # Keep the source schema, including empty fields, for auditing.
    empty = df.isna().all(axis=1)
    report['empty_rows'] = int(empty.sum())
    df = df.loc[~empty].copy()
    dup = df.duplicated()
    report['exact_duplicates'] = int(dup.sum())
    df = df.loc[~dup].copy()
    df[drug] = df[drug].astype('string').str.lower().str.strip()
    label = df[phenotype].astype('string').str.lower().str.strip()
    df['target'] = label.map({'r': 1, 's': 0, 'resistant': 1, 'susceptible': 0}).astype('Int64')
    reason = pd.Series('', index=df.index, dtype='string')
    reason.loc[df[sample].isna() | df[drug].isna()] = 'missing_sample_or_drug'
    reason.loc[df.target.isna()] = 'non_binary_or_missing_phenotype'
    if species:
        valid = df['Scientific name'].fillna('').str.match('^' + species + r'(?:\s|$)')
        reason.loc[~valid] = 'species_mismatch'
    # Conflicting repeats are quarantined, never decided by majority vote.
    binary = df.loc[df.target.notna()]
    conflicts = binary.groupby([sample, drug]).target.nunique()
    bad = set(conflicts[conflicts > 1].index)
    conflict_mask = pd.Series(list(zip(df[sample], df[drug])), index=df.index).isin(bad)
    reason.loc[conflict_mask] = 'conflicting_sample_drug_labels'
    df['exclusion_reason'] = reason
    df.loc[reason.ne('')].to_parquet(out / 'excluded.parquet', index=False)
    candidate = df.loc[reason.eq('')].drop(columns='exclusion_reason')
    candidate.to_parquet(out / 'candidate_labels.parquet', index=False)
    report['candidate_rows'] = len(candidate)
    report['unique_samples'] = int(candidate[sample].nunique())
    report['exclusions'] = reason[reason.ne('')].value_counts().to_dict()
    counts = candidate.drop_duplicates([sample, drug]).groupby([drug, 'target']).size().unstack(fill_value=0)
    counts.to_csv(out / 'class_counts.csv')
    report['remaining_steps'] = ['review testing standards and QC', 'join genomic features', 'group related genomes before splitting', 'fit transformations and class weights using training data only']
    (out / 'qc_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reports = {}
    for folder, filename, species in [('escherichia_coli', 'ecoli_ast.tsv', 'Escherichia coli'), ('acinetobacter_baumannii', 'abaumannii_ast.tsv', 'Acinetobacter baumannii')]:
        df = pd.read_csv(RAW / folder / filename, sep='\t', dtype='string', keep_default_na=False)
        reports[folder] = clean(df, '#BioSample', 'Antibiotic', 'Resistance phenotype', species, OUT / folder)
    tb = RAW / 'tuberculosis'
    inventory = {}
    for path in tb.glob('*.parquet'):
        pf = pq.ParquetFile(path)
        inventory[path.name] = {'rows': pf.metadata.num_rows, 'columns': pf.schema_arrow.names}
    reports['tuberculosis'] = clean(pd.read_parquet(tb / 'DST_MEASUREMENTS.parquet'), 'UNIQUEID', 'DRUG', 'PHENOTYPE', None, OUT / 'tuberculosis')
    reports['tuberculosis']['table_inventory'] = inventory
    (OUT / 'summary.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    for species, report in reports.items():
        print(species, {k: report[k] for k in ['input_rows', 'exact_duplicates', 'candidate_rows', 'unique_samples', 'exclusions']})


if __name__ == '__main__':
    main()
