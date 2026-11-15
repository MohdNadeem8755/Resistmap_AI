"""Prepare a non-overlapping EUCAST external cohort and assembly accession list."""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AST = Path(r'D:\downloading files\asts_all_standards.tsv')
OUT = ROOT / 'data' / 'external'


def read(path, delimiter=','):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def main():
    ast = read(AST, '\t')
    old = {r['BioSample'] for r in read(ROOT / 'results/ceftazidime_clsi_split_v2.csv')}
    labels = defaultdict(set)
    ast_rows = {}
    for row in ast:
        sample = row['#BioSample'].strip()
        if row['Testing standard'] == 'EUCAST':
            labels[sample].add(row['Resistance phenotype'])
            ast_rows[sample] = row
    candidates = {sample for sample, values in labels.items()
                  if len(values) == 1 and sample not in old}
    isolate_rows = {}
    for row in read(ROOT / 'data/raw/isolates_with_metadata.tsv', '\t'):
        sample = row['BioSample'].strip()
        if sample in candidates and sample not in isolate_rows:
            isolate_rows[sample] = row
    output = []
    for sample in sorted(candidates):
        ast_row, isolate = ast_rows[sample], isolate_rows.get(sample, {})
        output.append({
            'BioSample': sample,
            'Isolate': ast_row['Isolate'],
            'phenotype': next(iter(labels[sample])),
            'testing_standard': 'EUCAST',
            'MIC_mg_L': ast_row['MIC (mg/L)'],
            'measurement_sign': ast_row['Measurement sign'],
            'disk_diffusion_mm': ast_row['Disk diffusion (mm)'],
            'location': ast_row['Location'],
            'create_date': ast_row['Create date'],
            'Assembly': isolate.get('Assembly', '').strip(),
            'SNP_cluster': isolate.get('SNP cluster', '').strip(),
            'genome_metadata_available': bool(isolate),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'eucast_external_candidates.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=output[0])
        writer.writeheader(); writer.writerows(output)
    accessions = sorted({r['Assembly'] for r in output if r['Assembly']})
    (OUT / 'assembly_accessions.txt').write_text('\n'.join(accessions) + '\n')
    susceptible = sum(r['phenotype'] == 'susceptible' for r in output)
    resistant = sum(r['phenotype'] == 'resistant' for r in output)
    print(f'EUCAST candidates: {len(output)} (S={susceptible}, R={resistant})')
    print(f'Assemblies available: {len(accessions)}; missing: {len(output)-len(accessions)}')


if __name__ == '__main__':
    main()
