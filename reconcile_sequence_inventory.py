"""Reconcile checkpointed sequence features without inventing QC or training status."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCALE = ROOT / 'results/ceftazidime_sequence_scaleup'


def reconcile():
    with (SCALE / 'development_processing_queue.csv').open(newline='', encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    expected = {row['BioSample'] for row in rows}
    main = json.loads((SCALE / 'genomic_features_main_partial.json').read_text())
    expanded = json.loads((SCALE / 'genomic_features_with_called_sites_partial.json').read_text())
    completed = []
    for checkpoint in sorted((SCALE / 'reads/completed').glob('*.json')):
        record = json.loads(checkpoint.read_text())
        sample = record['summary']['BioSample']
        if sample not in expected:
            raise ValueError(f'Unexpected checkpoint {sample}')
        feature_path = SCALE / 'reads/feature_rows' / f'{sample}.json'
        features = json.loads(feature_path.read_text())
        main[sample] = features['main']
        expanded[sample] = features['with_called_sites']
        completed.append(sample)
    if set(main) - expected or set(expanded) != set(main):
        raise ValueError('Feature inventory does not match expected cohort')
    missing = sorted(expected - set(main))
    target = SCALE / 'reconciled'
    target.mkdir(exist_ok=True)
    for name, data in [('main_features.json', main), ('expanded_features.json', expanded)]:
        temp = target / (name + '.tmp')
        temp.write_text(json.dumps(data, indent=2))
        temp.replace(target / name)
    report = {'expected_samples': len(expected), 'available_samples': len(main),
              'completed_read_checkpoints': len(completed), 'missing_samples': missing,
              'sequence_processing_complete': not missing, 'contamination_screen': 'pending',
              'eligible_for_final_training': False,
              'reason': 'Biological QC and inclusion decisions must be completed before final training.',
              'fresh_independent_validation': 'pending'}
    (target / 'inventory.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'missing_samples'}, indent=2))
    return report


if __name__ == '__main__':
    reconcile()
