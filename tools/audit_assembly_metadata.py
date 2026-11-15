"""Cache public assembly metadata and audit identity/missingness, without QC pass claims."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1] / 'data/processed/multispecies'
ENDPOINT = 'https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/'


def fetch(accessions, cache):
    key = hashlib.sha256(','.join(accessions).encode()).hexdigest()[:20]
    path = cache / (key + '.json')
    if path.exists():
        return json.loads(path.read_text())['reports']
    records, token = [], None
    while True:
        params = {'page_size': 100}
        if token:
            params['page_token'] = token
        url = ENDPOINT + ','.join(accessions) + '/dataset_report'
        for attempt in range(4):
            try:
                response = requests.get(url, params=params, timeout=45)
                response.raise_for_status()
                payload = response.json()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        records.extend(payload.get('reports', []))
        token = payload.get('next_page_token')
        time.sleep(.4)
        if not token:
            break
    path.write_text(json.dumps({'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                               'url': url, 'requested': accessions, 'reports': records}))
    return records


def run(species):
    base = ROOT / species / 'unsupervised_profiles'
    out = base / 'assembly_metadata_audit'
    cache = out / 'source_cache'
    cache.mkdir(parents=True, exist_ok=True)
    selected = pd.read_parquet(base / 'annotation_qc_review/sample_qc_context.parquet')[['BioSample', 'matrix_row']]
    samples = pd.read_parquet(base / 'samples.parquet')[['BioSample', 'Assembly']]
    frame = selected.merge(samples, on='BioSample', how='left', validate='one_to_one')
    accessions = sorted(set(frame.Assembly.dropna()) - {''})
    assert all(pd.Series(accessions).str.fullmatch(r'GC[AF]_\d+\.\d+'))
    records = []
    for start in range(0, len(accessions), 50):
        records.extend(fetch(accessions[start:start+50], cache))
        print(species, min(start+50, len(accessions)), '/', len(accessions), flush=True)
    flat = []
    for record in records:
        info = record.get('assembly_info', {})
        stats = record.get('assembly_stats', {})
        checkm = record.get('checkm_info', {})
        flat.append(dict(Assembly=record['accession'], metadata_found=True,
            ncbi_biosample=info.get('biosample', {}).get('accession'),
            organism=record.get('organism', {}).get('organism_name'),
            assembly_status=info.get('assembly_status'), assembly_level=info.get('assembly_level'),
            contigs=stats.get('number_of_contigs'), contig_n50=stats.get('contig_n50'),
            length=stats.get('total_sequence_length'), reported_coverage=stats.get('genome_coverage'),
            checkm_completeness=checkm.get('completeness'), checkm_contamination=checkm.get('contamination'),
            taxonomy_status=record.get('average_nucleotide_identity', {}).get('taxonomy_check_status')))
    meta = pd.DataFrame(flat).drop_duplicates()
    assert meta.Assembly.is_unique, 'Conflicting API records require review'
    result = frame.merge(meta, on='Assembly', how='left', validate='many_to_one')
    result['biosample_identity'] = 'unknown'
    known = result.ncbi_biosample.fillna('').ne('')
    result.loc[known, 'biosample_identity'] = result.loc[known].apply(
        lambda row: 'match' if row.BioSample == row.ncbi_biosample else 'mismatch', axis=1)
    result.to_parquet(out / 'sample_metadata.parquet', index=False)
    fields = ['reported_coverage', 'contigs', 'contig_n50', 'checkm_completeness', 'checkm_contamination', 'taxonomy_status']
    report = {'species': species, 'samples': len(result),
        'missing_assembly_ids': int(result.Assembly.fillna('').eq('').sum()),
        'unique_requested_assemblies': len(accessions),
        'metadata_found': int(result.metadata_found.fillna(False).sum()),
        'biosample_identity': result.biosample_identity.value_counts().to_dict(),
        'available_fields': {f: int(result[f].notna().sum()) for f in fields},
        'assembly_status': result.assembly_status.fillna('unknown').value_counts().to_dict(),
        'taxonomy_status': result.taxonomy_status.fillna('unknown').value_counts().to_dict(),
        'limitations': ['Metadata audit only; no raw-read QC or external validation.',
            'Missing values remain unknown; no automatic exclusion or QC pass.',
            'Exact accession versions only; paired or newer assemblies are not substituted.',
            'Reported coverage is submitter metadata, not recomputed coverage.']}
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
