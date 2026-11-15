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
        return True
    except (ProcessLookupError, PermissionError):
        return False


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


def multispecies_summary(root=ROOT):
    """Expose saved multispecies development summaries without loading large matrices."""
    base = root / 'data/processed/multispecies'
    output = []
    for species, label in [('escherichia_coli', 'E. coli'), ('acinetobacter_baumannii', 'A. baumannii')]:
        unsup = read_json(base / species / 'unsupervised_profiles/report.json', {}) or {}
        model = read_json(base / species / 'encoded/supervised_models/report.json', {}) or {}
        anomaly = read_json(base / species / 'unsupervised_profiles/anomaly_resampling/report.json', {}) or {}
        output.append({'species': label, 'encoded_samples': unsup.get('encoded_samples'),
            'genomic_features': unsup.get('features'), 'unique_profiles': unsup.get('unique_profiles'),
            'eligible_tasks_trained': model.get('eligible_tasks_trained', 0),
            'supervised_summary': model.get('summary', []),
            'anomaly_validation_samples': anomaly.get('validation_samples'),
            'anomaly_rank_correlation': anomaly.get('pairwise_spearman_range'),
            'status': 'development baseline; independent validation pending'})
    return {'species': output, 'tb_status': 'preprocessed cohort; genomic feature matrix pending',
            'scope': 'Saved development analyses only; no external validation claim.'}


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
