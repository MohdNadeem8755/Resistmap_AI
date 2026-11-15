"""Resolve authoritative GTDB GenBank aliases before measuring reference coverage."""
import hashlib
import json
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/external/multispecies_candidate_screen/reference_coverage'
URL = 'https://data.gtdb.ecogenomic.org/releases/release226/226.0/bac120_metadata_r226.tsv.gz'


def main():
    path = OUT / 'bac120_metadata_r226.tsv.gz'
    if not path.exists():
        partial = path.with_suffix('.part')
        with requests.get(URL, stream=True, timeout=(30, 60)) as r:
            r.raise_for_status()
            n = 0
            with partial.open('wb') as f:
                for block in r.iter_content(1024*1024):
                    f.write(block)
                    n += len(block)
                    if n % (50*1024*1024) == 0:
                        print('Downloaded metadata MB:', n//(1024*1024), flush=True)
            assert not r.headers.get('Content-Length') or n == int(r.headers['Content-Length'])
        partial.replace(path)
    header = pd.read_csv(path, sep='\t', nrows=0).columns
    assert 'ncbi_genbank_assembly_accession' in header, list(header)
    columns = ['accession', 'ncbi_genbank_assembly_accession']
    frames = list(pd.read_csv(path, sep='\t', usecols=columns, dtype=str, keep_default_na=False, chunksize=100000))
    aliases = pd.concat(frames, ignore_index=True)
    aliases['index_accession'] = aliases.accession.str.replace(r'^(RS_|GB_)', '', regex=True)
    index = pd.read_csv(OUT / 'gtdb-rs226.lineages.csv', usecols=['ident'], dtype=str)
    aliases = aliases[aliases.index_accession.isin(set(index.ident))]
    aliases.to_parquet(OUT / 'verified_genbank_aliases.parquet', index=False)
    exact = set(index.ident)
    alias_ids = set(aliases.ncbi_genbank_assembly_accession) - {'', 'none', 'na'}
    summaries = []
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        p = ROOT / 'reports/multispecies_validation_readiness' / (species + '_previously_seen_keys.parquet')
        seen = pd.read_parquet(p)
        assemblies = sorted(set(seen.Assembly) - {''})
        df = pd.DataFrame({'Assembly': assemblies})
        df['exact_index_match'] = df.Assembly.isin(exact)
        df['documented_genbank_alias_match'] = df.Assembly.isin(alias_ids)
        df['covered_by_inventory'] = df.exact_index_match | df.documented_genbank_alias_match
        df.to_parquet(OUT / (species + '_alias_coverage.parquet'), index=False)
        covered = set(df.loc[df.covered_by_inventory, 'Assembly'])
        summaries.append({'species': species, 'previous_assemblies': len(df),
            'covered_exact_or_alias': len(covered), 'not_covered': len(df)-len(covered),
            'coverage_percent': round(100*len(covered)/len(df), 3),
            'samples_with_missing_assembly': int(seen.loc[seen.Assembly.eq(''), 'BioSample'].nunique())})
    report = {'source': URL, 'metadata_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'cohorts': summaries, 'step_1_complete': False, 'genome_overlap_search_completed': False,
        'decision': 'This reference is insufficient for a full-development no-overlap claim. Uncovered references and missing assemblies remain unresolved.',
        'limitations': 'Inventory coverage is not sequence independence. Paired accession coverage is accepted only where explicitly documented by GTDB metadata; sketch membership is still unverified.'}
    (OUT / 'alias_coverage_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
