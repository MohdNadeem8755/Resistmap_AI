import hashlib
import json
import pathlib
import subprocess
from datetime import datetime, timezone
import sklearn
import numpy

root = pathlib.Path(r"D:\ResistMap-AI")
base = root / "data/processed/multispecies/tuberculosis"
matrix = base / "features/mutation_features.npz"
models = base / "supervised_models"

jobs = list(models.glob("*.joblib"))
if not jobs:
    raise FileNotFoundError("No model files found")

sha = hashlib.sha256()
with matrix.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        sha.update(chunk)

commit = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=root, text=True
).strip()
dirty = bool(subprocess.check_output(
    ["git", "status", "--porcelain"], cwd=root, text=True
).strip())

for job in jobs:
    snapshot = {
        "record_type": "current_snapshot_not_training_provenance",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": job.name,
        "current_git_commit": commit,
        "working_tree_has_changes": dirty,
        "current_sklearn_version": sklearn.__version__,
        "current_numpy_version": numpy.__version__,
        "current_feature_matrix_sha256": sha.hexdigest(),
        "training_date": None,
        "training_environment_verified": False,
        "training_feature_order_verified": False
    }
    target = models / f"{job.stem}.current_snapshot.json"
    target.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

print(f"Saved current snapshots for {len(jobs)} models.")
print("Original training provenance remains unverified.")
