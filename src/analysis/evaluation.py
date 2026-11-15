"""Evaluation helpers. Anomaly flags alone do not establish biological novelty."""
import numpy as np
from sklearn.metrics import silhouette_score, adjusted_rand_score


def cluster_quality(features, labels, reference=None, metric='euclidean'):
    labels = np.asarray(labels)
    valid = labels != -1
    selected = features[np.ix_(valid, valid)] if metric == 'precomputed' else features[valid]
    count = len(np.unique(labels[valid]))
    score = None
    if 1 < count < int(valid.sum()):
        score = float(silhouette_score(selected, labels[valid], metric=metric,
                                       sample_size=min(1000, int(valid.sum())), random_state=42))
    return {'silhouette': score, 'noise_count': int((~valid).sum()),
            'adjusted_rand': None if reference is None else float(adjusted_rand_score(reference, labels))}
