"""Verified, resumable assembly processing for the frozen development cohort.

Run with the Windows Python used for the pilot. Stages: resolve, process,
species, audit, all. No model training or sequence-based sample exclusion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

import ceftazidime_sequence_pilot as pilot

ROOT = pilot.ROOT
PILOT = ROOT / 'results/ceftazidime_sequence_pilot'
OUT = ROOT / 'results/ceftazidime_sequence_scaleup'
pilot.OUT = OUT
QC_ENV = '/home/Mohd_Sami/.local/share/resistmap-sequence-qc/env'


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)


def csv_rows(path):
    return pilot.read_csv(path)


def write_csv(path, rows):
    temp = path.with_suffix('.tmp')
    pilot.save_csv(temp, rows)
    temp.replace(path)


def queue():
    rows = csv_rows(OUT / 'development_processing_queue.csv')
    expected = {r['BioSample']: r for r in csv_rows(ROOT / 'results/ceftazidime_clsi_split_v2.csv')
                if r['partition'] == 'train'}
    if len(rows) != 445 or len(expected) != 445 or {r['BioSample'] for r in rows} != set(expected):
        raise ValueError('Development manifest changed or is incomplete')
    for row in rows:
        old = expected[row['BioSample']]
        if row['partition'] != 'development' or row['Isolate'] != old['Isolate'] or row['BioProject'] != old['BioProject']:
            raise ValueError('Saved split identity mismatch')
    assemblies = [r for r in rows if r['source'] == 'assembly']
    if len(assemblies) != 310 or len({r['Assembly'] for r in assemblies}) != 310:
        raise ValueError('Unexpected assembly inventory')
    return rows


def resolve():
    rows = [r for r in queue() if r['source'] == 'assembly']
    manifest_file = OUT / 'assembly_download_manifest.json'
    # Batch accession lookup; each returned record must match exact version and BioSample.
    records = {}
    for start in range(0, len(rows), 30):
        batch = rows[start:start+30]
        search = pilot.eutils('esearch.fcgi', db='assembly', retmode='json', retmax=200,
                              term=' OR '.join(r['Assembly'] + '[Assembly Accession]' for r in batch))['esearchresult']
        ids = search['idlist']
        if int(search['count']) > len(ids) or not ids:
            raise ValueError('Assembly search truncated or empty')
        result = pilot.eutils('esummary.fcgi', db='assembly', id=','.join(ids), retmode='json')['result']
        for uid in result['uids']:
            record = result[uid]
            for accession in [record.get('assemblyaccession'), record.get('synonym', {}).get('genbank')]:
                if accession:
                    records[accession] = record
        print(f'NCBI assembly metadata fetched {min(start+30,len(rows))}/{len(rows)}', flush=True)
    downloads = []
    for n, row in enumerate(rows, 1):
        sample, accession = row['BioSample'], row['Assembly']
        record = records.get(accession)
        if not record or record.get('biosampleaccn') != sample:
            raise ValueError('Exact assembly/BioSample identity failed: ' + sample)
        base = record['ftppath_genbank'].replace('ftp://', 'https://').rstrip('/')
        if not base.startswith('https://ftp.ncbi.nlm.nih.gov/genomes/'):
            raise ValueError('Unexpected genome host')
        filename = base.rsplit('/', 1)[1] + '_genomic.fna.gz'
        checksums = {line.split()[1].removeprefix('./'): line.split()[0]
                     for line in pilot.fetch(base + '/md5checksums.txt').splitlines() if len(line.split()) == 2}
        md5 = checksums[filename]
        if len(md5) != 32 or any(c not in '0123456789abcdef' for c in md5):
            raise ValueError('Invalid source checksum')
        downloads.append({'BioSample': sample, 'Assembly': accession, 'kind': 'assembly',
                          'url': base + '/' + filename, 'md5': md5, 'bytes': None,
                          'relative_path': 'downloads/' + sample + '.fna.gz'})
        if n % 25 == 0 or n == len(rows):
            print(f'Assembly source/MD5 verified {n}/{len(rows)}', flush=True)
    atomic_json(manifest_file, downloads)


def environment():
    config = json.loads((PILOT / 'linux_environment.json').read_text())
    prefix = pilot.WSL + ['env', 'MAMBA_ROOT_PREFIX=' + config['base'], config['micromamba'], 'run', '-p']
    amr_command = prefix + [config['env']]
    version = subprocess.check_output(amr_command + ['amrfinder', '-V'], stderr=subprocess.STDOUT, text=True)
    def canonical(text):
        return [line.strip() for line in text.splitlines()
                if line.startswith(('Software version:', 'Database version:', 'Database directory:'))]
    if canonical(version) != canonical((PILOT / 'amrfinder_versions.txt').read_text()):
        raise ValueError('AMRFinder software/database differs from completed pilot')
    config['amrfinder_version_fields'] = canonical(version)
    atomic_json(OUT / 'processing_environment.json', config)
    return amr_command, prefix + [QC_ENV], canonical(version)


def report_features(report, mutations):
    def read(path):
        with path.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, delimiter='\t')
            required = {'Element symbol','Element name','Method','% Identity to reference','% Coverage of reference'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('Unexpected AMRFinder columns: ' + str(path))
            return list(reader)
    hits, called = read(report), read(mutations)
    main = {}
    for hit in hits:
        symbol = hit['Element symbol']
        if not symbol or symbol == 'NA':
            continue
        main['present:' + symbol] = 1
        main['method:' + symbol + ':' + hit['Method']] = 1
        for field, prefix in [('% Identity to reference','identity:'),('% Coverage of reference','coverage:')]:
            if hit[field] in ('NA', ''):
                continue
            value = float(hit[field]) / 100
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid numeric genomic feature')
            key = prefix + symbol
            main[key] = max(value, main.get(key, 0))
    expanded = dict(main)
    unknown = 0
    for hit in called:
        if '[UNKNOWN]' in hit['Element name']:
            unknown += 1
            continue
        symbol = hit['Element symbol']
        if symbol and symbol != 'NA':
            # Preserve exact AMRFinder allele/site notation. A missing call is
            # not filled with wild type; ambiguous multi-copy calls remain multiple.
            expanded['called_site_state:' + symbol] = 1
    return main, expanded, len(hits), len(called), unknown


def process(limit=None, workers=2):
    rows = [r for r in queue() if r['source'] == 'assembly']
    items = json.loads((OUT / 'assembly_download_manifest.json').read_text())
    downloads = {i['BioSample']: i for i in items}
    if len(downloads) != 310 or set(downloads) != {r['BioSample'] for r in rows}:
        raise ValueError('Incomplete source verification')
    if shutil.disk_usage(ROOT).free < 15 * 1024**3:
        raise RuntimeError('Insufficient free space for assembly stage')
    command, _, version = environment()
    for name in ['downloads','assemblies','amrfinder','logs','completed','feature_rows']:
        (OUT / name).mkdir(exist_ok=True)
    pilot_summary = {r['BioSample']: r for r in csv_rows(PILOT / 'pilot_processing_summary.csv')}
    if limit is not None:
        rows = rows[:limit]
    def one(row):
        sample = row['BioSample']
        item = downloads[sample]
        done_path = OUT / 'completed' / (sample + '.json')
        fasta = OUT / 'assemblies' / (sample + '.fna')
        report = OUT / 'amrfinder' / (sample + '.tsv')
        mutations = OUT / 'amrfinder' / (sample + '.all_mutations.tsv')
        expected = {'source_url': item['url'], 'source_md5': item['md5'], 'version': version, 'schema': 1}
        if done_path.exists():
            saved = json.loads(done_path.read_text())
            if saved['provenance'] != expected or any(pilot.digest(OUT / name, 'sha256') != value
                                                      for name, value in saved['output_sha256'].items()):
                raise ValueError('Cached result provenance failed: ' + sample)
            return saved['summary']
        pilot_download = PILOT / item['relative_path']
        if sample in pilot_summary and pilot_download.exists() and pilot.digest(pilot_download) == item['md5']:
            packed = pilot_download
        else:
            packed = pilot.download_file(item)
        tmp_fasta = fasta.with_suffix('.partial.fna')
        with gzip.open(packed, 'rb') as source, tmp_fasta.open('wb') as target:
            shutil.copyfileobj(source, target)
        stats = pilot.fasta_stats(tmp_fasta)
        fasta_hash = pilot.digest(tmp_fasta, 'sha256')
        tmp_fasta.replace(fasta)
        old = pilot_summary.get(sample)
        reused = bool(old and old['assembly_sha256'] == fasta_hash)
        if reused:
            for path in (report, mutations):
                shutil.copyfile(PILOT / 'amrfinder' / path.name, path)
        else:
            temp_report = report.with_suffix('.partial.tsv')
            temp_mutations = mutations.with_suffix('.partial.tsv')
            args = ['amrfinder','-n',pilot.linux_path(fasta),'-O','Klebsiella_pneumoniae',
                    '--threads','4','--plus','--mutation_all',pilot.linux_path(temp_mutations),
                    '-o',pilot.linux_path(temp_report)]
            atomic_json(OUT / 'logs' / (sample + '.command.json'), command + args)
            with (OUT / 'logs' / (sample + '.log')).open('w') as log:
                subprocess.run(command + args, stdout=log, stderr=subprocess.STDOUT, check=True)
            report_features(temp_report, temp_mutations)
            temp_report.replace(report)
            temp_mutations.replace(mutations)
        main, expanded, hits, sites, unknown = report_features(report, mutations)
        feature_path = OUT / 'feature_rows' / (sample + '.json')
        atomic_json(feature_path, {'main': main, 'with_called_sites': expanded})
        summary = {k: row[k] for k in ['BioSample','Isolate','BioProject','Assembly','source']}
        summary.update(stats | {'AMR_report_rows': hits,'all_mutation_rows': sites,
                               'unknown_variant_rows_not_encoded': unknown,'main_feature_count': len(main),
                               'expanded_feature_count': len(expanded),'reused_pilot_report': reused})
        hashes = {str(path.relative_to(OUT)): pilot.digest(path, 'sha256')
                  for path in (fasta, report, mutations, feature_path)}
        atomic_json(done_path, {'provenance': expected,'summary': summary,'output_sha256': hashes})
        return summary
    failures, finished = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, row): row['BioSample'] for row in rows}
        for future in as_completed(futures):
            sample = futures[future]
            try:
                finished.append(future.result())
                print(f'Completed assembly {len(finished)}/{len(rows)}: {sample}', flush=True)
            except Exception as exc:
                failures.append({'BioSample': sample, 'error': str(exc)})
                print('REVIEW:', sample, repr(exc), flush=True)
            atomic_json(OUT / 'assembly_progress.json', {'requested': len(rows),'completed': len(finished),
                        'failures': failures,'running': True,'updated_unix': time.time()})
    atomic_json(OUT / 'assembly_progress.json', {'requested': len(rows),'completed': len(finished),
                'failures': failures,'running': False,'updated_unix': time.time()})
    if finished:
        write_csv(OUT / 'assembly_processing_summary.csv', sorted(finished, key=lambda r:r['BioSample']))
    if failures:
        raise RuntimeError(f'{len(failures)} samples require review; see assembly_progress.json')


def species():
    rows = [r for r in queue() if r['source'] == 'assembly']
    paths = [OUT / 'assemblies' / (r['BioSample'] + '.fna') for r in rows]
    if not all((OUT / 'completed' / (r['BioSample'] + '.json')).exists() for r in rows):
        raise ValueError('Complete the 310 assembly reports before the species stage')
    _, command, _ = environment()
    expected = json.loads((PILOT / 'biological_qc/tool_and_reference_versions.json').read_text())
    version = subprocess.check_output(command + ['kleborate','--version'], text=True).strip()
    if version != expected['versions']['kleborate']:
        raise ValueError('Kleborate version changed')
    for reference in expected['kleborate_mash_references']:
        reference_hash = subprocess.check_output(command + ['python','-c',
            'import hashlib,sys; print(hashlib.file_digest(open(sys.argv[1], "rb"), "sha256").hexdigest())',
            reference['path']], text=True).strip()
        if reference_hash != reference['sha256']:
            raise ValueError('Kleborate reference changed')
    args = ['kleborate','-a', *[pilot.linux_path(p) for p in paths], '-o', pilot.linux_path(OUT / 'kleborate'),
            '-m','general__species,general__contig_stats','--trim_headers']
    atomic_json(OUT / 'species_command.json', args)
    # Pass the long input list inside Linux to avoid Windows command-length limits.
    launcher = command + ['python','-c',
        'import json,subprocess,sys; subprocess.run(json.load(open(sys.argv[1])), check=True)',
        pilot.linux_path(OUT / 'species_command.json')]
    with (OUT / 'species.log').open('w') as log:
        subprocess.run(launcher, stdout=log, stderr=subprocess.STDOUT, check=True)
    atomic_json(OUT / 'species_inputs_sha256.json', {p.name: pilot.digest(p,'sha256') for p in paths})


def audit():
    rows = queue()
    with (OUT / 'kleborate/general__species_output.txt').open() as f:
        calls = {r['strain']: r for r in csv.DictReader(f, delimiter='\t')}
    expected = {r['BioSample'] for r in rows if r['source'] == 'assembly'}
    if set(calls) != expected:
        raise ValueError('Species output does not cover the assembly cohort')
    main, expanded, summaries = {}, {}, []
    for row in rows:
        sample = row['BioSample']
        if row['source'] == 'assembly':
            done = json.loads((OUT / 'completed' / (sample + '.json')).read_text())
            if any(pilot.digest(OUT / p, 'sha256') != h for p,h in done['output_sha256'].items()):
                raise ValueError('Output checksum mismatch: ' + sample)
            features = json.loads((OUT / 'feature_rows' / (sample + '.json')).read_text())
            main[sample], expanded[sample] = features['main'], features['with_called_sites']
            sp = calls[sample]
            summaries.append(done['summary'] | {'species': sp['species'], 'species_match': sp['species_match'],
                                                'QC_warnings': sp['QC_warnings'],'contamination_screen': 'pending'})
        elif (PILOT / 'amrfinder' / (sample + '.tsv')).exists():
            main[sample], expanded[sample], *_ = report_features(
                PILOT / 'amrfinder' / (sample + '.tsv'), PILOT / 'amrfinder' / (sample + '.all_mutations.tsv'))
    if len(main) != 315 or set(main) != set(expanded):
        raise ValueError('Expected 310 assemblies plus five completed pilot read assemblies')
    atomic_json(OUT / 'genomic_features_main_partial.json', main)
    atomic_json(OUT / 'genomic_features_with_called_sites_partial.json', expanded)
    write_csv(OUT / 'assembly_qc_summary.csv', summaries)
    status = {'status': '310_assembly_stage_complete','development_samples':445,
              'assembly_reports':310,'pilot_read_reports':5,'genomes_with_features':315,
              'remaining_read_samples':130,'species_review_count':sum(r['species']!='Klebsiella pneumoniae' or r['species_match']!='strong' for r in summaries),
              'assembly_warning_count':sum(r['QC_warnings']!='-' for r in summaries),
              'contamination_screen':'pending','samples_removed':0,'model_trained':False,'accuracy_measured':False,
              'feature_note':'Main report features plus known/wild-type called site states; UNKNOWN variants retained only in raw reports.'}
    atomic_json(OUT / 'assembly_stage_status.json', status)
    print(json.dumps(status, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['resolve','process','species','audit','all'])
    parser.add_argument('--limit', type=int)
    parser.add_argument('--workers', type=int, choices=[1,2], default=2)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage in ('resolve','all'):
        resolve()
    if args.stage in ('process','all'):
        process(args.limit, args.workers)
    if args.stage in ('species','all'):
        species()
    if args.stage in ('audit','all'):
        audit()
