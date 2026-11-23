import hashlib
import json
import pathlib
import sys

root = pathlib.Path(r"D:\ResistMap-AI")
base = root / "data/processed/multispecies/tuberculosis"
matrix = base / "features/mutation_features.npz"
snapshot_dir = base / "supervised_models"

sha = hashlib.sha256()
with matrix.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        sha.update(chunk)
expected_sha = sha.hexdigest()

models = list(snapshot_dir.glob("*.joblib"))
if not models:
    sys.exit("FAIL: No model files found.")

failed = []
for model in models:
    path = snapshot_dir / f"{model.stem}.current_snapshot.json"
    if not path.exists():
        failed.append(f"{path.name}: missing")
        continue
    try:
        snap = json.loads(path.read_text(encoding="utf-8-sig"))
        if snap.get("current_feature_matrix_sha256") != expected_sha:
            failed.append(f"{path.name}: checksum mismatch")
    except (ValueError, OSError, UnicodeError) as error:
        failed.append(f"{path.name}: {error}")

if failed:
    print("FAIL:\n" + "\n".join(failed))
    sys.exit(1)

print(f"PASS: All {len(models)} snapshots match the current matrix checksum.")
print("This does not verify training-time provenance or feature ordering.")
