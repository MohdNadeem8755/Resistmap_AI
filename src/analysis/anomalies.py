"""Fit anomaly detector on training data, threshold on separate calibration data."""
import numpy as np
from sklearn.ensemble import IsolationForest


def fit_detector(training, calibration, review_fraction=0.03, seed=42):
    if not 0 < review_fraction < 1:
        raise ValueError('Review fraction must be between zero and one.')
    model = IsolationForest(n_estimators=300, contamination='auto', random_state=seed, n_jobs=4)
    model.fit(training)
    threshold = float(np.quantile(-model.score_samples(calibration), 1 - review_fraction))
    return model, threshold


def score_samples(model, threshold, features):
    scores = -model.score_samples(features)
    return scores, scores > threshold
