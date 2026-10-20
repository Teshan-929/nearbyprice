"""Robust price-anomaly detection: rolling median + MAD (baseline method).

Two views of the same market:
  * station view: station price minus the median of its region at the same moment
    ("unusual compared to its neighbours"). Removes the shared daily cycle.
  * region view: region median minus the national median
    ("unusual regional jump").

A point is flagged when its robust z-score is large AND the deviation is big enough
in euros (so tiny but statistically 'significant' wiggles are ignored), and it
persists for several consecutive samples.
"""
import pandas as pd


def robust_flags(
    wide: pd.DataFrame,
    window: int = 336,        # 7 days of 30-minute samples
    min_periods: int = 144,   # need 3 days of history before flagging
    z: float = 4.0,
    min_dev: float = 0.03,    # euros
    persist: int = 2,         # consecutive samples required
    mad_floor: float = 0.002,
):
    """wide: timestamp x series DataFrame of relative prices. Returns (flags, z, dev)."""
    med = wide.rolling(window, min_periods=min_periods).median().shift(1)
    dev = wide - med
    mad = dev.abs().rolling(window, min_periods=min_periods).median().shift(1)
    mad = mad.clip(lower=mad_floor)
    zs = 0.6745 * dev / mad
    raw = (zs.abs() > z) & (dev.abs() > min_dev)
    flags = raw.astype(int).rolling(persist).sum() == persist
    return flags, zs, dev


def relative_views(prices: pd.DataFrame):
    """Return (station_rel, region_rel): prices relative to regional / national medians."""
    wide = prices.pivot(index="ts", columns="station_id", values="price").sort_index()
    region_of = prices.drop_duplicates("station_id").set_index("station_id")["region"]
    regions = region_of.reindex(wide.columns)

    region_med = wide.T.groupby(regions.values).median().T          # ts x region
    national = wide.median(axis=1)

    neighbours = region_med.reindex(columns=regions.values).set_axis(wide.columns, axis=1)
    station_rel = wide - neighbours
    region_rel = region_med.sub(national, axis=0)
    return station_rel, region_rel


def detect(prices: pd.DataFrame, **kwargs):
    """prices columns: ts, station_id, region, price (one fuel type).

    Returns dict with 'station' and 'region' results, each a (flags, z, dev) tuple.
    """
    station_rel, region_rel = relative_views(prices)
    return {
        "station": robust_flags(station_rel, **kwargs),
        "region": robust_flags(region_rel, **kwargs),
    }
