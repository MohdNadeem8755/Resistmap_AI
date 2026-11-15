"""Training-fitted visualization representations."""
from sklearn.decomposition import PCA


def fit_representation(training, method='pca', components=2, seed=42):
    if method == 'pca':
        model = PCA(n_components=components, random_state=seed)
    elif method == 'umap':
        from umap import UMAP
        model = UMAP(n_components=components, random_state=seed)
    else:
        raise ValueError('Unknown representation method')
    return model, model.fit_transform(training)
