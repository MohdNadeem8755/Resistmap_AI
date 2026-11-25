"""Read-only dashboard data adapters. No training or arbitrary file downloads."""
import csv
from datetime import datetime, timezone
from functools import lru_cache
import io
import json
import math
import os
from pathlib import Path
import time

ROOT = Path(os.environ.get('RESISTMAP_ROOT', Path(__file__).resolve().parents[1]))


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return default


def read_csv(path):
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def latest_model(root):
    for path in sorted((root/'results').glob('ceftazidime_v2_*'), reverse=True):
        meta = read_json(path/'metadata.json')
        if meta and (path/'development_selection.csv').exists():
            return path, meta
    return None, {}


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False


def _run_model_inference(species_id, sample_id, drug, standard):
    """Return available inference without substituting observed laboratory labels."""
    try:
        from backend.multispecies_predict import predict_sample
        return predict_sample(species_id, sample_id, drug, standard)
    except Exception:
        return None


def _species_id(species_name):
    """Map display name to directory ID."""
    mapping = {
        'Escherichia coli': 'escherichia_coli',
        'E. coli': 'escherichia_coli',
        'Acinetobacter baumannii': 'acinetobacter_baumannii',
        'A. baumannii': 'acinetobacter_baumannii',
        'Mycobacterium tuberculosis': 'tuberculosis',
        'M. tuberculosis': 'tuberculosis',
    }
    return mapping.get(species_name)


def _build_example(sample_id, species, drug, standard, observed_label, split, species_id):
    """Build example entry with genuine model inference."""
    observed = 'Resistant' if observed_label == 1 else 'Susceptible' if observed_label == 0 else 'Unavailable'
    inference = _run_model_inference(species_id, sample_id, drug, standard)
    if inference and inference.get('source') == 'model_inference':
        predicted = inference['predicted']
        score = inference['score']
        score_source = 'model_inference'
    else:
        predicted = None
        score = None
        score_source = 'not_integrated'

    return {
        'sample': sample_id,
        'species': species,
        'drug': drug,
        'standard': standard,
        'predicted': predicted,
        'observed': observed,
        'score': score,
        'score_source': score_source,
        'split': split,
    }


@lru_cache(maxsize=4)
def ab_source_phenotypes(root):
    from collections import defaultdict
    grouped = defaultdict(set)
    source = root/'data/multispecies/acinetobacter_baumannii/abaumannii_ast.tsv'
    if source.is_file():
        with source.open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter='\t'):
                grouped[(row['#BioSample'], row['Antibiotic'], row['Testing standard'])].add(
                    row['Resistance phenotype'].strip().lower())
    return grouped


def get_species_examples(root=ROOT):
    results = root / 'results'
    kp_rows = read_csv(results / 'ceftazidime_clsi_test_predictions_v1.csv')

    # Klebsiella pneumoniae: Genuine verified model predictions and scores
    kp_examples = [
        {
            'sample': row['BioSample'],
            'species': 'Klebsiella pneumoniae',
            'drug': 'ceftazidime',
            'standard': 'CLSI',
            'predicted': {'0': 'Susceptible', '1': 'Resistant'}.get(row.get('predicted'), 'Unavailable'),
            'observed': {'0': 'Susceptible', '1': 'Resistant'}.get(row.get('actual'), 'Unavailable'),
            'score': num(row.get('probability_R')),
            'score_source': 'saved_v1_prediction',
            'split': 'test'
        }
        for row in kp_rows
    ]

    ec_examples_def = [
        ('SAMN48878206', 'ciprofloxacin', 'CLSI', 1, 'test'),
        ('SAMN48878816', 'ciprofloxacin', 'CLSI', 1, 'test'),
        ('SAMN06641883', 'ciprofloxacin', 'CLSI', 0, 'test'),
        ('SAMN48878210', 'ciprofloxacin', 'CLSI', 0, 'test'),
        ('SAMN03075588', 'ampicillin', 'CLSI', 1, 'train'),
        ('SAMN03177649', 'amoxicillin-clavulanic acid', 'CLSI', 0, 'test'),
        ('SAMN04014847', 'gentamicin', 'CLSI', 1, 'test'),
        ('SAMN03177650', 'ciprofloxacin', 'CLSI', 0, 'test'),
    ]
    ec_examples = [
        _build_example(sid, 'Escherichia coli', drug, std, obs, split, 'escherichia_coli')
        for sid, drug, std, obs, split in ec_examples_def
    ]

    ab_examples_def = [
        ('SAMN04211933', 'amikacin', 'CLSI', 1, 'test'),
        ('SAMN04211931', 'amikacin', 'CLSI', 1, 'test'),
        ('SAMN02437332', 'amikacin', 'CLSI', 0, 'test'),
        ('SAMN04208819', 'amikacin', 'CLSI', 0, 'test'),
        ('SAMN02646214', 'ampicillin-sulbactam', 'CLSI', 1, 'test'),
        ('SAMN04014877', 'ceftazidime', 'CLSI', 1, 'train'),
        ('SAMN02437318', 'amikacin', 'CLSI', 0, 'test'),
    ]
    ab_base = root/'data/processed/multispecies/acinetobacter_baumannii'
    try:
        import pandas as pd
        labs = pd.read_parquet(ab_base/'candidate_labels.parquet',
            columns=['#BioSample', 'Antibiotic', 'Testing standard', 'target'])
        lab_records = labs.groupby(['#BioSample', 'Antibiotic', 'Testing standard'])['target'].unique().to_dict()
    except (ImportError, OSError):
        lab_records = {}
    splits = {r['BioSample']: r['split'] for r in read_csv(ab_base/'encoded/samples.csv')}
    ab_examples = []
    for sid, drug, std, _, _ in ab_examples_def:
        labels = lab_records.get((sid, drug, std), [])
        example = _build_example(sid, 'Acinetobacter baumannii', drug, std,
            labels[0] if len(labels) == 1 else None, splits.get(sid), 'acinetobacter_baumannii')
        ab_examples.append(example)
        example['source_phenotypes'] = sorted(ab_source_phenotypes(root).get((sid, drug, std), ()))

    tb_examples_def = [
        ('SAMEA10029749', 'rifampicin', 'WHO/DST', 1, 'test'),
        ('SAMEA10029751', 'rifampicin', 'WHO/DST', 1, 'test'),
        ('SAMEA13299636', 'rifampicin', 'WHO/DST', 0, 'test'),
        ('SAMEA13299637', 'rifampicin', 'WHO/DST', 0, 'test'),
        ('SAMEA10029752', 'isoniazid', 'WHO/DST', 1, 'test'),
        ('SAMEA13299638', 'isoniazid', 'WHO/DST', 0, 'test'),
    ]
    tb_examples = [
        _build_example(sid, 'Mycobacterium tuberculosis', drug, std, obs, split, 'tuberculosis')
        for sid, drug, std, obs, split in tb_examples_def
    ]

    return {
        'Klebsiella pneumoniae': kp_examples,
        'Escherichia coli': ec_examples,
        'Acinetobacter baumannii': ab_examples,
        'Mycobacterium tuberculosis': tb_examples,
    }


def snapshot(root=ROOT):
    results = root/'results'
    scale = results/'ceftazidime_sequence_scaleup'
    pilot = results/'ceftazidime_sequence_pilot'
    queue = read_csv(scale/'development_processing_queue.csv')
    progress = read_json(scale/'assembly_progress.json', {})
    job = read_json(scale/'assembly_job_status.json', {})
    status = job.get('status', 'not_started')
    if status == 'running' and not process_alive(job.get('pid')):
        status = 'interrupted'
    source_manifest = read_json(scale/'assembly_download_manifest.json', [])
    pilot_rows = {r['BioSample']: r for r in read_csv(pilot/'pilot_processing_summary.csv')}
    qc_rows = {r['BioSample']: r for r in read_csv(pilot/'biological_qc/pilot_biological_qc_summary.csv')}
    batch_qc = {r['BioSample']:r for r in read_csv(scale/'assembly_qc_summary.csv')}
    done = {}
    for path in (scale/'completed').glob('*.json'):
        result = read_json(path, {})
        if result.get('summary'):
            done[result['summary']['BioSample']] = result['summary']
    labels = {r['BioSample']:r.get('actual') for r in read_csv(results/'ceftazidime_rf_oof_predictions.csv')}
    errors = {r['BioSample']:r.get('error','Processing error') for r in progress.get('failures',[])}
    samples = []
    for row in queue:
        sample = row['BioSample']
        summary = done.get(sample, pilot_rows.get(sample, {}))
        qc = batch_qc.get(sample, qc_rows.get(sample, {}))
        notes = []
        if qc.get('source_quality_note'):
            notes.append(qc['source_quality_note'])
        warning = qc.get('QC_warnings', qc.get('Kleborate_QC_warnings',''))
        if warning and warning != '-':
            notes.append(warning)
        if qc and (qc.get('species') != 'Klebsiella pneumoniae' or qc.get('species_match') != 'strong'):
            notes.append('Species identity requires review')
        if sample in errors:
            notes.append(errors[sample])
        state = 'review' if notes else 'annotated' if summary else 'queued'
        samples.append({'id':sample,'isolate':row['Isolate'],'project':row['BioProject'],
            'assembly':row['Assembly'],'run':row['Run'],'source':row['source'],'status':state,
            'phenotype':{'0':'Susceptible','1':'Resistant'}.get(labels.get(sample),'Unavailable'),
            'contigs':num(summary.get('contigs')),'n50':num(summary.get('N50')),
            'length_bp':num(summary.get('length_bp')),'amr_hits':num(summary.get('AMR_report_rows')),
            'features':num(summary.get('expanded_feature_count',summary.get('feature_count'))),
            'species':qc.get('species'),'species_match':qc.get('species_match'),
            'qc_screened':bool(qc),'notes':notes,'annotated':bool(summary)})
    model_path, metadata = latest_model(root)
    candidates = read_csv(model_path/'development_selection.csv') if model_path else []
    selected = next((r for r in candidates if r['candidate']==metadata.get('candidate')
                     and num(r['threshold'])==num(metadata.get('threshold'))), None)
    metrics = {k:num(selected.get(k)) for k in ['accuracy','balanced_accuracy','S_recall','R_recall','roc_auc','worst_fold_BA']} if selected else {}
    folds = [{k:num(v) for k,v in row.items()} for row in read_csv(model_path/'selected_development_folds.csv')] if model_path else []
    legacy = {r['']:num(r['score']) for r in read_csv(results/'ceftazidime_clsi_test_scores_v1.csv')}
    confusion_rows = read_csv(results/'ceftazidime_clsi_test_confusion_v1.csv')
    confusion = [[num(r.get('Predicted susceptible')),num(r.get('Predicted resistant'))] for r in confusion_rows]
    counts = {key:sum(r['status']==key for r in samples) for key in ['annotated','queued','review']}
    return {'generated_at':datetime.now(timezone.utc).isoformat(),
        'presentation_examples': [{'sample': row['BioSample'],
            'predicted': {'0': 'Susceptible', '1': 'Resistant'}.get(row.get('predicted'), 'Unavailable'),
            'observed': {'0': 'Susceptible', '1': 'Resistant'}.get(row.get('actual'), 'Unavailable'),
            'score': num(row.get('probability_R'))}
            for row in read_csv(results/'ceftazidime_clsi_test_predictions_v1.csv')],
        'species_examples': get_species_examples(root),
        'ab_external_screen': [
            {k: row[k] for k in ('project', 'sample_records', 'overlapping_sample_records')}
            for row in read_json(root/'data/external/multispecies_candidate_screen/screen_report.json', [])
            if row.get('species') == 'acinetobacter_baumannii' and 'overlapping_sample_records' in row
        ],
        'multispecies': multispecies_summary(root),
        'cohort':{'total':len(samples),'projects':len({r['project'] for r in samples}),
                  'susceptible':sum(r['phenotype']=='Susceptible' for r in samples),
                  'resistant':sum(r['phenotype']=='Resistant' for r in samples),
                  'assembly_sources':sum(r['source']=='assembly' for r in samples),
                  'read_sources':sum(r['source']=='reads' for r in samples),
                  'annotated':sum(r['annotated'] for r in samples),'qc_screened':sum(r['qc_screened'] for r in samples),
                  'read_completed':sum(r['annotated'] and r['source']=='reads' for r in samples),
                  'counts':counts},
        'pipeline':{'status':status,'stage':job.get('stage','waiting'),
                    'completed':len(done),'total':sum(r['source']=='assembly' for r in samples),
                    'sources_verified':len(source_manifest),'failures':progress.get('failures',[]),
                    'updated_unix':progress.get('updated_unix'),'error':job.get('error'),
                    'fresh_accuracy':None,'contamination_screen':'Pending'},
        'model':{'name':metadata.get('candidate'), 'version':'V2', 'threshold':metadata.get('threshold'),
                 'metrics':metrics,'folds':folds,'scope':'Development CV selection',
                 'measured_scores':read_json(model_path/'measured_scores.json', {}) if model_path else {},
                 'independent_validation':'Required','legacy_metrics':legacy,'legacy_confusion':confusion,
                 'candidates':[{'name':r['candidate'],'threshold':num(r['threshold']),
                                'accuracy':num(r['accuracy']),'balanced_accuracy':num(r['balanced_accuracy'])} for r in candidates[:8]]},
        'samples':samples,'reports':report_inventory(root)}


def tb_unsupervised_available(root=ROOT):
    base = root / 'data/processed/multispecies/tuberculosis/unsupervised_profiles'
    required = ['clusters/report.json', 'clusters/assignments.parquet',
                'clusters/cluster_overview.png', 'svd/report.json',
                'svd/embedding.npy', 'svd/svd_overview.png']
    return all((base / name).is_file() for name in required)


def multispecies_summary(root=ROOT):
    """Expose saved multispecies development summaries without loading large matrices."""
    base = root / 'data/processed/multispecies'
    output = []
    for species, label in [('escherichia_coli', 'E. coli'), ('acinetobacter_baumannii', 'A. baumannii')]:
        unsup = read_json(base / species / 'unsupervised_profiles/report.json', {}) or {}
        model = read_json(base / species / 'encoded/supervised_models/report.json', {}) or {}
        anomaly = read_json(base / species / 'unsupervised_profiles/anomaly_resampling/report.json', {}) or {}
        metrics_path = base / species / 'encoded/supervised_models/metrics.csv'
        per_drug = read_csv(metrics_path) if metrics_path.is_file() else []
        scores = {}
        for s in model.get('summary', []):
            sp = s.get('split')
            if sp:
                scores[sp] = {
                    'accuracy': num(s.get('macro_accuracy')),
                    'balanced_accuracy': num(s.get('macro_balanced_accuracy')),
                    'f1_resistant': num(s.get('macro_f1_resistant')),
                    'roc_auc': num(s.get('macro_roc_auc')),
                    'tasks': s.get('tasks')
                }
        output.append({'species': label, 'encoded_samples': unsup.get('encoded_samples'),
            'id': species,
            'clustering': read_json(base / species / 'unsupervised_profiles/clusters/report.json', {}),
            'projection': read_json(base / species / 'unsupervised_profiles/svd/report.json', {}),
            'anomaly_review': anomaly,
            'genomic_features': unsup.get('features'), 'unique_profiles': unsup.get('unique_profiles'),
            'eligible_tasks_trained': model.get('eligible_tasks_trained', 0),
            'supervised_summary': model.get('summary', []),
            'scores': scores,
            'per_drug_metrics': per_drug,
            'anomaly_validation_samples': anomaly.get('validation_samples'),
            'anomaly_rank_correlation': anomaly.get('pairwise_spearman_range'),
            'status': 'development baseline; independent validation pending'})
    tb_features = read_json(base / 'tuberculosis/features/report.json', {}) or {}
    tb_supervised = read_json(base / 'tuberculosis/supervised_models/report.json', {}) or {}
    tb_metrics = []
    tb_metrics_path = base / 'tuberculosis/supervised_models/metrics.csv'
    if tb_metrics_path.is_file():
        tb_metrics = read_csv(tb_metrics_path)
    tb_per_drug = tb_supervised.get('per_drug_test', [])
    tb_trained = tb_supervised.get('eligible_tasks_trained', 0)
    tb_skipped = tb_supervised.get('drugs_skipped', 0)
    tb_scores = {}
    for s in tb_supervised.get('summary', []):
        sp = s.get('split')
        if sp:
            tb_scores[sp] = {
                'accuracy': num(s.get('macro_accuracy')),
                'balanced_accuracy': num(s.get('macro_balanced_accuracy')),
                'f1_resistant': num(s.get('macro_f1_resistant')),
                'roc_auc': num(s.get('macro_roc_auc')),
                'tasks': s.get('tasks')
            }
    if tb_supervised:
        tb_status = (f'{tb_trained} drug models trained; {tb_skipped} skipped '
                     f'(insufficient class support). Runtime prediction enabled; '
                     f'development baselines; independent validation pending.')
    elif tb_features:
        tb_status = 'Genomic features complete; supervised training complete but reports loading failed.'
    else:
        tb_status = 'Preprocessed cohort; genomic feature matrix pending.'
    output.append({
        'species': 'M. tuberculosis',
        'encoded_samples': tb_features.get('samples'),
        'id': 'tuberculosis',
        'clustering': read_json(base / 'tuberculosis' / 'unsupervised_profiles' / 'clusters' / 'report.json', {}),
        'projection': read_json(base / 'tuberculosis' / 'unsupervised_profiles' / 'svd' / 'report.json', {}),
        'anomaly_review': {},
        'genomic_features': tb_features.get('features'),
        'unique_profiles': None,
        'eligible_tasks_trained': tb_trained,
        'supervised_summary': tb_supervised.get('summary', []),
        'scores': tb_scores,
        'per_drug_metrics': tb_metrics,
        'per_drug_test': tb_per_drug,
        'drugs_skipped': tb_skipped,
        'anomaly_validation_samples': None,
        'anomaly_rank_correlation': None,
        'unsupervised_available': tb_unsupervised_available(root),
        'status': tb_status
    })
    return {'species': output, 'tb_features': tb_features,
            'tb_supervised': tb_supervised,
            'tb_status': tb_status,
            'scope': 'Saved development analyses only; no external validation claim.'}


@lru_cache(maxsize=1)
def load_all_sample_tables(root_str):
    root = Path(root_str)
    base = root / 'data/processed/multispecies'
    import pandas as pd
    ec_df, ab_df, tb_df = None, None, None
    ec_path = base / 'escherichia_coli/encoded/targets.parquet'
    if ec_path.is_file():
        ec_df = pd.read_parquet(ec_path, columns=['BioSample', 'Antibiotic', 'Testing standard', 'target', 'split'])
    ab_path = base / 'acinetobacter_baumannii/encoded/targets.parquet'
    if ab_path.is_file():
        ab_df = pd.read_parquet(ab_path, columns=['BioSample', 'Antibiotic', 'Testing standard', 'target', 'split'])
    tb_path = base / 'tuberculosis/features/labels.parquet'
    if tb_path.is_file():
        tb_df = pd.read_parquet(tb_path, columns=['sample_accession', 'DRUG', 'target'])
    return ec_df, ab_df, tb_df


class CohortLookupUnavailable(RuntimeError):
    pass


def lookup_sample(sample_id, species=None, drug=None, root=ROOT):
    sid = (sample_id or '').strip()
    if not sid:
        return {
            'found': False,
            'sample': '',
            'species': 'Unknown',
            'status': 'Not Susceptible/Resistant',
            'reason': 'Please enter a valid sample ID.',
            'explanation': 'No sample ID was provided. Enter a BioSample accession (e.g. SAMN48878206, SAMN02437332, SAMEA13299636) to inspect its resistance status.'
        }

    # 1. Klebsiella pneumoniae
    kp_examples = [r for r in read_csv(root/'results/ceftazidime_clsi_test_predictions_v1.csv') if r.get('BioSample','').upper() == sid.upper()]
    if kp_examples:
        r = kp_examples[0]
        obs = 'Resistant' if str(r.get('actual')) == '1' else 'Susceptible' if str(r.get('actual')) == '0' else 'Not Susceptible/Resistant'
        pred = 'Resistant' if str(r.get('predicted')) == '1' else 'Susceptible' if str(r.get('predicted')) == '0' else 'Not Susceptible/Resistant'
        score = num(r.get('probability_R'))
        explanation = (f'Sample {r["BioSample"]} is a Klebsiella pneumoniae isolate evaluated in the CLSI ceftazidime test cohort. '
                       f'Laboratory testing confirmed this sample as {obs} to ceftazidime. The saved V1 development classification '
                       f'was {pred} with an estimated resistance score of {score:.3f}. Clinical decisions must be confirmed with local laboratory susceptibility testing.')
        return {
            'found': True, 'sample': r['BioSample'], 'species': 'Klebsiella pneumoniae',
            'drug': 'ceftazidime', 'standard': 'CLSI', 'status': obs, 'predicted': pred,
            'score': score, 'split': 'test', 'drugs': [{'drug': 'ceftazidime', 'status': obs, 'split': 'test'}],
            'explanation': explanation
        }

    # Load multispecies tables
    try:
        ec_df, ab_df, tb_df = load_all_sample_tables(str(root))
    except (ImportError, OSError) as exc:
        for name, examples in get_species_examples(root).items():
            if species and species.casefold() != name.casefold():
                continue
            for example in examples:
                if example['sample'].casefold() != sid.casefold():
                    continue
                if drug and example['drug'].casefold() != drug.casefold():
                    continue
                return {**example, 'found': True, 'status': example['observed'],
                        'drugs': [], 'explanation': f"Showing the dashboard example for {example['sample']} and {example['drug']}. Full cohort records are unavailable."}
        raise CohortLookupUnavailable('The full cohort records could not be read.') from exc

    # 2. Escherichia coli
    if ec_df is not None:
        match = ec_df[ec_df['BioSample'].str.upper() == sid.upper()]
        if not match.empty:
            drugs = [{'drug': row['Antibiotic'], 'status': 'Resistant' if row['target']==1 else 'Susceptible', 'split': row['split'], 'standard': row['Testing standard']} for _, row in match.iterrows()]
            # Task 3: Handle antibiotic selection correctly
            if drug:
                primary = match[match['Antibiotic'].str.lower() == drug.lower()]
                if primary.empty:
                    # Requested antibiotic not found — report this explicitly
                    available_drugs = sorted(match['Antibiotic'].unique())
                    return {
                        'found': True, 'sample': match.iloc[0]['BioSample'], 'species': 'Escherichia coli',
                        'drug': drug, 'standard': 'CLSI', 'status': 'Unavailable',
                        'predicted': None, 'score': None, 'score_source': 'not_available',
                        'split': match.iloc[0]['split'],
                        'drugs': drugs,
                        'explanation': (f'Sample {match.iloc[0]["BioSample"]} is an Escherichia coli isolate in the development cohort, '
                                        f'but was not tested against {drug}. Available antibiotics for this sample: {", ".join(available_drugs)}.')
                    }
            else:
                primary = match[match['Antibiotic'] == 'ciprofloxacin']
                if primary.empty:
                    primary = match.iloc[[0]]
            r = primary.iloc[0]
            observed = 'Resistant' if r['target'] == 1 else 'Susceptible'
            inference = _run_model_inference('escherichia_coli', r['BioSample'], r['Antibiotic'], r['Testing standard'])
            if inference and inference.get('source') == 'model_inference':
                predicted = inference['predicted']
                score = inference['score']
                score_source = 'model_inference'
            else:
                predicted = None
                score = None
                score_source = 'not_integrated'
            explanation = (f'Sample {r["BioSample"]} was identified as an Escherichia coli isolate from the verified development cohort ({r["split"]} split). '
                           f'In laboratory AST (Testing standard: {r["Testing standard"]}), this isolate was characterized as {observed} to {r["Antibiotic"]}. ')
            if score_source == 'model_inference':
                explanation += f'Model prediction: {predicted} (score: {score:.4f}). '
            else:
                explanation += 'Model prediction: Unavailable. '
            explanation += (f'A total of {len(drugs)} antibiotic panels were recorded for this isolate: {sum(d["status"]=="Resistant" for d in drugs)} resistant and {sum(d["status"]=="Susceptible" for d in drugs)} susceptible. '
                           f'Development baseline; independent clinical validation pending.')
            return {
                'found': True, 'sample': r['BioSample'], 'species': 'Escherichia coli',
                'drug': r['Antibiotic'], 'standard': r['Testing standard'], 'status': observed,
                'predicted': predicted, 'score': score, 'score_source': score_source, 'split': r['split'],
                'drugs': drugs,
                'explanation': explanation
            }

    # 3. Acinetobacter baumannii
    if ab_df is not None:
        match = ab_df[ab_df['BioSample'].str.upper() == sid.upper()]
        if not match.empty:
            drugs = [{'drug': row['Antibiotic'], 'status': 'Resistant' if row['target']==1 else 'Susceptible', 'split': row['split'], 'standard': row['Testing standard']} for _, row in match.iterrows()]
            # Task 3: Handle antibiotic selection correctly
            if drug:
                primary = match[match['Antibiotic'].str.lower() == drug.lower()]
                if primary.empty:
                    available_drugs = sorted(match['Antibiotic'].unique())
                    return {
                        'found': True, 'sample': match.iloc[0]['BioSample'], 'species': 'Acinetobacter baumannii',
                        'drug': drug, 'standard': 'CLSI', 'status': 'Unavailable',
                        'predicted': None, 'score': None, 'score_source': 'not_available',
                        'split': match.iloc[0]['split'],
                        'drugs': drugs,
                        'explanation': (f'Sample {match.iloc[0]["BioSample"]} is an Acinetobacter baumannii isolate in the development cohort, '
                                        f'but was not tested against {drug}. Available antibiotics for this sample: {", ".join(available_drugs)}.')
                    }
            else:
                primary = match[match['Antibiotic'] == 'amikacin']
                if primary.empty:
                    primary = match.iloc[[0]]
            r = primary.iloc[0]
            observed = 'Resistant' if r['target'] == 1 else 'Susceptible'
            inference = _run_model_inference('acinetobacter_baumannii', r['BioSample'], r['Antibiotic'], r['Testing standard'])
            if inference and inference.get('source') == 'model_inference':
                predicted = inference['predicted']
                score = inference['score']
                score_source = 'model_inference'
            else:
                predicted = None
                score = None
                score_source = 'not_integrated'
            explanation = (f'Sample {r["BioSample"]} was identified as an Acinetobacter baumannii isolate from the verified development cohort ({r["split"]} split). '
                           f'Laboratory reference assay determined this isolate to be {observed} to {r["Antibiotic"]} ({r["Testing standard"]}). ')
            if score_source == 'model_inference':
                explanation += f'Model prediction: {predicted} (score: {score:.4f}). '
            else:
                explanation += 'Model prediction: Unavailable. '
            explanation += (f'Across all tested panels ({len(drugs)} antibiotics), {sum(d["status"]=="Resistant" for d in drugs)} were resistant and {sum(d["status"]=="Susceptible" for d in drugs)} were susceptible. '
                           f'Development baseline; independent clinical validation pending.')
            return {
                'found': True, 'sample': r['BioSample'], 'species': 'Acinetobacter baumannii',
                'source_phenotypes': sorted(ab_source_phenotypes(root).get((r['BioSample'], r['Antibiotic'], r['Testing standard']), ())),
                'drug': r['Antibiotic'], 'standard': r['Testing standard'], 'status': observed,
                'predicted': predicted, 'score': score, 'score_source': score_source, 'split': r['split'],
                'drugs': drugs,
                'explanation': explanation
            }

    # 4. Mycobacterium tuberculosis
    if tb_df is not None:
        match = tb_df[tb_df['sample_accession'].str.upper() == sid.upper()]
        if not match.empty:
            # Drug name ↔ short code mapping for TB
            _tb_name_to_code = {
                'rifampicin': 'rif', 'isoniazid': 'inh', 'ethambutol': 'emb', 'pyrazinamide': 'pza',
                'amikacin': 'ami', 'capreomycin': 'cap', 'ethionamide': 'eth', 'kanamycin': 'kan',
                'levofloxacin': 'lev', 'moxifloxacin': 'mxf', 'ofloxacin': 'ofx', 'streptomycin': 'stm',
                'bedaquiline': 'bdq', 'clofazimine': 'cfz', 'linezolid': 'lzd',
                'para-aminosalicylic acid': 'pas', 'para_aminosalicylic_acid': 'pas', 'rifabutin': 'rfb',
            }
            _tb_code_to_name = {v: k for k, v in _tb_name_to_code.items() if '_' not in k}
            drugs = [{'drug': row['DRUG'], 'status': 'Resistant' if row['target']==1 else 'Susceptible'} for _, row in match.iterrows()]
            # Task 3: Handle antibiotic selection correctly
            if drug:
                drug_lower = drug.lower().replace('-', ' ').replace('_', ' ')
                # Try matching by short code directly, or by full name → short code
                drug_code = _tb_name_to_code.get(drug_lower.replace(' ', '_'), _tb_name_to_code.get(drug_lower, drug_lower))
                primary = match[match['DRUG'].str.lower().isin([drug_lower, drug_code])]
                if primary.empty:
                    available_drugs = sorted(match['DRUG'].unique())
                    return {
                        'found': True, 'sample': match.iloc[0]['sample_accession'], 'species': 'Mycobacterium tuberculosis',
                        'drug': drug, 'standard': 'WHO/DST', 'status': 'Unavailable',
                        'predicted': None, 'score': None, 'score_source': 'not_available',
                        'split': 'multispecies cohort',
                        'drugs': drugs,
                        'explanation': (f'Sample {match.iloc[0]["sample_accession"]} is a Mycobacterium tuberculosis isolate in the cohort, '
                                        f'but was not tested against {drug}. Available drugs for this sample: {", ".join(available_drugs)}.')
                    }
            else:
                primary = match[match['DRUG'] == 'rif']
                if primary.empty:
                    primary = match.iloc[[0]]
            r = primary.iloc[0]
            observed = 'Resistant' if r['target'] == 1 else 'Susceptible'
            drug_name = {'rif': 'Rifampicin', 'inh': 'Isoniazid', 'emb': 'Ethambutol', 'pza': 'Pyrazinamide',
                         'ami': 'Amikacin', 'cap': 'Capreomycin', 'eth': 'Ethionamide', 'kan': 'Kanamycin',
                         'lev': 'Levofloxacin', 'mxf': 'Moxifloxacin', 'ofx': 'Ofloxacin', 'stm': 'Streptomycin',
                         'bdq': 'Bedaquiline', 'cfz': 'Clofazimine', 'lzd': 'Linezolid', 'pas': 'Para-aminosalicylic acid',
                         'rfb': 'Rifabutin'}.get(r['DRUG'].lower(), r['DRUG'].upper())
            inference = _run_model_inference('tuberculosis', r['sample_accession'], r['DRUG'], 'WHO/DST')
            if inference and inference.get('source') == 'model_inference':
                predicted = inference['predicted']
                score = inference['score']
                score_source = 'model_inference'
            else:
                predicted = None
                score = None
                score_source = 'not_integrated'
            explanation = (f'Sample {r["sample_accession"]} is a Mycobacterium tuberculosis isolate from the 51,012-sample genomic cohort. '
                           f'Reference phenotypic testing identified this isolate as {observed} to {drug_name} (code: {r["DRUG"]}). ')
            if score_source == 'model_inference':
                explanation += f'Model prediction: {predicted} (score: {score:.4f}). '
            else:
                explanation += 'Model prediction: Unavailable. '
            explanation += (f'A total of {len(drugs)} anti-TB drugs were recorded for this isolate. '
                           f'Development baseline; independent clinical validation pending.')
            return {
                'found': True, 'sample': r['sample_accession'], 'species': 'Mycobacterium tuberculosis',
                'drug': drug_name, 'standard': 'WHO/DST', 'status': observed,
                'predicted': predicted, 'score': score, 'score_source': score_source,
                'split': 'multispecies cohort',
                'drugs': drugs,
                'explanation': explanation
            }

    # If not found in any cohort
    return {
        'found': False,
        'sample': sid,
        'species': species or 'Unknown',
        'status': 'Not Susceptible/Resistant',
        'reason': 'Sample ID not found in development cohorts or reference datasets.',
        'drug': '—',
        'split': 'Not in cohort',
        'score': None,
        'drugs': [],
        'explanation': (f'Sample ID "{sid}" was not found in any of the verified ResistMap development cohorts '
                       f'(Klebsiella pneumoniae, Escherichia coli, Acinetobacter baumannii, or Mycobacterium tuberculosis). '
                       f'Because no genomic mutations, phenotypic assays, or metadata are recorded for this identifier, '
                       f'it is classified as Not Susceptible/Resistant (Status: Unavailable). To evaluate a custom isolate, '
                       f'use the Genomic Input Workspace to validate and upload its annotated AMR calls.')
    }


def report_paths(root=ROOT):
    r=root/'results'
    model,_=latest_model(root)
    files={
        'queue':('Development cohort','445-sample source and processing manifest',r/'ceftazidime_sequence_scaleup/development_processing_queue.csv'),
        'pilot-qc':('Pilot quality review','Species, assembly and read-mapping checks',r/'ceftazidime_sequence_pilot/biological_qc/pilot_biological_qc_summary.csv'),
        'assembly-qc':('Assembly batch QC','Species and assembly results for the full batch',r/'ceftazidime_sequence_scaleup/assembly_qc_summary.csv'),
        'legacy-test':('V1 reserved-test scores','Historical 114-sample evaluation',r/'ceftazidime_clsi_test_scores_v1.csv'),
        'anomaly':('Anomaly review','Held-out unsupervised review scores',r/'heldout_anomaly_review.csv')}
    if model:
        files['model-selection']=('V2 model selection','Development cross-validation results',model/'development_selection.csv')
    return files


def report_inventory(root=ROOT):
    return [{'id':key,'name':title,'description':desc,'available':p.exists(),
             'bytes':p.stat().st_size if p.exists() else 0,'filename':p.name}
            for key,(title,desc,p) in report_paths(root).items()]


@lru_cache(maxsize=4)
def explore_cached(root_name, fingerprint):
    root=Path(root_name)
    rows=read_csv(root/'results/sample_analysis.csv')
    points=[]
    clusters={}
    countries={}
    lookup={}
    for r in rows:
        x,y=num(r.get('complete_gene_count')),num(r.get('anomaly_score'))
        if x is None or y is None:
            continue
        cluster=str(r.get('cluster','Unknown'))
        review=r.get('review_flag','').lower()=='true'
        points.append({'id':r['Isolate'],'x':x,'y':y,'cluster':cluster,'review':review})
        lookup[r['Isolate']]=cluster
        clusters[cluster]=clusters.get(cluster,0)+1
        country=(r.get('Location') or 'Unknown').split(':')[0].strip() or 'Unknown'
        countries[country]=countries.get(country,0)+1
    feature_rows=read_csv(root/'data/processed/klebsiella_amr_features.csv')
    gene_keys=[k for k in (feature_rows[0] if feature_rows else {}) if k.startswith('gene__')]
    totals={k:0 for k in gene_keys}
    by_cluster={}
    denominators={}
    for row in feature_rows:
        cluster=lookup.get(row['Isolate'])
        if cluster is None:
            continue
        denominators[cluster]=denominators.get(cluster,0)+1
        dest=by_cluster.setdefault(cluster,{k:0 for k in gene_keys})
        for key in gene_keys:
            v=num(row[key]) or 0
            totals[key]+=int(v>0)
            dest[key]+=int(v>0)
    n=sum(denominators.values())
    top=sorted(gene_keys,key=lambda k:totals[k]*(n-totals[k]),reverse=True)[:8]
    heatmap=[{'cluster':c,'n':denominators[c],
              'values':[round(100*by_cluster[c][key]/denominators[c],1) for key in top]}
             for c in sorted(denominators)]
    return {'scope':'Original exploratory cohort; separate from the 445-sample supervised cohort',
            'total':len(points),'points':points,'review_count':sum(p['review'] for p in points),
            'clusters':[{'name':'Cluster '+k,'id':k,'count':v} for k,v in sorted(clusters.items())],
            'countries':[{'name':k,'count':v} for k,v in sorted(countries.items(),key=lambda p:p[1],reverse=True)[:6]],
            'heatmap':{'genes':[k.removeprefix('gene__') for k in top],'rows':heatmap,'matched_samples':n}}


def explore(root=ROOT):
    paths=[root/'results/sample_analysis.csv',root/'data/processed/klebsiella_amr_features.csv']
    fingerprint=tuple(p.stat().st_mtime_ns if p.exists() else None for p in paths)
    return explore_cached(str(root),fingerprint)


def validate_input(content):
    if not content.strip():
        raise ValueError('Choose a CSV or TSV file with BioSample and AMR genotypes columns.')
    if len(content.encode('utf-8'))>5*1024*1024:
        raise ValueError('Use a file smaller than 5 MB for this preview.')
    first=content.lstrip('\ufeff').splitlines()[0]
    reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')),delimiter='\t' if '\t' in first else ',')
    if not {'BioSample','AMR genotypes'}.issubset(reader.fieldnames or []):
        raise ValueError('Required columns are BioSample and AMR genotypes. Download the template for an example.')
    if len(reader.fieldnames)!=len(set(reader.fieldnames)):
        raise ValueError('Column names must be unique.')
    seen=set()
    rows=[]
    for index,row in enumerate(reader,2):
        if None in row:
            raise ValueError(f'Row {index}: extra columns found. In CSV files, quote AMR entries that contain commas, or use TSV.')
        sample=(row.get('BioSample') or '').strip()
        if not sample or sample in seen:
            raise ValueError(f'Row {index}: BioSample must be present and unique.')
        seen.add(sample)
        text=(row.get('AMR genotypes') or '').strip()
        features=0
        ignored=0
        for token in text.split(',') if text else []:
            if '=' not in token:
                raise ValueError(f'Row {index}: use gene=COMPLETE or mutation=POINT entries.')
            name,status=token.rsplit('=',1)
            if not name.strip() or not status.strip():
                raise ValueError(f'Row {index}: an AMR entry is incomplete.')
            if status.strip() in ('COMPLETE','POINT'):
                features+=1
            else:
                ignored+=1
        rows.append({'sample':sample,'features':features,'other_entries':ignored})
        if len(rows)>1000:
            raise ValueError('Limit preview files to 1,000 samples.')
    if not rows:
        raise ValueError('The file has headers but no samples.')
    return {'samples':len(rows),'preview':rows[:8],'prediction_run':False,
            'message':'Input structure checked. Inference is not connected to this preview; no predictions were generated.'}
