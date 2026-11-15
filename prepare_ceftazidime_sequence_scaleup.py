"""Prepare a development-only 445-sample queue and FASTQ storage inventory.

Fetches ENA metadata only. Does not download sequences, assemble or train.
"""
import csv
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
import time

ROOT = Path(r'D:\ResistMap-AI')
READY = ROOT / 'results/ceftazidime_sequence_readiness'
OUT = ROOT / 'results/ceftazidime_sequence_scaleup'


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def ena(row):
    run = row['Run']
    path = OUT / 'ena_metadata' / (run + '.json')
    fields = 'run_accession,sample_accession,secondary_sample_accession,library_strategy,library_layout,fastq_ftp,fastq_md5,fastq_bytes'
    url = 'https://www.ebi.ac.uk/ena/portal/api/filereport?' + urllib.parse.urlencode({
        'accession': run, 'result': 'read_run', 'format': 'json', 'fields': fields})
    if path.exists():
        data = json.loads(path.read_text())
    else:
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=40) as response:
                    data = json.load(response)
                path.write_text(json.dumps(data, indent=2))
                path.with_suffix('.source.json').write_text(json.dumps({'url': url, 'retrieved_unix': time.time()}))
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
    assert len(data) == 1 and data[0]['run_accession'] == run
    item = data[0]
    assert row['BioSample'] in (item['sample_accession'], item['secondary_sample_accession'])
    assert item['library_strategy'] == 'WGS' and item['library_layout'] == 'PAIRED'
    urls, md5s, sizes = [item.get(k, '').split(';') for k in ('fastq_ftp','fastq_md5','fastq_bytes')]
    assert len(urls) == len(md5s) == len(sizes)
    pairs = [(u, m, int(s)) for u, m, s in zip(urls, md5s, sizes)
             if u.endswith(('_1.fastq.gz', '_2.fastq.gz'))]
    assert len(pairs) == 2 and len({u.rsplit('_', 1)[1] for u, _, _ in pairs}) == 2
    row['FASTQ_bytes'] = sum(s for _, _, s in pairs)
    row['metadata_status'] = 'verified_paired_WGS'
    row['metadata_file'] = str(path)
    return row


def main():
    (OUT / 'ena_metadata').mkdir(parents=True, exist_ok=True)
    inventory = rows(READY / 'development_assembly_manifest.csv')
    allowed = {r['BioSample']: r['Isolate'] for r in rows(ROOT / 'results/ceftazidime_clsi_split_v2.csv')
               if r['partition'] == 'train'}
    assert len(inventory) == len(allowed) == 445
    assert {r['BioSample'] for r in inventory} == set(allowed)
    sources = {r['BioSample']: r for r in rows(READY / 'ncbi_source_lookup/missing_assembly_source_manifest.csv')}
    pilot = {r['BioSample'] for r in rows(ROOT / 'results/ceftazidime_sequence_pilot/pilot_manifest.csv')}
    queue = []
    for row in inventory:
        assert row['partition'] == 'development' and allowed[row['BioSample']] == row['Isolate']
        assembly = row['Assembly']
        run = '' if assembly else sources[row['BioSample']]['candidate_paired_Illumina_WGS_runs']
        assert assembly.startswith('GCA_') if assembly else run.startswith('SRR') and ';' not in run
        queue.append({k: row[k] for k in ['BioSample','Isolate','BioProject','Assembly']} | {
            'Run': run, 'source': 'assembly' if assembly else 'reads', 'partition': 'development',
            'pilot_processed': row['BioSample'] in pilot, 'FASTQ_bytes': '',
            'metadata_status': 'assembly_metadata_pending' if assembly else 'pending', 'metadata_file': ''})
    pending = [r for r in queue if r['source'] == 'reads']
    with ThreadPoolExecutor(max_workers=2) as pool:
        for n, result in enumerate(pool.map(ena, pending), 1):
            print(f'ENA metadata verified {n}/{len(pending)}: {result["Run"]}', flush=True)
    output = OUT / 'development_processing_queue.csv'
    temp = output.with_suffix('.tmp')
    with temp.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(queue[0]))
        writer.writeheader()
        writer.writerows(queue)
    temp.replace(output)
    summary = {'development_samples': len(queue), 'existing_assembly_sources': 310,
               'raw_read_sources': len(pending), 'pilot_processed': len(pilot),
               'compressed_paired_FASTQ_bytes_all_135': sum(r['FASTQ_bytes'] for r in pending),
               'compressed_paired_FASTQ_bytes_remaining_130': sum(r['FASTQ_bytes'] for r in pending if not r['pilot_processed']),
               'sequence_downloads_started_by_this_script': False, 'model_training_started': False,
               'note': 'FASTQ size excludes cleaned reads, assemblies, BAM files, databases and temporary space. Assembly URLs/checksums still require verification.'}
    (OUT / 'queue_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
