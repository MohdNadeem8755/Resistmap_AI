"""Audit exact-accession coverage before selecting a genomic reference index."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/external/multispecies_candidate_screen/reference_coverage'
URL = 'https://farm.cse.ucdavis.edu/~ctbrown/sourmash-db.new/gtdb-rs226/gtdb-rs226.lineages.csv'


def main():
    OUT.mkdir(exist_ok=True)
    path = OUT / 'gtdb-rs226.lineages.csv'
    if not path.exists():
        partial = path.with_suffix('.part')
        with requests.get(URL, stream=True, timeout=(30, 60)) as r:
            r.raise_for_status()
            assert r.status_code == 200, 'Partial response is not a complete index inventory'
            sha = hashlib.sha256()
            size = 0
            with partial.open('wb') as stream:
                for block in r.iter_content(1024*1024):
                    stream.write(block)
                    sha.update(block)
                    size += len(block)
            assert not r.headers.get('Content-Length') or size == int(r.headers['Content-Length'])
        partial.replace(path)
        (OUT / 'source.json').write_text(json.dumps({'url': URL, 'bytes': size,
            'sha256': sha.hexdigest(), 'retrieved_utc': datetime.now(timezone.utc).isoformat()}, indent=2))
    reference = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert reference.ident.is_unique
    ids = set(reference.ident)
    reports = []
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        previous = pd.read_parquet(ROOT / 'reports/multispecies_validation_readiness' / (species + '_previously_seen_keys.parquet'))
        assemblies = sorted(set(previous.Assembly) - {''})
        coverage = pd.DataFrame({'Assembly': assemblies})
        coverage['exact_accession_present'] = coverage.Assembly.isin(ids)
        coverage.to_parquet(OUT / (species + '_assembly_coverage.parquet'), index=False)
        # All previously seen isolates are checked, not just the fitted model subset.
        matched = previous.Assembly.isin(ids)
        report = {'species': species, 'distinct_previous_assemblies': len(assemblies),
            'exact_accessions_in_index': int(coverage.exact_accession_present.sum()),
            'accessions_requiring_alias_resolution_or_new_sketch': int((~coverage.exact_accession_present).sum()),
            'biosamples_with_exact_index_match': int(previous.loc[matched, 'BioSample'].nunique()),
            'biosamples_with_missing_assembly': int(previous.loc[previous.Assembly.eq(''), 'BioSample'].nunique()),
            'full_reference_coverage_verified': False}
        reports.append(report)
    report = {'reference': 'GTDB RS226 entire-genome index accession inventory',
        'reference_records': len(reference), 'cohorts': reports,
        'decision': 'Do not certify independence using this index until missing accession coverage and GCA/GCF aliases are resolved.',
        'limitations': ['Exact accession coverage is a lower bound: paired GenBank/RefSeq accessions may differ.',
            'Taxonomy inventory is not the actual sketch manifest; sketch integrity and membership still require verification.',
            'No genome similarity search has been performed.']}
    (OUT / 'coverage_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
