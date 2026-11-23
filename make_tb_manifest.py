import json, pathlib, re
root = pathlib.Path(r'D:\ResistMap-AI')
log_path = root / 'reports' / 'tb_training_log.txt'
report_path = root / 'data' / 'processed' / 'multispecies' / 'tuberculosis' / 'supervised_models' / 'report.json'
manifest_path = root / 'data' / 'processed' / 'multispecies' / 'tuberculosis' / 'training_manifest.json'
log = log_path.read_text(encoding='utf-8')
trained = [m.group(1) for m in re.finditer(r'TRAIN (\w+)\s+\|', log)]
skipped = [m.group(1) for m in re.finditer(r'SKIP\s+(\w+)\s+\|', log)]
report = json.loads(report_path.read_text(encoding='utf-8'))
manifest = {
    "training_log_path": str(log_path),
    "model_report_path": str(report_path),
    "dataset": {
        "samples": report['split_counts'],
        "features": {"total": report['feature_selection']['total_features'], "selected": report['feature_selection']['selected_features']}
    },
    "drugs": {"trained": trained, "skipped": skipped},
    "split_policy": report.get('split_policy'),
    "limitations": report.get('limitations', ''),
    "notes": "Generated from existing logs; original manifest missing."
}
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(f'Manifest written to {manifest_path}')
