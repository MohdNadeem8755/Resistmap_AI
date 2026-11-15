"""Resumable processing of the 130 remaining development read sets.

One assembly at a time; two concurrent mate downloads. No training or label edits.
Species/own-assembly mapping are preliminary QC, not contamination clearance.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import traceback
from urllib.parse import urlparse

import process_ceftazidime_assemblies as assembly

pilot = assembly.pilot
ROOT = assembly.ROOT
SCALE = assembly.OUT
OUT = SCALE / 'reads'
atomic = assembly.atomic_json


def inventory():
    rows = assembly.queue()
    reads = [r for r in rows if r['source'] == 'reads']
    old = {r['BioSample'] for r in pilot.read_csv(assembly.PILOT / 'pilot_manifest.csv')
           if r['source'] == 'reads'}
    if len(reads) != 135 or len(old) != 5 or not old <= {r['BioSample'] for r in reads}:
        raise ValueError('Read/pilot inventory mismatch')
    pending = [r for r in reads if r['BioSample'] not in old]
    items = {}
    for row in pending:
        sample, run = row['BioSample'], row['Run']
        if not re.fullmatch(r'SAM[NED][0-9]+', sample) or not re.fullmatch(r'[SED]RR[0-9]+', run):
            raise ValueError('Unexpected accession')
        records = json.loads((SCALE / 'ena_metadata' / (run + '.json')).read_text())
        if len(records) != 1:
            raise ValueError('Ambiguous ENA metadata')
        record = records[0]
        if (record['run_accession'] != run or sample not in
                (record['sample_accession'], record['secondary_sample_accession']) or
                record['library_strategy'] != 'WGS' or record['library_layout'] != 'PAIRED'):
            raise ValueError('Source identity/layout mismatch: ' + sample)
        parts = [record[k].split(';') for k in ('fastq_ftp', 'fastq_md5', 'fastq_bytes')]
        if len({len(p) for p in parts}) != 1:
            raise ValueError('Invalid source manifest')
        pairs = {}
        for url, md5, size in zip(*parts):
            match = re.search(r'_([12])\.fastq\.gz$', url)
            if not match:
                continue
            url = url if '://' in url else 'https://' + url
            parsed = urlparse(url)
            mate = int(match[1])
            if (parsed.scheme != 'https' or parsed.hostname != 'ftp.sra.ebi.ac.uk' or
                    not re.fullmatch(r'[a-f0-9]{32}', md5) or int(size) <= 0 or mate in pairs):
                raise ValueError('Invalid paired source')
            pairs[mate] = {'BioSample': sample, 'Run': run, 'url': url, 'md5': md5,
                           'bytes': int(size), 'relative_path': f'downloads/{sample}_{mate}.fastq.gz'}
        if set(pairs) != {1, 2} or sum(p['bytes'] for p in pairs.values()) != int(row['FASTQ_bytes']):
            raise ValueError('Paired read size mismatch')
        items[sample] = [pairs[1], pairs[2]]
    return pending, items


def environment():
    amr, qc, version = assembly.environment()
    config = json.loads((assembly.PILOT / 'linux_environment.json').read_text())
    prefix = pilot.WSL + ['env', 'MAMBA_ROOT_PREFIX=' + config['base'], config['micromamba']]
    packages = subprocess.check_output(prefix + ['list', '-p', config['env'], '--explicit'], text=True)
    expected = (assembly.PILOT / 'environment_explicit.txt').read_text()
    for name in ('fastp-', 'skesa-'):
        old = [x for x in expected.splitlines() if '/' + name in x]
        new = [x for x in packages.splitlines() if '/' + name in x]
        if len(old) != 1 or old != new:
            raise ValueError('Pilot processing package changed: ' + name)
    refs = json.loads((assembly.PILOT / 'biological_qc/tool_and_reference_versions.json').read_text())
    for tool, args in [('kleborate', ['--version']), ('minimap2', ['--version']), ('samtools', ['--version'])]:
        current = subprocess.check_output(qc + [tool] + args, text=True).strip()
        if current != refs['versions'][tool].strip():
            raise ValueError('QC tool version changed: ' + tool)
    for ref in refs['kleborate_mash_references']:
        digest = subprocess.check_output(qc + ['python', '-c',
            'import hashlib,sys; print(hashlib.file_digest(open(sys.argv[1],"rb"),"sha256").hexdigest())',
            ref['path']], text=True).strip()
        if digest != ref['sha256']:
            raise ValueError('Species reference changed')
    provenance = {'amrfinder': version, 'qc': refs, 'pilot_packages': packages,
                  'runner_sha256': pilot.digest(Path(__file__), 'sha256'),
                  'mapping_code_sha256': pilot.digest(ROOT / 'ceftazidime_pilot_biological_qc.py', 'sha256'),
                  'feature_code_sha256': pilot.digest(ROOT / 'process_ceftazidime_assemblies.py', 'sha256')}
    atomic(OUT / 'environment.json', provenance)
    return amr, qc, provenance


def checkpoint(sample, name, recipe, outputs, action):
    path = OUT / 'checkpoints' / f'{sample}.{name}.json'
    if path.exists():
        saved = json.loads(path.read_text())
        if saved['recipe'] != recipe or any(not p.exists() or
                pilot.digest(p, 'sha256') != saved['outputs'].get(str(p.relative_to(OUT))) for p in outputs):
            raise ValueError(f'Checkpoint changed: {sample}/{name}; review before replacing')
        return
    action()
    hashes = {str(p.relative_to(OUT)): pilot.digest(p, 'sha256') for p in outputs}
    atomic(path, {'recipe': recipe, 'outputs': hashes})


def run(command, args, sample, name):
    atomic(OUT / 'logs' / f'{sample}.{name}.command.json', command + args)
    with (OUT / 'logs' / f'{sample}.{name}.log').open('w') as log:
        subprocess.run(command + args, stdout=log, stderr=subprocess.STDOUT, check=True)


def quality_levels(paths):
    result = {}
    for mate, path in enumerate(paths, 1):
        levels, count = set(), 0
        with gzip.open(path, 'rt') as stream:
            for _ in range(1000):
                header = stream.readline()
                if not header:
                    break
                seq, plus, qual = stream.readline().strip(), stream.readline(), stream.readline().strip()
                if not header.startswith('@') or not plus.startswith('+') or not seq or len(seq) != len(qual):
                    raise ValueError('Invalid FASTQ: ' + str(path))
                levels.update(ord(c) - 33 for c in qual)
                count += 1
        if not count:
            raise ValueError('Empty read source')
        result[str(mate)] = {'sampled_reads': count, 'phred_values': sorted(levels)}
    return result


def process_one(row, sources, amr, qc, provenance, update):
    sample = row['BioSample']
    recipe = {'schema': 1, 'sources': sources, 'environment': provenance}
    done = OUT / 'completed' / (sample + '.json')
    if done.exists():
        saved = json.loads(done.read_text())
        if saved['recipe'] != recipe or any(not (OUT / p).exists() or pilot.digest(OUT / p, 'sha256') != h
                                           for p, h in saved['output_sha256'].items()):
            raise ValueError('Completed sample provenance failed: ' + sample)
        return saved['summary']
    if shutil.disk_usage(ROOT).free < 40 * 1024**3:
        raise RuntimeError('Less than 40 GiB free; stop before downloading/processing')
    update('download', sample)
    pilot.OUT = OUT
    with ThreadPoolExecutor(max_workers=2) as pool:
        raw = list(pool.map(pilot.download_file, sources))
    qualities = quality_levels(raw)
    clean = [OUT / 'qc' / f'{sample}_{m}.fastq.gz' for m in (1, 2)]
    fastp_json, fastp_html = [OUT / 'qc' / (sample + ext) for ext in ('.json', '.html')]
    update('clean', sample)
    checkpoint(sample, 'clean', recipe, [*clean, fastp_json, fastp_html], lambda: run(amr,
        ['fastp', '-i', pilot.linux_path(raw[0]), '-I', pilot.linux_path(raw[1]),
         '-o', pilot.linux_path(clean[0]), '-O', pilot.linux_path(clean[1]), '--thread', '4',
         '--detect_adapter_for_pe', '--json', pilot.linux_path(fastp_json),
         '--html', pilot.linux_path(fastp_html)], sample, 'fastp'))
    fasta = OUT / 'assemblies' / (sample + '.fna')
    def assemble():
        partial = fasta.with_suffix('.partial.fna')
        run(amr, ['skesa', '--reads', ','.join(map(pilot.linux_path, clean)), '--cores', '4',
                  '--memory', '4', '--contigs_out', pilot.linux_path(partial)], sample, 'skesa')
        pilot.fasta_stats(partial)
        partial.replace(fasta)
    update('assemble', sample)
    checkpoint(sample, 'assembly', recipe, [fasta], assemble)
    stats = pilot.fasta_stats(fasta)
    report = OUT / 'amrfinder' / (sample + '.tsv')
    mutations = OUT / 'amrfinder' / (sample + '.all_mutations.tsv')
    def annotate():
        run(amr, ['amrfinder', '-n', pilot.linux_path(fasta), '-O', 'Klebsiella_pneumoniae',
                  '--threads', '4', '--plus', '--mutation_all', pilot.linux_path(mutations),
                  '-o', pilot.linux_path(report)], sample, 'amrfinder')
        assembly.report_features(report, mutations)
    update('annotate', sample)
    checkpoint(sample, 'annotation', recipe, [report, mutations], annotate)
    qc_dir = OUT / 'biological_qc' / sample
    qc_dir.mkdir(parents=True, exist_ok=True)
    species_file = qc_dir / 'kleborate/general__species_output.txt'
    update('species', sample)
    checkpoint(sample, 'species', recipe, [species_file], lambda: run(qc,
        ['kleborate', '-a', pilot.linux_path(fasta), '-o', pilot.linux_path(qc_dir / 'kleborate'),
         '-m', 'general__species,general__contig_stats', '--trim_headers'], sample, 'species'))
    with species_file.open() as stream:
        species = list(csv.DictReader(stream, delimiter='\t'))
    if len(species) != 1 or species[0]['strain'] != sample:
        raise ValueError('Species identity mismatch')
    mapping_file = qc_dir / (sample + '.mapping.json')
    # Reuse the exact pilot mapping implementation with sample-scoped paths.
    mapping_adapter = (
        'import sys; from pathlib import Path; import ceftazidime_pilot_biological_qc as q; '
        'q.PILOT=Path(sys.argv[1]); q.OUT=Path(sys.argv[2]); '
        'q.manifest=lambda:[dict(BioSample=sys.argv[3], Run=sys.argv[4], source="reads")]; q.mapping()')
    update('mapping', sample)
    checkpoint(sample, 'mapping', recipe, [mapping_file, qc_dir / (sample + '.contig_depth.csv')],
        lambda: run(qc, ['python', '-c', mapping_adapter, pilot.linux_path(OUT),
                       pilot.linux_path(qc_dir), sample, row['Run']], sample, 'mapping'))
    main, expanded, hits, sites, unknown = assembly.report_features(report, mutations)
    feature_file = OUT / 'feature_rows' / (sample + '.json')
    atomic(feature_file, {'main': main, 'with_called_sites': expanded})
    mapping = json.loads(mapping_file.read_text())
    fastp = json.loads(fastp_json.read_text())['summary']
    before, after = fastp['before_filtering'], fastp['after_filtering']
    summary = {**row, **stats, 'AMR_report_rows': hits, 'all_mutation_rows': sites,
               'unknown_variant_rows_not_encoded': unknown, 'species': species[0]['species'],
               'species_match': species[0]['species_match'], 'QC_warnings': species[0]['QC_warnings'],
               'reads_retained_pct': 100*after['total_reads']/before['total_reads'],
               'post_QC_Q30_pct': 100*after['q30_rate'], 'sampled_quality_levels': qualities,
               'uniform_sampled_quality': any(len(v['phred_values']) == 1 for v in qualities.values()),
               'primary_mapped_pct': mapping['primary_mapped_pct'],
               'assembly_bases_ge10x_pct': mapping['assembly_bases_ge10x_pct'],
               'mean_depth_MQ20_overlap_removed': mapping['mean_depth_MQ20_overlap_removed'],
               'contamination_screen': 'pending', 'samples_removed': 0}
    outputs = [*raw, *clean, fastp_json, fastp_html, fasta, report, mutations, species_file,
               mapping_file, qc_dir / (sample + '.contig_depth.csv'), feature_file]
    atomic(done, {'recipe': recipe, 'summary': summary, 'output_sha256':
                 {str(p.relative_to(OUT)): pilot.digest(p, 'sha256') for p in outputs}})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    rows, items = inventory()
    if args.preflight:
        print(json.dumps({'remaining_samples': len(rows), 'download_files': sum(map(len, items.values())),
                          'compressed_bytes': sum(p['bytes'] for pair in items.values() for p in pair),
                          'disk_free_bytes': shutil.disk_usage(ROOT).free}, indent=2))
        return
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError('Limit must be positive')
        rows = rows[:args.limit]
    for name in ('downloads', 'qc', 'assemblies', 'amrfinder', 'logs', 'checkpoints', 'completed', 'feature_rows'):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    lock = OUT / 'read_stage.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps({'pid': os.getpid(), 'started_unix': time.time()}).encode())
    os.close(fd)
    results, failures = [], []
    def update(stage, sample=None, status='running', error=None):
        atomic(OUT / 'read_job_status.json', {'status': status, 'stage': stage, 'pid': os.getpid(),
            'current_sample': sample, 'requested': len(rows), 'completed': len(results), 'failures': failures,
            'updated_unix': time.time(), 'error': error, 'contamination_screen': 'pending',
            'model_trained': False, 'accuracy_measured': False})
        print(status, stage, sample or '', f'{len(results)}/{len(rows)}', flush=True)
    try:
        update('environment')
        amr, qc, provenance = environment()
        atomic(OUT / 'download_manifest.json', [p for row in rows for p in items[row['BioSample']]])
        for row in rows:
            try:
                results.append(process_one(row, items[row['BioSample']], amr, qc, provenance, update))
            except Exception as exc:
                failures.append({'BioSample': row['BioSample'], 'error': str(exc)})
                traceback.print_exc()
                # Stop on first failure: do not silently skip a project or class.
                raise
            assembly.write_csv(OUT / 'read_qc_summary.csv', results)
            update('sample_complete', row['BioSample'])
        update('preliminary_read_processing_complete', status='completed')
    except BaseException as exc:
        update('interrupted_or_failed', status='failed', error=str(exc))
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
