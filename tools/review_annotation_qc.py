"""Review technical annotation associations in fixed development anomaly scores.

Partial calls are not proof of low quality. No raw records are removed and no
biological validity, clinical accuracy or external validation is inferred.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, rankdata

ROOT = Path(__file__).resolve().parents[1] / 'data/processed/multispecies'


def corr(x, y):
    if pd.Series(x).nunique() < 2 or pd.Series(y).nunique() < 2:
        return None
    return float(spearmanr(x, y).statistic)


def run(species):
    base = ROOT / species / 'unsupervised_profiles'
    out = base / 'annotation_qc_review'
    out.mkdir(exist_ok=True)
    a = pd.read_parquet(base / 'anomaly_stability/validation_score_audit.parquet')
    b = pd.read_parquet(base / 'anomaly_resampling/sample_uncertainty.parquet')
    assert a.BioSample.is_unique and b.BioSample.is_unique
    # Use the bootstrap ensemble consistently; discard the earlier seed mean.
    a = a.drop(columns='mean_unusualness_score')
    df = a.merge(b, on=['BioSample', 'matrix_row'], validate='one_to_one', how='inner')
    assert len(df) == len(a) == len(b)
    assert np.isfinite(df.mean_unusualness_score).all()
    df['any_partial_call'] = df.partial_call_fraction > 0
    df['any_unseen_call'] = df.unseen_training_calls > 0
    n = int(np.ceil(.05*len(df)))
    # A descriptive rank slice, not a threshold for declaring true anomalies.
    ordered = df.sort_values(['mean_unusualness_score', 'BioSample'], ascending=[False, True])
    df['score_slice'] = 'remaining_95pct'
    df.loc[ordered.index[:n], 'score_slice'] = 'highest_5pct_for_audit'
    quality = df.groupby('score_slice').agg(
        samples=('BioSample', 'size'),
        median_profile_size=('profile_size', 'median'),
        any_partial_fraction=('any_partial_call', 'mean'),
        median_partial_call_fraction=('partial_call_fraction', 'median'),
        any_unseen_fraction=('any_unseen_call', 'mean'),
        median_bootstrap_rank_range=('rank_range', 'median'),
        zero_retained_features=('zero_retained_features', 'sum'))
    quality.to_csv(out / 'score_slice_quality.csv')
    versions = df.groupby('AMRFinderPlus version', dropna=False).agg(
        samples=('BioSample', 'size'), median_score=('mean_unusualness_score', 'median'),
        median_profile_size=('profile_size', 'median'),
        partial_fraction=('any_partial_call', 'mean'))
    versions.to_csv(out / 'version_summary.csv')
    # Within-count-band diagnostics to expose relationships obscured by size.
    df['profile_size_band'] = pd.cut(df.profile_size, [0, 3, 7, 14, np.inf], labels=['1-3', '4-7', '8-14', '15+'])
    strata = []
    for name, group in df.groupby('profile_size_band', observed=True):
        strata.append({'band': str(name), 'samples': len(group), 'partial_score_spearman': corr(group.partial_call_fraction, group.mean_unusualness_score), 'unseen_score_spearman': corr(group.unseen_training_calls, group.mean_unusualness_score)})
    pd.DataFrame(strata).to_csv(out / 'within_size_band_associations.csv', index=False)
    # Descriptive joint rank regression; do not call this predictive accuracy.
    fields = ['profile_size', 'partial_call_fraction', 'unseen_training_calls']
    columns = [np.ones(len(df))]
    for field in fields:
        r = rankdata(df[field]).astype(float)
        if r.std() > 0:
            columns.append((r-r.mean())/r.std())
    dummies = pd.get_dummies(df['AMRFinderPlus version'].fillna('missing'), drop_first=True, dtype=float)
    columns.extend(dummies[c].to_numpy() for c in dummies)
    design = np.column_stack(columns)
    y = rankdata(df.mean_unusualness_score)
    fitted = design @ np.linalg.lstsq(design, y, rcond=None)[0]
    r2 = float(1-np.sum((y-fitted)**2)/np.sum((y-y.mean())**2))
    projects = df.groupby('BioProject', dropna=False).agg(samples=('BioSample', 'size'), median_score=('mean_unusualness_score', 'median'))
    projects['small_sample_flag'] = projects.samples < 20
    projects.to_csv(out / 'project_summary.csv')
    df.to_parquet(out / 'sample_qc_context.parquet', index=False)
    assert quality.samples.sum() == len(df) and (df.score_slice == 'highest_5pct_for_audit').sum() == n
    report = {'species': species, 'reviewed_samples': len(df), 'score_slice_comparison': quality.reset_index().to_dict(orient='records'), 'joint_rank_association_r_squared': r2, 'version_counts': df['AMRFinderPlus version'].value_counts(dropna=False).to_dict(), 'zero_retained_feature_samples': int(df.zero_retained_features.sum()), 'missing_project_samples': int(df.BioProject.fillna('').eq('').sum()), 'within_profile_size_bands': strata, 'interpretation': 'R-squared describes in-sample association of score ranks with size, partial calls, unseen calls and version; it is not accuracy or a causal estimate. Null correlations indicate no variation. Weak measured associations do not rule out technical artifacts.', 'remaining_qc': ['raw read/assembly contamination and coverage verification', 'annotation database and pipeline provenance beyond tool version', 'independent non-overlapping cohort validation'], 'limitations': 'Previously explored development subset of 1500 samples. Repeated genomes and ascertainment bias can affect summaries. A partial call is not automatically an error. No records removed, model thresholds changed or alerts enabled.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
