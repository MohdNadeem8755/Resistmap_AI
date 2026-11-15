"""Screen public study metadata for identifier overlap; do not infer independence."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from resolve_missing_assembly_links import get

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/external/multispecies_candidate_screen'
STUDIES = [
    ('escherichia_coli', 'PRJEB115520', 'https://www.medrxiv.org/content/10.64898/2026.08.27.26361401v1.full'),
    ('acinetobacter_baumannii', 'PRJNA1286014', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC13340785/'),
    ('acinetobacter_baumannii', 'PRJNA573295', 'https://research.birmingham.ac.uk/files/256488886/DinNS2025Whole-genome.pdf'),
]


def download(url, path, params=None):
    if path.exists():
        return
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=50)
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    path.write_bytes(response.content)
    path.with_suffix(path.suffix + '.provenance.json').write_text(json.dumps({
        'url': response.url, 'retrieved_utc': datetime.now(timezone.utc).isoformat(),
        'sha256': hashlib.sha256(response.content).hexdigest()}, indent=2))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for species, project, source in STUDIES:
        path = OUT / (project + '_ena_runs.tsv')
        params = {'accession': project, 'result': 'read_run', 'format': 'tsv',
            'fields': 'run_accession,sample_accession,secondary_sample_accession,study_accession,scientific_name',
            'download': 'true'}
        download('https://www.ebi.ac.uk/ena/portal/api/filereport', path, params)
        runs = pd.read_csv(path, sep='\t', dtype=str, keep_default_na=False)
        previous = pd.read_parquet(ROOT / 'reports/multispecies_validation_readiness' / (species + '_previously_seen_keys.parquet'))
        seen = set(previous.BioSample) - {''}
        samples = runs[['sample_accession', 'secondary_sample_accession', 'scientific_name']].drop_duplicates().copy()
        assembly_count = 0
        if samples.empty:
            cache = OUT / (project + '_assembly_cache')
            cache.mkdir(exist_ok=True)
            search = get('esearch', {'term': project + '[BioProject]', 'retmax': 10000}, cache)['esearchresult']
            uids = search['idlist']
            assert len(uids) == int(search['count']), 'Truncated project lookup'
            assemblies = []
            for start in range(0, len(uids), 100):
                summary = get('esummary', {'id': ','.join(uids[start:start+100])}, cache)['result']
                for uid in summary['uids']:
                    record = summary[uid]
                    assert 'error' not in record
                    assemblies.append(record)
            assembly_count = len(assemblies)
            samples = pd.DataFrame([{
                'sample_accession': r.get('biosampleaccn', ''),
                'secondary_sample_accession': '',
                'scientific_name': r.get('speciesname', '')
            } for r in assemblies], columns=['sample_accession', 'secondary_sample_accession', 'scientific_name']).drop_duplicates()
            pd.DataFrame([{'BioSample': r.get('biosampleaccn', ''),
                'Assembly': r.get('assemblyaccession', ''),
                'paired_genbank': r.get('synonym', {}).get('genbank', ''),
                'paired_refseq': r.get('synonym', {}).get('refseq', '')}
                for r in assemblies]).to_parquet(OUT / (project + '_assembly_identifiers.parquet'), index=False)
        def aliases(row):
            return set((row.sample_accession + ';' + row.secondary_sample_accession).split(';')) - {''}
        samples['seen_identifier_overlap'] = pd.Series([bool(aliases(row) & seen) for row in samples.itertuples()], index=samples.index, dtype=bool)
        samples['has_biosample_identifier'] = pd.Series([any(v.startswith('SAM') for v in aliases(row)) for row in samples.itertuples()], index=samples.index, dtype=bool)
        samples['species_name_matches'] = samples.scientific_name.str.match('^' + species.replace('_', ' ').capitalize() + r'(?:\s|$)')
        samples.to_parquet(OUT / (project + '_sample_overlap.parquet'), index=False)
        report = {'species': species, 'project': project, 'source': source,
            'runs': len(runs), 'fallback_assembly_records': assembly_count, 'sample_records': len(samples),
            'overlapping_sample_records': int(samples.seen_identifier_overlap.sum()),
            'no_identifier_overlap_records': int((~samples.seen_identifier_overlap & samples.has_biosample_identifier).sum()),
            'missing_biosample_identifier_records': int((~samples.has_biosample_identifier).sum()),
            'species_name_mismatch_records': int((~samples.species_name_matches).sum()),
            'independence_established': False,
            'pending': ['Assembly aliases, genomic relatedness and exact profiles must be checked.',
                        'Per-isolate phenotype availability and annotation compatibility require review.']}
        report['screen_status'] = ('lookup_unresolved_no_records' if samples.empty else
            'reject_all_samples_previously_seen' if samples.seen_identifier_overlap.all() else
            'requires_further_overlap_review')
        results.append(report)
        print(json.dumps(report), flush=True)
    # The Liverpool source uses local IDs; never equate zero string matches with independence.
    for remote, local in [('1/README.md', 'liverpool_README.md'), ('2/meta_data_tidy.txt', 'liverpool_metadata.tsv')]:
        download('https://datacat.liverpool.ac.uk/3008/' + remote, OUT / local)
    metadata = pd.read_csv(OUT / 'liverpool_metadata.tsv', sep='\t', dtype=str)
    results.append({'species': 'escherichia_coli', 'source': 'https://datacat.liverpool.ac.uk/3008/',
        'metadata_rows': len(metadata), 'unique_local_ids': int(metadata.genome_id.nunique()),
        'independence_established': False, 'status': 'blocked_on_accession_crosswalk',
        'limitations': ['Local strain IDs cannot be compared with BioSample IDs.',
            'Phenotype-enriched sampling is not representative prevalence.',
            'AMRFinderPlus 3.11.14 / database 2023-07-13.2 differs from development annotations.']})
    (OUT / 'screen_report.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
