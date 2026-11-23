"""
Multispecies sample-level inference from saved .joblib model artifacts.

Supports genuine model inference for:
- Escherichia coli (21 Logistic Regression models from genomic_features.npz)
- Acinetobacter baumannii (9 Logistic Regression models from genomic_features.npz)
- Mycobacterium tuberculosis (16 Logistic Regression models from mutation_features.npz + selected_feature_cols.npy)

TB inference is enabled: selected_feature_cols.npy aligns the full 1.85M-column
mutation matrix to the 241,285 columns used during training.
"""
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse

ROOT = Path(os.environ.get('RESISTMAP_ROOT', Path(__file__).resolve().parents[1]))


@lru_cache(maxsize=4)
def _load_matrix(species_id):
    """Load the genomic feature matrix, sample index, and optional column mask for a species."""
    base = ROOT / 'data/processed/multispecies' / species_id

    if species_id == 'tuberculosis':
        feat_path = base / 'features/mutation_features.npz'
        samp_path = base / 'features/samples.parquet'
        cols_path = base / 'supervised_models/selected_feature_cols.npy'
        if not feat_path.is_file() or not samp_path.is_file() or not cols_path.is_file():
            return None, None, None
        X = scipy.sparse.load_npz(str(feat_path)).tocsr()
        samples = pd.read_parquet(str(samp_path))
        cols = np.load(str(cols_path))
        return X, samples, cols

    elif species_id in ('escherichia_coli', 'acinetobacter_baumannii'):
        feat_path = base / 'encoded/genomic_features.npz'
        samp_path = base / 'encoded/samples.csv'
        if not feat_path.is_file() or not samp_path.is_file():
            return None, None, None
        X = scipy.sparse.load_npz(str(feat_path)).tocsr()
        samples = pd.read_csv(str(samp_path))
        return X, samples, None

    return None, None, None


@lru_cache(maxsize=64)
def _load_model(model_path_str, mtime_ns):
    """Load a single joblib model with cache keyed on path + modification time."""
    import joblib
    return joblib.load(model_path_str)


def predict_sample(species_id, sample_id, drug, standard='CLSI'):
    """
    Run inference for a single sample on a specific drug model.

    Returns dict with keys:
      - predicted: 'Resistant' | 'Susceptible' | None
      - score: float probability of Resistant class, or None
      - source: 'model_inference' | 'not_integrated'
      - reason: str explanation if prediction unavailable
    """
    # TB inference is now enabled – selected_feature_cols.npy aligns the
    # full mutation matrix to the 241 285 columns the models were trained on.

    X, samples, cols = _load_matrix(species_id)
    if X is None or samples is None:
        return {
            'predicted': None,
            'score': None,
            'source': 'not_integrated',
            'reason': f'Feature matrix or sample index not available for {species_id}.',
        }

    base = ROOT / 'data/processed/multispecies' / species_id

    # Resolve model file
    if species_id == 'tuberculosis':
        sample_col = 'sample_accession'
        models_dir = base / 'supervised_models'
        drug_code = drug.lower().replace(' ', '_').replace('-', '_')
        code_map = {
            'rifampicin': 'rif', 'isoniazid': 'inh', 'ethambutol': 'emb', 'pyrazinamide': 'pza',
            'amikacin': 'ami', 'capreomycin': 'cap', 'ethionamide': 'eth', 'kanamycin': 'kan',
            'levofloxacin': 'lev', 'moxifloxacin': 'mxf', 'ofloxacin': 'ofx', 'streptomycin': 'stm',
            'bedaquiline': 'bdq', 'clofazimine': 'cfz', 'linezolid': 'lzd',
            'para_aminosalicylic_acid': 'pas', 'rifabutin': 'rfb'
        }
        short_code = code_map.get(drug_code, drug_code[:3])
        model_path = models_dir / f'{short_code}_WHO.joblib'
        if not model_path.is_file():
            # Search
            for candidate in models_dir.glob('*.joblib'):
                if short_code in candidate.stem.lower():
                    model_path = candidate
                    break
    else:
        sample_col = 'BioSample'
        models_dir = base / 'encoded/supervised_models'
        drug_clean = drug.lower().replace(' ', '_').replace('-', '_')
        std_clean = (standard or 'CLSI').upper()
        model_path = models_dir / f'{drug_clean}_{std_clean}.joblib'

    if not model_path or not model_path.is_file():
        return {
            'predicted': None,
            'score': None,
            'source': 'not_integrated',
            'reason': f'No saved model found for {drug} in {species_id}.',
        }

    # Find sample row
    match = samples[samples[sample_col].str.upper() == sample_id.strip().upper()]
    if match.empty:
        return {
            'predicted': None,
            'score': None,
            'source': 'not_integrated',
            'reason': f'Sample {sample_id} not found in the {species_id} cohort.',
        }

    row_idx = match.index[0]

    try:
        model = _load_model(str(model_path), model_path.stat().st_mtime_ns)

        if cols is not None:
            # Sub-select columns for TB
            x_row = X[row_idx, cols]
        else:
            x_row = X[row_idx]

        probas = model.predict_proba(x_row)
        classes = list(model.classes_)
        r_idx = classes.index(1) if 1 in classes else -1
        if r_idx < 0:
            return {
                'predicted': None,
                'score': None,
                'source': 'not_integrated',
                'reason': 'Model class labels do not include Resistant (1).',
            }

        prob_r = float(probas[0, r_idx])
        label = model.predict(x_row)[0]
        predicted = 'Resistant' if int(label) == 1 else 'Susceptible'

        return {
            'predicted': predicted,
            'score': round(prob_r, 4),
            'source': 'model_inference',
            'reason': None,
        }
    except Exception as e:
        return {
            'predicted': None,
            'score': None,
            'source': 'not_integrated',
            'reason': f'Model inference error: {e}',
        }
