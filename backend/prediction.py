"""Inference from trusted local artifacts; no uploaded pickle loading.

Supports live profile prediction for:
- Klebsiella pneumoniae (V2 Random Forest model; ceftazidime)
- Escherichia coli (Saved Logistic Regression models across 21 drugs; default: ciprofloxacin)
- Acinetobacter baumannii (Saved Logistic Regression models across 9 drugs; default: amikacin)
- Mycobacterium tuberculosis (16 Logistic Regression models across 16 drugs; default: rifampicin)
"""
import csv
import json
from functools import lru_cache
import io
import joblib
import pandas as pd
from pathlib import Path
import scipy.sparse
import numpy as np

from backend import dashboard

ROOT = dashboard.ROOT


@lru_cache(maxsize=2)
def load_kp_model(directory, modified):
    import joblib
    import sklearn
    path = Path(directory)
    metadata = json.loads((path / 'metadata.json').read_text(encoding='utf-8-sig'))
    if sklearn.__version__ != metadata['sklearn_version']:
        raise RuntimeError('Model runtime version does not match its training version.')
    model = joblib.load(path / 'model_with_threshold.joblib')
    if float(model.threshold) != float(metadata['threshold']):
        raise RuntimeError('Saved model threshold and metadata disagree.')
    return model, metadata


@lru_cache(maxsize=32)
def _load_multispecies_model_file(model_path_str, mtime_ns):
    import joblib
    return joblib.load(model_path_str)


@lru_cache(maxsize=4)
def _load_multispecies_feature_names(species_id):
    path = ROOT / 'data/processed/multispecies' / species_id / 'encoded/feature_names.json'
    if not path.is_file():
        return None
    names = json.loads(path.read_text(encoding='utf-8-sig'))
    return {name: idx for idx, name in enumerate(names)}


def _resolve_multispecies_model(species_id, drug=None, standard='CLSI'):
    base = ROOT / 'data/processed/multispecies' / species_id / 'encoded/supervised_models'
    if not base.is_dir():
        return None, None
    std = (standard or 'CLSI').upper()
    if drug:
        drug_clean = drug.lower().replace(' ', '_').replace('-', '_')
        candidate = base / f'{drug_clean}_{std}.joblib'
        if candidate.is_file():
            return candidate, drug
        # No fuzzy fallback – require exact match
        return None, None
    else:
        # Default drug per species
        default_drug = 'ciprofloxacin' if species_id == 'escherichia_coli' else 'amikacin'
        candidate = base / f'{default_drug}_{std}.joblib'
        if candidate.is_file():
            return candidate, default_drug
        # No fallback – require explicit default drug file
        return None, None


def predict(content, species, complete_profile, drug=None):
    if not complete_profile:
        raise ValueError('Please confirm a complete annotated AMR profile before running prediction.')

    normalized_species = (species or '').strip().lower()

    if 'klebsiella' in normalized_species:
        return _predict_kp(content)
    elif 'coli' in normalized_species:
        return _predict_multispecies(content, 'escherichia_coli', 'Escherichia coli', drug=drug)
    elif 'baumannii' in normalized_species:
        return _predict_multispecies(content, 'acinetobacter_baumannii', 'Acinetobacter baumannii', drug=drug)
    elif 'tuberculosis' in normalized_species:
        return _predict_tb(content, drug)

    else:
        raise ValueError(f'Species "{species}" is not recognized. '
                         'Supported species: Klebsiella pneumoniae, Escherichia coli, Acinetobacter baumannii, Mycobacterium tuberculosis.')


def _predict_kp(content):
    dashboard.validate_input(content)
    first = content.lstrip('\ufeff').splitlines()[0]
    rows = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff')),
                               delimiter='\t' if '\t' in first else ','))
    path, _ = dashboard.latest_model(ROOT)
    if path is None or not (path / 'model_with_threshold.joblib').is_file():
        raise RuntimeError('Saved V2 model is unavailable.')
    model, metadata = load_kp_model(str(path), (path / 'model_with_threshold.joblib').stat().st_mtime_ns)
    vocabulary = model.estimator_.named_steps['features'].vocabulary_
    prepared = []
    for row in rows:
        features = {}
        ignored = 0
        for token in row['AMR genotypes'].split(','):
            if not token.strip():
                continue
            name, status = (part.strip() for part in token.rsplit('=', 1))
            prefix = {'COMPLETE': 'gene:', 'POINT': 'mutation:'}.get(status)
            if prefix:
                features[prefix + name] = 1
            else:
                ignored += 1
        known = sum(key in vocabulary for key in features)
        prepared.append((row['BioSample'].strip(), features, known, ignored))
    eligible = [item for item in prepared if item[2]]
    predictions = {}
    if eligible:
        inputs = [item[1] for item in eligible]
        probabilities = model.predict_proba(inputs)[:, list(model.classes_).index(1)]
        labels = model.predict(inputs)
        predictions = {item[0]: (float(prob), int(label))
                       for item, prob, label in zip(eligible, probabilities, labels)}
    results = []
    for sample, features, known, ignored in prepared:
        probability, label = predictions.get(sample, (None, None))
        results.append({'sample': sample,
                        'prediction': None if label is None else ('Resistant' if label else 'Susceptible'),
                        'probability_R': probability, 'known_features': known,
                        'unseen_features': sorted(set(features) - set(vocabulary)),
                        'ignored_entries': ignored,
                        'status': 'research_prediction' if known else 'insufficient_known_features'})
    return {'target': 'ceftazidime', 'species': 'Klebsiella pneumoniae', 'model': metadata['candidate'],
            'version': 'V2', 'threshold': metadata['threshold'], 'samples': len(rows),
            'prediction_run': bool(eligible), 'results': results,
            'independent_validation': 'pending',
            'notice': 'Research baseline only. Probability is a model score, not calibrated confidence. '
                      'Missing calls are encoded as absent; incomplete profiles can produce misleading results. '
                      'No uncertainty or genomic novelty guarantee is provided. Independent validation pending.'}


@lru_cache(maxsize=2)
def _load_tb_artifacts(tb_base_str, feat_mtime_ns, cols_mtime_ns):
    """Load cached TB mutation vocabulary and selected training column map."""
    tb_base = Path(tb_base_str)
    feature_names = json.loads((tb_base / 'features/feature_names.json').read_text(encoding='utf-8-sig'))
    # Each entry is [gene, mutation] — build a lookup from "gene:mutation" → column index
    feat2idx = {}
    for idx, entry in enumerate(feature_names):
        if isinstance(entry, list) and len(entry) == 2:
            feat2idx[f'{entry[0]}:{entry[1]}'] = idx
        elif isinstance(entry, str):
            feat2idx[entry] = idx
    selected_cols = np.load(str(tb_base / 'supervised_models/selected_feature_cols.npy'))
    selected_set = set(selected_cols.tolist())
    col_to_pos = {int(c): i for i, c in enumerate(selected_cols)}
    return feat2idx, selected_cols, selected_set, col_to_pos


def _resolve_tb_feature(name, status, feat2idx, selected_set):
    """Resolve gene_mutation or gene:mutation tokens against the TB vocabulary."""
    prefix = {'COMPLETE': 'gene:', 'POINT': 'mutation:'}.get(status)
    if not prefix:
        return None, None
    candidates = [name, prefix + name]
    if ':' not in name and '_' in name:
        candidates.extend(
            f'{name[:i]}:{name[i + 1:]}'
            for i, ch in enumerate(name)
            if ch == '_' and i > 0 and i + 1 < len(name)
        )
    fallback_idx = None
    for candidate in candidates:
        idx = feat2idx.get(candidate)
        if idx is not None:
            if idx in selected_set:
                return candidate, idx
            if fallback_idx is None:
                fallback_idx = (candidate, idx)
    return fallback_idx if fallback_idx is not None else (prefix + name, None)


def _predict_tb(content, drug=None):
    """TB supervised prediction via saved LogisticRegression models + selected_feature_cols.npy."""
    dashboard.validate_input(content)
    first = content.lstrip('\ufeff').splitlines()[0]
    rows = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff')),
                               delimiter='\t' if '\t' in first else ','))

    # Load feature vocabulary (feature_names.json) and column selection mask for TB
    tb_base = ROOT / 'data/processed/multispecies/tuberculosis'
    feat_names_path = tb_base / 'features/feature_names.json'
    if not feat_names_path.is_file():
        raise RuntimeError('TB feature vocabulary (feature_names.json) is not available.')
    cols_path = tb_base / 'supervised_models/selected_feature_cols.npy'
    if not cols_path.is_file():
        raise RuntimeError('TB selected feature columns (selected_feature_cols.npy) is not available.')

    feat2idx, selected_cols, selected_set, col_to_pos = _load_tb_artifacts(
        str(tb_base),
        feat_names_path.stat().st_mtime_ns,
        cols_path.stat().st_mtime_ns,
    )

    # Resolve the drug model
    drug_code = (drug or 'rif').lower().replace(' ', '_').replace('-', '_')
    code_map = {
        'rifampicin': 'rif', 'isoniazid': 'inh', 'ethambutol': 'emb', 'pyrazinamide': 'pza',
        'amikacin': 'ami', 'capreomycin': 'cap', 'ethionamide': 'eth', 'kanamycin': 'kan',
        'levofloxacin': 'lev', 'moxifloxacin': 'mxf', 'ofloxacin': 'ofx', 'streptomycin': 'stm',
        'bedaquiline': 'bdq', 'clofazimine': 'cfz', 'linezolid': 'lzd',
        'para_aminosalicylic_acid': 'pas', 'rifabutin': 'rfb'
    }
    short_code = code_map.get(drug_code, drug_code[:3])
    model_path = tb_base / 'supervised_models' / f'{short_code}_WHO.joblib'
    if not model_path.is_file():
        raise ValueError(f'No saved TB model found for drug "{drug or "rifampicin"}" (code: {short_code}).')

    model = _load_multispecies_model_file(str(model_path), model_path.stat().st_mtime_ns)
    n_selected = len(selected_cols)
    if model.n_features_in_ != n_selected:
        raise RuntimeError(f'TB model feature dimension mismatch: model expects {model.n_features_in_}, got {n_selected}.')

    classes = list(model.classes_)
    if set(classes) != {0, 1}:
        raise RuntimeError('TB model must have binary Susceptible (0) / Resistant (1) classes.')
    r_idx = classes.index(1)

    results = []
    for row in rows:
        sample_id = row['BioSample'].strip()
        tokens = [t.strip() for t in row['AMR genotypes'].split(',') if t.strip()]
        known_positions = set()
        unseen = []
        for t in tokens:
            if '=' not in t:
                continue
            name, status = t.rsplit('=', 1)
            name = name.strip()
            status = status.strip()
            if status not in {'COMPLETE', 'POINT'}:
                continue
            feat_key, full_idx = _resolve_tb_feature(name, status, feat2idx, selected_set)
            if full_idx is not None and full_idx in selected_set:
                pos = col_to_pos.get(full_idx)
                if pos is not None:
                    known_positions.add(pos)
            else:
                unseen.append(feat_key)

        known_count = len(known_positions)
        if known_count > 0:
            row_vec = scipy.sparse.csr_matrix(
                ([1.0] * known_count, ([0] * known_count, sorted(known_positions))),
                shape=(1, n_selected)
            )
            prob = float(model.predict_proba(row_vec)[0, r_idx])
            pred_label = int(model.predict(row_vec)[0])
            pred_str = 'Resistant' if pred_label == 1 else 'Susceptible'
            results.append({
                'sample': sample_id,
                'prediction': pred_str,
                'probability_R': round(prob, 4),
                'known_features': known_count,
                'unseen_features': unseen,
                'ignored_entries': 0,
                'status': 'research_prediction'
            })
        else:
            results.append({
                'sample': sample_id,
                'prediction': None,
                'probability_R': None,
                'known_features': 0,
                'unseen_features': unseen,
                'ignored_entries': 0,
                'status': 'insufficient_known_features'
            })

    eligible_count = sum(r['prediction'] is not None for r in results)
    drug_display = {v: k.replace('_', ' ').title() for k, v in code_map.items()}.get(short_code, short_code.upper())

    return {
        'target': drug_display,
        'species': 'Mycobacterium tuberculosis',
        'model': f'{short_code}_WHO',
        'version': 'TB Logistic Regression baseline',
        'threshold': 0.5,
        'samples': len(rows),
        'prediction_run': eligible_count > 0,
        'results': results,
        'independent_validation': 'development_baselines',
        'notice': (f'Research baseline only. Development M. tuberculosis model for {drug_display}. '
                   f'16 drug models trained on 51,012 isolates (CRyPTIC + public WGS). '
                   f'Development test‑set metrics available in report.json. '
                   f'Results are not for clinical use.')
    }


def _predict_multispecies(content, species_id, display_species, drug=None):
    dashboard.validate_input(content)
    first = content.lstrip('\ufeff').splitlines()[0]
    rows = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff')),
                               delimiter='\t' if '\t' in first else ','))

    model_file, resolved_drug = _resolve_multispecies_model(species_id, drug)
    if model_file is None:
        raise ValueError(f'No saved model found for {drug or "default drug"} in {display_species}.')

    feat2idx = _load_multispecies_feature_names(species_id)
    if feat2idx is None:
        raise RuntimeError(f'Feature vocabulary unavailable for {display_species}.')

    n_features = len(feat2idx)
    model = _load_multispecies_model_file(str(model_file), model_file.stat().st_mtime_ns)

    if model.n_features_in_ != n_features:
        raise RuntimeError(f'Model feature dimension mismatch for {display_species}.')
    classes = list(model.classes_)
    if set(classes) != {0, 1}:
        raise RuntimeError('Model must have binary Susceptible (0) / Resistant (1) classes.')
    r_idx = classes.index(1)

    prepared = []
    results = []
    for row in rows:
        sample_id = row['BioSample'].strip()
        tokens = [t.strip() for t in row['AMR genotypes'].split(',') if t.strip()]
        known_indices = set()
        unseen = []
        for t in tokens:
            if t in feat2idx:
                known_indices.add(feat2idx[t])
            else:
                unseen.append(t)

        known_count = len(known_indices)
        if known_count > 0:
            # Construct sparse row
            row_vec = scipy.sparse.csr_matrix(
                ([1.0] * known_count, ([0] * known_count, sorted(known_indices))),
                shape=(1, n_features)
            )
            prob = float(model.predict_proba(row_vec)[0, r_idx]) if r_idx >= 0 else None
            pred_label = int(model.predict(row_vec)[0])
            pred_str = 'Resistant' if pred_label == 1 else 'Susceptible'
            results.append({
                'sample': sample_id,
                'prediction': pred_str,
                'probability_R': round(prob, 4) if prob is not None else None,
                'known_features': known_count,
                'unseen_features': unseen,
                'ignored_entries': 0,
                'status': 'research_prediction'
            })
        else:
            results.append({
                'sample': sample_id,
                'prediction': None,
                'probability_R': None,
                'known_features': 0,
                'unseen_features': unseen,
                'ignored_entries': 0,
                'status': 'insufficient_known_features'
            })

    eligible_count = sum(r['prediction'] is not None for r in results)

    return {
        'target': resolved_drug,
        'species': display_species,
        'model': model_file.stem,
        'version': 'Multispecies Logistic Regression baseline',
        'threshold': 0.5,
        'samples': len(rows),
        'prediction_run': eligible_count > 0,
        'results': results,
        'independent_validation': 'pending',
        'notice': (f'Research baseline only. Development {display_species} model for {resolved_drug}. '
                   f'Independent external validation remains pending. Results are not for clinical use.')
    }
