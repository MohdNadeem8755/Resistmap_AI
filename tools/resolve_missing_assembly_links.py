"""Find candidate public assembly links; never replace annotation provenance."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]


def get(kind, params, cache):
    params = dict(params, db='assembly', retmode='json')
    key = hashlib.sha256((kind + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = cache / (key + '.json')
    if path.exists():
        return json.loads(path.read_text())['response']
    url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/' + kind + '.fcgi'
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=40)
            r.raise_for_status()
            data = r.json()
            if 'error' in data:
                raise ValueError(data['error'])
            break
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    path.write_text(json.dumps({'url': url, 'parameters': params,
        'retrieved_utc': datetime.now(timezone.utc).isoformat(), 'response': data}))
    time.sleep(.4)
    return data


def run(species):
    base = ROOT / 'data/processed/multispecies' / species / 'unsupervised_profiles'
    out = base / 'missing_assembly_lookup'
    cache = out / 'source_cache'
    cache.mkdir(parents=True, exist_ok=True)
    audit = pd.read_parquet(base / 'assembly_metadata_audit/sample_metadata.parquet')
    missing = audit.loc[audit.Assembly.fillna('').eq(''), ['BioSample', 'matrix_row']].copy()
    records = []
    ids = sorted(missing.BioSample)
    for start in range(0, len(ids), 30):
        term = ' OR '.join(s + '[BioSample]' for s in ids[start:start+30])
        search = get('esearch', {'term': term, 'retmax': 10000}, cache)['esearchresult']
        uids = search['idlist']
        assert len(uids) == int(search['count']), 'Truncated assembly search'
        for pos in range(0, len(uids), 100):
            summary = get('esummary', {'id': ','.join(uids[pos:pos+100])}, cache)['result']
            for uid in summary['uids']:
                r = summary[uid]
                if 'error' in r:
                    raise ValueError(r['error'])
                records.append({'BioSample': r.get('biosampleaccn'),
                    'candidate_assembly': r.get('assemblyaccession'),
                    'species_name': r.get('speciesname'),
                    'assembly_name': r.get('assemblyname'),
                    'release_date': r.get('asmreleasedate_genbank')})
        print(species, min(start+30, len(ids)), '/', len(ids), flush=True)
    candidates = pd.DataFrame(records, columns=['BioSample', 'candidate_assembly', 'species_name', 'assembly_name', 'release_date']).drop_duplicates()
    candidates = candidates[candidates.BioSample.isin(ids)]
    candidates.to_parquet(out / 'candidate_assemblies.parquet', index=False)
    counts = candidates.groupby('BioSample').candidate_assembly.nunique()
    missing['candidate_count'] = missing.BioSample.map(counts).fillna(0).astype(int)
    missing['lookup_status'] = missing.candidate_count.map(lambda n: 'none_found' if n == 0 else 'single_candidate' if n == 1 else 'multiple_candidates')
    missing.to_parquet(out / 'lookup_status.parquet', index=False)
    report = {'species': species, 'missing_ids_checked': len(missing),
        'lookup_status': missing.lookup_status.value_counts().to_dict(),
        'candidate_records': len(candidates),
        'interpretation': 'Exact BioSample lookup only. Candidates are not confirmed sources of existing AMR annotations. Original features and splits unchanged. New links to existing samples are not independent validation data.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    for species in ['escherichia_coli', 'acinetobacter_baumannii']:
        run(species)
