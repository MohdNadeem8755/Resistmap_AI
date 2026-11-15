"""Acquire public genome archive and inventory exact sequence duplicates only."""
import hashlib
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/external/multispecies_candidate_screen'


def main():
    target = OUT / 'liverpool_genomes.zip'
    if not target.exists():
        page = 'https://datacat.liverpool.ac.uk/3008/'
        response = requests.get(page, timeout=40)
        response.raise_for_status()
        links = {urljoin(page, x) for x in re.findall(r'href=["\']([^"\']+)["\']', response.text) if x.endswith('/genomes.zip')}
        assert len(links) == 1
        url = links.pop()
        partial = target.with_suffix('.zip.part')
        started = time.monotonic()
        with requests.get(url, stream=True, timeout=(30, 90)) as response:
            response.raise_for_status()
            expected = int(response.headers.get('Content-Length', 0))
            received, last = 0, 0
            sha = hashlib.sha256()
            with partial.open('wb') as handle:
                for chunk in response.iter_content(1024*1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    sha.update(chunk)
                    received += len(chunk)
                    if time.monotonic() - last > 20:
                        elapsed = time.monotonic() - started
                        print(f'Downloaded {received/1e6:.1f}/{expected/1e6:.1f} MB; {received/1e6/elapsed:.2f} MB/s', flush=True)
                        last = time.monotonic()
            assert not expected or received == expected, 'Incomplete download'
        assert zipfile.is_zipfile(partial), 'Response is not a ZIP archive'
        partial.replace(target)
        target.with_suffix('.provenance.json').write_text(json.dumps({'url': url,
            'retrieved_utc': datetime.now(timezone.utc).isoformat(), 'bytes': received,
            'sha256': sha.hexdigest(), 'download_seconds': time.monotonic()-started}, indent=2))
    rows = []
    accessions = set()
    with zipfile.ZipFile(target) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or entry.filename.startswith('__MACOSX/') or Path(entry.filename).name.startswith('._') or not entry.filename.lower().endswith(('.fna', '.fa', '.fasta')):
                continue
            # Reading each entry also validates its ZIP CRC. No archive paths are extracted.
            text = archive.read(entry).decode('ascii')
            sequences, current = [], []
            for line in text.splitlines():
                if line.startswith('>'):
                    accessions.update(re.findall(r'\b(?:SAM[NED][A-Z]*\d+|GC[AF]_\d+\.\d+|PRJ(?:NA|EB|DB)\d+)\b', line))
                    if current:
                        sequences.append(''.join(current).upper())
                    current = []
                else:
                    current.append(line.strip())
            if current:
                sequences.append(''.join(current).upper())
            assert sequences and all(sequences)
            complement = str.maketrans('ACGTRYMKBDHVN', 'TGCAYRKMVHDBN')
            contig_hashes = sorted(hashlib.sha256(min(s, s.translate(complement)[::-1]).encode()).hexdigest() for s in sequences)
            rows.append({'local_id': Path(entry.filename).stem, 'archive_entry': entry.filename,
                'contigs': len(sequences), 'total_bases': sum(map(len, sequences)),
                'exact_contig_set_sha256': hashlib.sha256('\n'.join(contig_hashes).encode()).hexdigest()})
    df = pd.DataFrame(rows)
    assert df.local_id.is_unique
    df.to_parquet(OUT / 'liverpool_genome_inventory.parquet', index=False)
    seen = pd.read_parquet(ROOT / 'reports/multispecies_validation_readiness/escherichia_coli_previously_seen_keys.parquet')
    assemblies = set(seen.Assembly) - {''}
    local = list((ROOT / 'data').rglob('*.fna')) + list((ROOT / 'data').rglob('*.fasta'))
    matched = [str(p) for p in local if any(a in assemblies for a in re.findall(r'GC[AF]_\d+\.\d+', str(p)))]
    report = {'genome_files': len(df), 'unique_exact_contig_sets': int(df.exact_contig_set_sha256.nunique()),
        'records_in_exact_duplicate_groups': int(df.exact_contig_set_sha256.duplicated(keep=False).sum()),
        'header_accessions': sorted(accessions), 'local_fasta_files_scanned': len(local),
        'local_files_with_known_ecoli_assembly_id': matched, 'independence_confirmed': False,
        'limitations': ['Exact contig fingerprints handle order and reverse complements, not alternate assemblies or related lineages.',
            'External versus development sequence comparison requires development genomes or a verified reference sketch index.',
            'Local reference inventory matches filename accession IDs only; unlabelled files remain unresolved.']}
    (OUT / 'liverpool_genome_readiness.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
