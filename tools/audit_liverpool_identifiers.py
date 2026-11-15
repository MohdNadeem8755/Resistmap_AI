"""Audit public file identifiers and cohort coverage, without interpreting AMR calls."""
import io
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin
import pandas as pd
import requests
from screen_external_studies import download, OUT


def main():
    page = 'https://datacat.liverpool.ac.uk/3008/'
    html = requests.get(page, timeout=40)
    html.raise_for_status()
    links = [urljoin(page, x) for x in re.findall(r'href=["\']([^"\']+)["\']', html.text)]
    for name, local in [('annots.zip', 'liverpool_annots.zip'),
                        ('meta_data_bv_brc_format.txt', 'liverpool_long_metadata.tsv')]:
        matches = sorted(set(x for x in links if x.endswith('/' + name)))
        assert len(matches) == 1, (name, matches)
        download(matches[0], OUT / local)
    pattern = re.compile(r'\b(?:SAM[NED][A-Z]*\d+|GC[AF]_\d+(?:\.\d+)?|PRJ(?:NA|EB|DB)\d+|[SED]RR\d+)\b')
    evidence = []
    local_ids = []
    with zipfile.ZipFile(OUT / 'liverpool_annots.zip') as archive:
        bad = archive.testzip()
        assert bad is None, bad
        for entry in archive.infolist():
            if entry.is_dir() or entry.filename.startswith('__MACOSX/'):
                continue
            text = archive.read(entry).decode('utf-8', errors='replace')
            identifiers = sorted(set(pattern.findall(entry.filename + '\n' + text)))
            evidence.append({'file': entry.filename, 'accessions': identifiers})
            if entry.filename.endswith('.tsv'):
                local_ids.append(Path(entry.filename).stem)
    metadata = pd.read_csv(OUT / 'liverpool_metadata.tsv', sep='\t', dtype=str)
    long = pd.read_csv(OUT / 'liverpool_long_metadata.tsv', sep='\t', dtype=str)
    for name in ['liverpool_README.md', 'liverpool_metadata.tsv', 'liverpool_long_metadata.tsv']:
        evidence.append({'file': name, 'accessions': sorted(set(pattern.findall((OUT / name).read_text(encoding='utf-8'))))})
    annotation_ids, phenotype_ids = set(local_ids), set(metadata.genome_id)
    # Only an exact local filename match is used; no inferred identifier conversion.
    table = pd.DataFrame({'local_id': sorted(annotation_ids | phenotype_ids)})
    table['annotation_file_present'] = table.local_id.isin(annotation_ids)
    table['phenotype_metadata_present'] = table.local_id.isin(phenotype_ids)
    table.to_csv(OUT / 'liverpool_file_coverage.csv', index=False)
    report = {'annotation_files': len(local_ids), 'unique_annotation_ids': len(annotation_ids),
        'wide_metadata_unique_ids': len(phenotype_ids), 'long_metadata_unique_ids': int(long.genome_id.nunique()),
        'exact_local_id_matches': len(annotation_ids & phenotype_ids),
        'annotation_only_ids': sorted(annotation_ids - phenotype_ids),
        'phenotype_only_ids': sorted(phenotype_ids - annotation_ids),
        'accession_mentions': evidence, 'independence_confirmed': False,
        'scope': 'README, both phenotype tables, and all annotation archive entries; genome archive not examined.',
        'conclusion': 'No crosswalk may be inferred from local IDs or reference protein accessions. Sequence-based duplicate/relatedness screening or an authoritative accession crosswalk is still required.'}
    (OUT / 'liverpool_identifier_audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['accession_mentions','annotation_only_ids','phenotype_only_ids']}))
    print('Files with accession mentions:', sum(bool(x['accessions']) for x in evidence))
    print('Example filenames:', local_ids[:4])


if __name__ == '__main__':
    main()
