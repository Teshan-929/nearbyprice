"""Synthetic fuel-price generator with labelled anomalies.

Real prices are not needed to develop or test the detector: we simulate a market with
a daily cycle, a market-wide drift, regional and station offsets, then inject known
spikes. Because we know where the spikes are, we can measure precision and recall.
"""
import numpy as np
import pandas as pd


def make_synthetic(
    n_regions: int = 5,
    per_region: int = 8,
    days: int = 30,
    step_min: int = 30,
    seed: int = 42,
    n_station_events: int = 25,
    n_region_events: int = 1,
):
    """Return (prices_long, events).

    prices_long columns: ts, station_id, region, price
    events columns: kind ('station'|'region'), target, start, end, magnitude
    """
    rng = np.random.default_rng(seed)
    steps_per_day = 24 * 60 // step_min
    ts = pd.date_range("2026-01-01", periods=days * steps_per_day, freq=f"{step_min}min")
    n = n_regions * per_region
    station_ids = [f"S{i:03d}" for i in range(n)]
    region_ids = [f"R{r}" for r in range(n_regions)]
    region_of = {sid: region_ids[i // per_region] for i, sid in enumerate(station_ids)}

    hours = ts.hour + ts.minute / 60
    day_idx = np.arange(len(ts)) // steps_per_day
    drift = np.cumsum(rng.normal(0, 0.008, days))[day_idx]  # market-wide movement
    region_offset = rng.normal(0, 0.02, n_regions)
    station_offset = rng.normal(0, 0.015, n)

    prices = np.empty((len(ts), n))
    for j in range(n):
        # each station follows the daily cycle a little earlier/later and with its own strength
        shift_h = rng.normal(0, 1.5)
        amp = rng.uniform(0.6, 1.4)
        own_cycle = amp * 0.05 * np.cos(2 * np.pi * (hours - 8 - shift_h) / 24)
        own_walk = np.cumsum(rng.normal(0, 0.006, days))[day_idx]   # slow station-specific drift
        prices[:, j] = (
            1.80 + drift + own_cycle + own_walk + region_offset[j // per_region]
            + station_offset[j] + rng.normal(0, 0.012, len(ts))
        )
    wide = pd.DataFrame(prices, index=ts, columns=station_ids)

    warmup = 8 * steps_per_day  # keep events after the detector has some history
    events, used = [], {}

    def free(target, a, b):
        return all(b < s or a > e for s, e in used.get(target, []))

    attempts = 0
    while sum(e["kind"] == "station" for e in events) < n_station_events and attempts < 1000:
        attempts += 1
        sid = str(rng.choice(station_ids))
        dur = int(rng.integers(3 * 60 // step_min, 12 * 60 // step_min + 1))
        start = int(rng.integers(warmup, len(ts) - dur - 1))
        if not free(sid, start, start + dur - 1):
            continue
        mag = float(rng.choice([0.03, 0.05, 0.08, 0.12, 0.20, 0.30]))
        wide.iloc[start:start + dur, wide.columns.get_loc(sid)] += mag
        used.setdefault(sid, []).append((start, start + dur - 1))
        events.append(dict(kind="station", target=sid, start=ts[start],
                           end=ts[start + dur - 1], magnitude=mag))

    for _ in range(n_region_events):
        rid = str(rng.choice(region_ids))
        dur = int(rng.integers(24 * 60 // step_min, 48 * 60 // step_min + 1))
        start = int(rng.integers(warmup, len(ts) - dur - 1))
        cols = [s for s in station_ids if region_of[s] == rid]
        wide.iloc[start:start + dur, [wide.columns.get_loc(c) for c in cols]] += 0.12
        events.append(dict(kind="region", target=rid, start=ts[start],
                           end=ts[start + dur - 1], magnitude=0.12))

    wide = wide.round(3)
    long = wide.stack().rename("price").reset_index()
    long.columns = ["ts", "station_id", "price"]
    long["region"] = long["station_id"].map(region_of)
    return long[["ts", "station_id", "region", "price"]], pd.DataFrame(events)
