"""Reusable clustering methods from the exploratory workflow."""
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.metrics import pairwise_distances


def cluster(features, method='kmeans', clusters=8, seed=42, eps=0.5, min_samples=5):
    if method == 'kmeans':
        model = KMeans(n_clusters=clusters, n_init=10, random_state=seed)
        return model, model.fit_predict(features)
    distance = pairwise_distances(features.astype(bool), metric='jaccard')
    if method == 'hierarchical':
        model = AgglomerativeClustering(n_clusters=clusters, metric='precomputed', linkage='average')
    elif method == 'dbscan':
        model = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
    else:
        raise ValueError('Unknown clustering method')
    return model, model.fit_predict(distance)
