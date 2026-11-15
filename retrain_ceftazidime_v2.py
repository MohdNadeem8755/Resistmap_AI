"""Retrain ceftazidime V2 inside the existing notebook using %run -i.

All displayed scores are DEVELOPMENT SELECTION scores, not independent accuracy.
The old 114-sample test set is excluded from training and selection. Because its
results have already informed further development, V2 needs fresh external data.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from IPython.display import display
from sklearn.base import clone
from sklearn.ensemble import (
    RandomForestClassifier, ExtraTreesClassifier,
    HistGradientBoostingClassifier,
)
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import FixedThresholdClassifier
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits


def retrain_v2(ns):
    required = [
        "root", "cohort", "train_idx", "test_idx", "cv_folds",
        "feature_dicts", "y", "groups", "profile_keys", "snp_keys",
        "tuned_model",
    ]
    missing = [name for name in required if name not in ns]
    if missing:
        raise ValueError("Run the earlier notebook cells first. Missing: " + ", ".join(missing))

    root = Path(ns["root"])
    cohort = ns["cohort"]
    dev = np.asarray(ns["train_idx"], dtype=int)
    legacy_test = set(np.asarray(ns["test_idx"], dtype=int))
    labels = np.asarray(ns["y"], dtype=int)
    features = ns["feature_dicts"]
    groups = np.asarray(ns["groups"])
    profiles, snps = ns["profile_keys"], ns["snp_keys"]
    dev_set = set(dev)
    assert len(dev_set) == len(dev) and dev_set.isdisjoint(legacy_test)
    assert set(labels[dev]) == {0, 1}
    assert set(groups[dev]).isdisjoint({groups[i] for i in legacy_test})
    assert {profiles[i] for i in dev}.isdisjoint({profiles[i] for i in legacy_test})
    assert {snps[i] for i in dev if snps[i] is not None}.isdisjoint(
        {snps[i] for i in legacy_test if snps[i] is not None}
    )

    folds = []
    validation_rows = []
    for number, (fit, val) in enumerate(ns["cv_folds"], 1):
        fit, val = np.asarray(fit, dtype=int), np.asarray(val, dtype=int)
        assert set(fit).issubset(dev_set) and set(val).issubset(dev_set)
        assert set(fit).isdisjoint(set(val))
        assert set(labels[fit]) == {0, 1} and set(labels[val]) == {0, 1}
        assert set(groups[fit]).isdisjoint(set(groups[val]))
        assert {profiles[i] for i in fit}.isdisjoint({profiles[i] for i in val})
        assert {snps[i] for i in fit if snps[i] is not None}.isdisjoint(
            {snps[i] for i in val if snps[i] is not None}
        )
        folds.append((fit, val))
        validation_rows.extend(val.tolist())

    assert len(validation_rows) == len(dev)
    assert set(validation_rows) == dev_set

    # Fixed, bounded candidate list. The V1 configuration is retained as a control.
    models = {
        "RF_v1_control": clone(ns["tuned_model"].named_steps["classifier"])
    }
    models["RF_v1_control"].set_params(n_jobs=4)
    for leaf in (1, 2, 4):
        models[f"RF_leaf_{leaf}"] = RandomForestClassifier(
            n_estimators=600, max_features=0.5, min_samples_leaf=leaf,
            class_weight="balanced", random_state=42, n_jobs=4,
        )
        models[f"ExtraTrees_leaf_{leaf}"] = ExtraTreesClassifier(
            n_estimators=600, max_features=0.5, min_samples_leaf=leaf,
            class_weight="balanced", random_state=42, n_jobs=4,
        )
    for c in (0.1, 1.0):
        models[f"Logistic_C_{c}"] = LogisticRegression(
            C=c, class_weight="balanced", solver="liblinear",
            max_iter=5000, random_state=42,
        )
    for leaves in (7, 15):
        models[f"HistGB_leaves_{leaves}"] = HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.05, max_leaf_nodes=leaves,
            min_samples_leaf=10, l2_regularization=1.0,
            class_weight="balanced", early_stopping=False, random_state=42,
        )

    # A single threshold is selected for all folds of a candidate.
    # It is not adjusted separately for an evaluation project or test sample.
    thresholds = np.round(np.arange(0.10, 0.901, 0.05), 2)

    def make_pipeline(estimator):
        return Pipeline([
            ("features", DictVectorizer(sparse=False, dtype=np.float64)),
            ("classifier", clone(estimator)),
        ])

    def threshold_metrics(actual, probability, threshold):
        predicted = (probability >= threshold).astype(int)
        s_recall = float(np.mean(predicted[actual == 0] == 0))
        r_recall = float(np.mean(predicted[actual == 1] == 1))
        return {
            "balanced_accuracy": (s_recall + r_recall) / 2,
            "accuracy": float(np.mean(actual == predicted)),
            "S_recall": s_recall,
            "R_recall": r_recall,
        }

    selection_rows, probability_parts, fold_outputs = [], [], {}
    print(f"Training {len(models)} candidates across {len(folds)} existing folds.")
    print(f"CV fits: {len(models) * len(folds)}; followed by one final development fit.")
    print("Threshold objective: highest mean development-CV balanced accuracy.")
    print("These are selection scores; fresh independent validation is required.", flush=True)

    with threadpool_limits(limits=4):
        for name, estimator in models.items():
            candidate_folds = []
            for fold, (fit, val) in enumerate(folds, 1):
                pipeline = make_pipeline(estimator)
                pipeline.fit([features[int(i)] for i in fit], labels[fit])
                classes = pipeline.named_steps["classifier"].classes_
                r_index = list(classes).index(1)
                probability = pipeline.predict_proba(
                    [features[int(i)] for i in val]
                )[:, r_index]
                assert np.isfinite(probability).all()
                candidate_folds.append((labels[val].copy(), probability.copy()))
                probability_parts.append(pd.DataFrame({
                    "candidate": name, "fold": fold, "row_id": val,
                    "BioSample": cohort.iloc[val]["BioSample"].astype(str).to_numpy(),
                    "actual": labels[val], "probability_R": probability,
                }))
                print(f"{name}: fold {fold}/{len(folds)} complete", flush=True)

            fold_outputs[name] = candidate_folds
            auc = float(np.mean([
                roc_auc_score(actual, probability)
                for actual, probability in candidate_folds
            ]))
            for threshold in thresholds:
                metrics = [
                    threshold_metrics(actual, probability, threshold)
                    for actual, probability in candidate_folds
                ]
                record = {
                    "candidate": name, "threshold": float(threshold),
                    "roc_auc": auc,
                    "worst_fold_BA": min(m["balanced_accuracy"] for m in metrics),
                    "distance_from_0_5": abs(float(threshold) - 0.5),
                }
                for metric in ("balanced_accuracy", "accuracy", "S_recall", "R_recall"):
                    record[metric] = float(np.mean([m[metric] for m in metrics]))
                selection_rows.append(record)

        table = pd.DataFrame(selection_rows).sort_values(
            ["balanced_accuracy", "worst_fold_BA", "distance_from_0_5"],
            ascending=[False, False, True], kind="stable",
        ).reset_index(drop=True)

        best = table.iloc[0]
        name, threshold = str(best["candidate"]), float(best["threshold"])
        final_v2 = FixedThresholdClassifier(
            estimator=make_pipeline(models[name]),
            threshold=threshold, pos_label=1, response_method="predict_proba",
        )
        final_v2.fit([features[int(i)] for i in dev], labels[dev])

    # Verify that the saved classifier uses exactly the selected threshold.
    check_x = [features[int(i)] for i in dev[:5]]
    r_index = list(final_v2.classes_).index(1)
    manual = (final_v2.predict_proba(check_x)[:, r_index] >= threshold).astype(int)
    assert np.array_equal(final_v2.predict(check_x), manual)

    selected_fold_rows = []
    for fold, (actual, probability) in enumerate(fold_outputs[name], 1):
        selected_fold_rows.append({
            "fold": fold,
            "threshold": threshold,
            **threshold_metrics(actual, probability, threshold),
            "roc_auc": roc_auc_score(actual, probability),
        })
    selected_folds = pd.DataFrame(selected_fold_rows)

    # Save each run separately, preserving all V1 results.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_dir = root / "results" / f"ceftazidime_v2_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    model_path = run_dir / "model_with_threshold.joblib"
    joblib.dump(final_v2, model_path)
    table.to_csv(run_dir / "development_selection.csv", index=False)
    pd.concat(probability_parts, ignore_index=True).to_csv(
        run_dir / "development_oof_probabilities.csv", index=False
    )
    selected_folds.to_csv(run_dir / "selected_development_folds.csv", index=False)

    metadata = {
        "status": "retrained; requires fresh independent validation",
        "target": "ceftazidime", "testing_standard": "CLSI",
        "feature_encoding": {
            "COMPLETE": "gene:<name>=1", "POINT": "mutation:<name>=1",
            "other_statuses": "excluded",
        },
        "labels": {"0": "susceptible", "1": "resistant"},
        "candidate": name, "threshold": threshold,
        "decision_rule": "predict resistant if probability_R >= threshold",
        "parameters": models[name].get_params(),
        "selection_objective": "mean development-CV balanced accuracy",
        "selection_score": float(best["balanced_accuracy"]),
        "selection_score_is_independent_accuracy": False,
        "legacy_test_evaluated_in_this_run": False,
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "training_biosamples": cohort.iloc[dev]["BioSample"].astype(str).tolist(),
        "candidates": {key: model.get_params() for key, model in models.items()},
        "threshold_grid": thresholds.tolist(),
    }
    with open(run_dir / "metadata.json", "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    columns = [
        "candidate", "threshold", "balanced_accuracy", "accuracy",
        "S_recall", "R_recall", "worst_fold_BA", "roc_auc",
    ]
    top = table.drop_duplicates("candidate")[columns].head(8).copy()
    score_columns = columns[2:]
    top[score_columns] = top[score_columns] * 100
    top = top.rename(columns={column: column + "_%" for column in score_columns})
    print("\nDEVELOPMENT SELECTION SCORES ONLY — not independent accuracy:")
    display(top.round(2))
    print(f"\nSelected: {name}; threshold: {threshold:.2f}")
    fold_display = selected_folds.copy()
    metrics = ["balanced_accuracy", "accuracy", "S_recall", "R_recall", "roc_auc"]
    fold_display[metrics] = fold_display[metrics] * 100
    fold_display = fold_display.rename(columns={column: column + "_%" for column in metrics})
    display(fold_display.round(2))
    print("\nSaved classifier with threshold:", model_path)
    print("V2 predict() applies the selected threshold automatically.")
    print("AUC and selection scores are not verified 99% accuracy.")

    return {
        "v2_model": final_v2, "v2_selection": table,
        "v2_fold_scores": selected_folds, "v2_run_dir": run_dir,
    }


if __name__ == "__main__":
    globals().update(retrain_v2(globals()))

