"""Descriptive post-hoc AST summaries for frozen exploratory clusters.

Not a predictive evaluation: labels are observed on a selected subset, and
cluster assignments do not establish resistance for unlabeled samples.
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / 'data/processed/multispecies'


def run(species, assignment_dir):
    base = ROOT / species
    clusters = pd.read_parquet(base / 'unsupervised_profiles' / assignment_dir / 'assignments.parquet')
    assert clusters.BioSample.is_unique
    labels = pd.read_parquet(base / 'labels_by_standard.parquet').rename(columns={'#BioSample':'BioSample'})
    assert not labels.duplicated(['BioSample','Antibiotic','Testing standard']).any()
    joined = labels.merge(clusters[['BioSample','cluster']], on='BioSample', how='inner', validate='many_to_one')
    out = base / 'unsupervised_profiles' / assignment_dir / 'ast_description'
    out.mkdir(exist_ok=True)
    sizes = clusters.groupby('cluster').size().rename('total_samples')
    coverage = joined.groupby('cluster').BioSample.nunique().rename('samples_with_any_usable_label')
    overall = sizes.to_frame().join(coverage).fillna(0)
    overall['samples_with_any_usable_label'] = overall.samples_with_any_usable_label.astype(int)
    overall['label_coverage_fraction'] = overall.samples_with_any_usable_label / overall.total_samples
    overall.to_csv(out / 'cluster_label_coverage.csv')
    counts = joined.groupby(['cluster','Antibiotic','Testing standard','target']).size().unstack(fill_value=0).reindex(columns=[0,1],fill_value=0)
    counts.columns = ['susceptible','resistant']
    counts['labeled_samples'] = counts.susceptible + counts.resistant
    counts['resistant_fraction_among_labeled'] = counts.resistant / counts.labeled_samples
    counts['small_sample_flag'] = counts.labeled_samples < 30
    counts = counts.reset_index().merge(sizes.reset_index(),on='cluster',validate='many_to_one')
    counts['drug_specific_label_coverage'] = counts.labeled_samples / counts.total_samples
    assert (counts.labeled_samples <= counts.total_samples).all()
    counts.to_csv(out / 'cluster_drug_standard_counts.csv',index=False)
    summary = {'assignment_source':assignment_dir,'clustered_samples':len(clusters),'samples_with_any_usable_label':joined.BioSample.nunique(),'matched_label_rows':len(joined),'unmatched_label_samples':len(set(labels.BioSample)-set(clusters.BioSample)),'cluster_drug_standard_cells':len(counts),'cells_with_fewer_than_30_labels':int(counts.small_sample_flag.sum()),'scope':'Frozen-cluster descriptive association only; no label-based tuning or resistance imputation. Testing standards kept separate. Coverage uses all samples in each cluster as denominator.','limitations':'Nonrandom AST availability, repeated antibiotics per isolate, related genomes and collection biases prevent treating these rates as population prevalence or independent predictive accuracy. No inferential confidence intervals.'}
    (out/'report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(species,json.dumps(summary),flush=True)


if __name__=='__main__':
    run('escherichia_coli','extended_cluster_audit')
    run('acinetobacter_baumannii','normalized_comparison')
