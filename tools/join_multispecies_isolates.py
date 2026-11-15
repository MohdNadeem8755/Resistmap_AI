"""Join candidate labels to unambiguous isolate metadata without modifying raw data."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    summary = {}
    for species, filename, scientific in [
        ('escherichia_coli', 'ecoli_isolates.tsv', 'Escherichia coli'),
        ('acinetobacter_baumannii', 'abaumannii_isolates.tsv', 'Acinetobacter baumannii'),
    ]:
        out = ROOT / 'data/processed/multispecies' / species
        labels = pd.read_parquet(out / 'labels_by_standard.parquet').rename(columns={'#BioSample': 'BioSample'})
        iso = pd.read_csv(ROOT / 'data/multispecies' / species / filename, sep='\t', dtype='string', keep_default_na=False)
        iso.columns = iso.columns.str.lstrip('#')
        for col in iso:
            iso[col] = iso[col].str.strip().replace('', pd.NA)
        relevant = iso.loc[iso.BioSample.isin(labels.BioSample)].drop_duplicates()
        # Different profiles/assemblies for one BioSample need explicit adjudication.
        ambiguous = relevant.BioSample[relevant.BioSample.duplicated(keep=False)].unique()
        relevant.loc[relevant.BioSample.isin(ambiguous)].to_parquet(out / 'ambiguous_isolates.parquet', index=False)
        unique = relevant.loc[~relevant.BioSample.isin(ambiguous)]
        joined = labels.merge(unique, on='BioSample', how='left', validate='many_to_one', indicator=True)
        joined['metadata_matched'] = joined['_merge'].eq('both')
        joined = joined.drop(columns='_merge')
        joined['species_verified'] = joined['Scientific name'].fillna('').str.match('^' + scientific + r'(?:\s|$)')
        joined['amr_profile_present'] = joined['AMR genotypes'].notna()
        joined['cluster_present'] = joined['SNP cluster'].notna()
        # Blank AMR profiles are unknown, not automatically all-zero genomes.
        joined.to_parquet(out / 'labels_with_isolates.parquet', index=False)
        ready = joined.metadata_matched & joined.species_verified & joined.amr_profile_present & joined.cluster_present
        joined.loc[ready].to_parquet(out / 'feature_candidates.parquet', index=False)
        samples = joined.drop_duplicates('BioSample')
        summary[species] = {
            'label_rows': len(labels), 'unique_label_samples': int(labels.BioSample.nunique()),
            'ambiguous_biosamples': len(ambiguous),
            'matched_samples': int(samples.metadata_matched.sum()),
            'species_verified_samples': int(samples.species_verified.sum()),
            'missing_amr_profiles': int((~samples.amr_profile_present).sum()),
            'missing_snp_clusters': int((~samples.cluster_present).sum()),
            'feature_candidate_samples': int(joined.loc[ready, 'BioSample'].nunique()),
            'feature_candidate_rows': int(ready.sum()),
            'status': 'joined_and_audited_not_final_training_split',
        }
    report = ROOT / 'data/processed/multispecies/isolate_join_report.json'
    report.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
