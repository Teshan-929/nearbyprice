"""Isolation Forest anomaly detector (machine-learning method to compare with MAD).

Unsupervised: it is trained only on an early 'normal' period (no labels), then scores
every later observation. Features describe how a station behaves relative to its
neighbours: deviation from its own recent baseline, short-term changes, and time of day.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def station_features(station_rel: pd.DataFrame, window: int = 336, min_periods: int = 144):
    """Return (X, valid_mask, shape). Rows are flattened (time, station), row-major."""
    base = station_rel.rolling(window, min_periods=min_periods).median().shift(1)
    dev = (station_rel - base).to_numpy()
    d1 = station_rel.diff(1).to_numpy()
    d4 = station_rel.diff(4).to_numpy()
    T, N = station_rel.shape
    hours = (station_rel.index.hour + station_rel.index.minute / 60).to_numpy()
    sin = np.repeat(np.sin(2 * np.pi * hours / 24)[:, None], N, axis=1)
    cos = np.repeat(np.cos(2 * np.pi * hours / 24)[:, None], N, axis=1)
    X = np.column_stack([a.ravel() for a in (dev, d1, d4, sin, cos)])
    valid = ~np.isnan(X).any(axis=1)
    return X, valid, (T, N)


def iforest_flags(
    station_rel: pd.DataFrame,
    train_steps: int,
    quantile: float = 0.002,
    persist: int = 2,
    seed: int = 0,
):
    """Flag unusual station observations.

    train_steps: number of initial timestamps assumed normal (used for fitting and to
    set the alert threshold: the `quantile` lowest training scores define 'unusual').
    """
    X, valid, (T, N) = station_features(station_rel)
    row_t = np.repeat(np.arange(T), N)
    train = valid & (row_t < train_steps)

    model = IsolationForest(n_estimators=200, random_state=seed)
    model.fit(X[train])
    thr = np.quantile(model.score_samples(X[train]), quantile)

    raw = np.zeros(len(X), dtype=bool)
    raw[valid] = model.score_samples(X[valid]) < thr
    raw = pd.DataFrame(raw.reshape(T, N), index=station_rel.index, columns=station_rel.columns)
    return raw.astype(int).rolling(persist).sum() == persist
