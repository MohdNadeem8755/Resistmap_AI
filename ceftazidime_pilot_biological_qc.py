"""Run inside the isolated Linux QC environment; never trains or edits labels.

Species/assembly screen plus read-to-own-assembly mapping are preliminary QC,
not a comprehensive contamination test or independent model validation.
"""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/mnt/d/ResistMap-AI')
PILOT = ROOT / 'results/ceftazidime_sequence_pilot'
OUT = PILOT / 'biological_qc'


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def run(args, name, stdout_path=None):
    args = [str(x) for x in args]
    write_json(OUT / (name + '.command.json'), {'args': args, 'started_unix': time.time()})
    with (OUT / (name + '.log')).open('w') as log:
        if stdout_path:
            with stdout_path.open('w') as stream:
                subprocess.run(args, stdout=stream, stderr=log, check=True)
        else:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)


def manifest():
    with (PILOT / 'pilot_manifest.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    with (ROOT / 'results/ceftazidime_clsi_split_v2.csv').open(newline='') as f:
        allowed = {r['BioSample'] for r in csv.DictReader(f) if r['partition'] == 'train'}
    assert len(rows) == 10 and len({r['BioSample'] for r in rows}) == 10
    assert all(r['BioSample'] in allowed for r in rows)
    return rows


def source_audit():
    sra = OUT / 'source/SRR4017923.sra'
    provenance = json.loads(sra.with_suffix('.source.json').read_text())
    md5 = hashlib.md5(sra.read_bytes()).hexdigest()
    assert md5 == provenance['md5'] and sra.stat().st_size == provenance['bytes']
    # A bounded sample from Normalized SRA, explicitly not SRA Lite.
    run(['fastq-dump', '--split-files', '-X', '1000', '-O', OUT / 'source', sra], 'source_dump')
    results = []
    for mate in (1, 2):
        normalized = OUT / f'source/SRR4017923_{mate}.fastq'
        ena = PILOT / f'downloads/SAMN05170247_{mate}.fastq.gz'
        normal_reads, ena_reads, qualities = [], [], set()
        with normalized.open() as f:
            while header := f.readline():
                seq, plus, quality = f.readline().strip(), f.readline(), f.readline().strip()
                assert header.startswith('@') and plus.startswith('+') and len(seq) == len(quality)
                normal_reads.append(seq)
                qualities.update(ord(c)-33 for c in quality)
        with gzip.open(ena, 'rt') as f:
            for _ in range(len(normal_reads)):
                assert f.readline().startswith('@')
                ena_reads.append(f.readline().strip())
                f.readline()
                f.readline()
        assert len(normal_reads) == 1000
        results.append({'mate': mate, 'sampled_reads': len(normal_reads),
                        'normalized_phred_values': sorted(qualities),
                        'sequences_equal_ENA_first_1000': normal_reads == ena_reads})
    write_json(OUT / 'source_quality_audit.json', {
        'BioSample': 'SAMN05170247', 'Run': 'SRR4017923',
        'source': provenance, 'source_md5_verified': True, 'mates': results,
        'scope': 'First 1000 reads per mate; original laboratory quality provenance remains unknown.'})
    print('Normalized SRA quality audit:', results, flush=True)


def species():
    rows = manifest()
    fastas = [PILOT / 'assemblies' / (r['BioSample'] + '.fna') for r in rows]
    inputs = {p.name: sha256(p) for p in fastas}
    saved = OUT / 'species_inputs.json'
    if saved.exists():
        assert json.loads(saved.read_text()) == inputs, 'Species inputs changed; review cached results'
        print('Species check already complete.', flush=True)
        return
    run(['kleborate', '-a', *fastas, '-o', OUT / 'kleborate', '-m',
         'general__species,general__contig_stats', '--trim_headers'], 'species')
    write_json(saved, inputs)
    print('Species and assembly-stat checks complete.', flush=True)


def mapping():
    summaries = []
    for row in manifest():
        if row['source'] != 'reads':
            continue
        sample = row['BioSample']
        fasta = PILOT / f'assemblies/{sample}.fna'
        mates = [PILOT / f'qc/{sample}_{i}.fastq.gz' for i in (1, 2)]
        inputs = {p.name: sha256(p) for p in [fasta, *mates]}
        result = OUT / (sample + '.mapping.json')
        if result.exists():
            previous = json.loads(result.read_text())
            assert previous['inputs_sha256'] == inputs, 'Mapping inputs changed'
            summaries.append(previous)
            continue
        bam = OUT / (sample + '.sorted.bam')
        bam_inputs = bam.with_suffix('.inputs.json')
        if bam.exists():
            assert json.loads(bam_inputs.read_text()) == inputs, 'BAM provenance mismatch'
        else:
            partial = bam.with_suffix('.partial.bam')
            mapper_args = ['minimap2', '-ax', 'sr', '-t', '4', str(fasta), *map(str, mates)]
            sorter_args = ['samtools', 'sort', '-@', '2', '-m', '256M', '-o', str(partial), '-']
            write_json(OUT / (sample + '.mapping.command.json'), [mapper_args, sorter_args])
            with (OUT / (sample + '.mapping.log')).open('w') as log:
                mapper = subprocess.Popen(mapper_args, stdout=subprocess.PIPE, stderr=log)
                try:
                    sorter = subprocess.run(sorter_args, stdin=mapper.stdout, stderr=log)
                    mapper.stdout.close()
                    mapper_code = mapper.wait()
                    if sorter.returncode or mapper_code:
                        raise RuntimeError(f'Mapping failed: minimap2={mapper_code}, sort={sorter.returncode}')
                finally:
                    if mapper.poll() is None:
                        mapper.terminate()
                        mapper.wait()
            run(['samtools', 'quickcheck', '-v', partial], sample + '.quickcheck')
            partial.replace(bam)
            write_json(bam_inputs, inputs)
        stats_file = OUT / (sample + '.flagstat.json')
        run(['samtools', 'flagstat', '-O', 'json', bam], sample + '.flagstat', stats_file)
        stats = json.loads(stats_file.read_text())
        run(['samtools', 'faidx', fasta], sample + '.faidx')
        lengths = {r.split('\t')[0]: int(r.split('\t')[1])
                   for r in fasta.with_suffix('.fna.fai').read_text().splitlines()}
        # Exclude supplementary as well as unmapped/secondary/QCFAIL/duplicates;
        # mapping quality >=20, base quality >=0, suppress overlapping mates.
        depth_args = ['samtools', 'depth', '-aa', '-s', '-Q', '20', '-q', '0',
                      '-G', 'UNMAP,SECONDARY,QCFAIL,DUP,SUPPLEMENTARY', str(bam)]
        write_json(OUT / (sample + '.depth.command.json'), depth_args)
        contigs = {name: [0, 0, 0, 0] for name in lengths}
        with (OUT / (sample + '.depth.log')).open('w') as log:
            proc = subprocess.Popen(depth_args, stdout=subprocess.PIPE, stderr=log, text=True)
            for line in proc.stdout:
                name, pos, depth = line.rstrip().split('\t')
                d = int(depth)
                value = contigs[name]
                value[0] += 1
                value[1] += d
                value[2] += d >= 1
                value[3] += d >= 10
            assert proc.wait() == 0, 'Depth failed'
        assert all(contigs[k][0] == v for k, v in lengths.items()), 'Incomplete depth output'
        totals = [sum(v[i] for v in contigs.values()) for i in range(4)]
        groups = [stats['QC-passed reads'], stats['QC-failed reads']]
        primary = sum(g['primary'] for g in groups)
        mapped = sum(g['primary mapped'] for g in groups)
        paired = sum(g['paired in sequencing'] for g in groups)
        proper = sum(g['properly paired'] for g in groups)
        summary = {'BioSample': sample, 'Run': row['Run'], 'inputs_sha256': inputs,
                   'primary_reads': primary, 'primary_mapped_pct': 100*mapped/primary,
                   'properly_paired_pct': 100*proper/paired,
                   'assembly_bases': totals[0], 'mean_depth_MQ20_overlap_removed': totals[1]/totals[0],
                   'assembly_bases_ge1x_pct': 100*totals[2]/totals[0],
                   'assembly_bases_ge10x_pct': 100*totals[3]/totals[0],
                   'scope': 'Mapping to own assembly; cannot exclude contamination.'}
        with (OUT / (sample + '.contig_depth.csv')).open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['contig', 'length', 'mean_depth_MQ20', 'bases_ge1x_pct', 'bases_ge10x_pct'])
            for name, (n, depth, one, ten) in contigs.items():
                writer.writerow([name, n, depth/n, 100*one/n, 100*ten/n])
        write_json(result, summary)
        summaries.append(summary)
        print('Mapped:', sample, 'primary mapped %:', round(summary['primary_mapped_pct'], 2),
              'breadth >=10x %:', round(summary['assembly_bases_ge10x_pct'], 2), flush=True)
    with (OUT / 'mapping_summary.csv').open('w', newline='') as f:
        fields = [k for k in summaries[0] if k != 'inputs_sha256']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(summaries)


def summarize():
    expected = manifest()
    with (OUT / 'kleborate/general__species_output.txt').open() as f:
        species_rows = {r['strain']: r for r in csv.DictReader(f, delimiter='\t')}
    with (OUT / 'mapping_summary.csv').open() as f:
        mapping_rows = {r['BioSample']: r for r in csv.DictReader(f)}
    assert set(species_rows) == {r['BioSample'] for r in expected}
    assert set(mapping_rows) == {r['BioSample'] for r in expected if r['source'] == 'reads'}
    source = json.loads((OUT / 'source_quality_audit.json').read_text())
    assert source['source_md5_verified']
    combined = []
    for row in expected:
        sample = row['BioSample']
        sp = species_rows[sample]
        metrics = mapping_rows.get(sample, {})
        combined.append({'BioSample': sample, 'source': row['source'],
                         'species': sp['species'], 'species_match': sp['species_match'],
                         'contigs': sp['contig_count'], 'N50': sp['N50'], 'GC_pct': sp['GC_content'],
                         'Kleborate_QC_warnings': sp['QC_warnings'],
                         'primary_reads_mapped_pct': metrics.get('primary_mapped_pct', ''),
                         'mapped_depth_MQ20': metrics.get('mean_depth_MQ20_overlap_removed', ''),
                         'assembly_breadth_ge10x_pct': metrics.get('assembly_bases_ge10x_pct', ''),
                         'source_quality_note': 'Uniform Q30 in sampled normalized SRA and ENA reads; cause unknown'
                             if sample == source['BioSample'] else '',
                         'comprehensive_contamination_screen': 'not_performed'})
    with (OUT / 'pilot_biological_qc_summary.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)
    status = {'status': 'preliminary_species_assembly_and_mapping_QC_complete',
              'samples': len(combined),
              'strong_K_pneumoniae_matches': sum(r['species']=='Klebsiella pneumoniae' and r['species_match']=='strong' for r in combined),
              'Kleborate_assembly_warnings': sum(r['Kleborate_QC_warnings'] != '-' for r in combined),
              'read_sets_mapped': len(mapping_rows), 'source_quality_flags': [source['BioSample']],
              'samples_removed': 0, 'model_trained': False, 'accuracy_measured': False,
              'remaining': 'Comprehensive contamination assessment; full-cohort processing; development validation; fresh independent evaluation.'}
    write_json(OUT / 'qc_status.json', status)
    print(json.dumps(status, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['source', 'species', 'mapping', 'summarize'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {'source': source_audit, 'species': species, 'mapping': mapping, 'summarize': summarize}[args.stage]()
