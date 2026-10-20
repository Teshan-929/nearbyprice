"""Measure the detector on synthetic data with known injected anomalies.

Usage (from the backend folder):
    python scripts/evaluate_synthetic.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.anomaly import detect          # noqa: E402
from app.synthetic import make_synthetic  # noqa: E402

STEP_MIN = 30


def episodes(flag: pd.Series, max_gap: int = 4):
    """Group consecutive flagged samples into (start, end) alert episodes."""
    idx = np.flatnonzero(flag.values)
    if len(idx) == 0:
        return []
    out, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > max_gap:
            out.append((s, p))
            s = i
        p = i
    out.append((s, p))
    return [(flag.index[a], flag.index[b]) for a, b in out]


def score(flags: pd.DataFrame, events: pd.DataFrame, grace_steps: int = 2):
    grace = pd.Timedelta(minutes=STEP_MIN * grace_steps)
    n_eps = fp_eps = detected = 0
    delays, by_mag = [], {}
    for col in flags.columns:
        ev = list(events[events["target"] == col].itertuples())
        for a, b in episodes(flags[col]):
            n_eps += 1
            if not any(a <= e.end + grace and b >= e.start for e in ev):
                fp_eps += 1
        for e in ev:
            window = flags[col][e.start: e.end + grace]
            hit = bool(window.any())
            detected += hit
            by_mag.setdefault(e.magnitude, []).append(hit)
            if hit:
                first = window[window].index[0]
                delays.append((first - e.start) / pd.Timedelta(minutes=1))
    return dict(
        events=len(events), detected=detected, episodes=n_eps, false_alarms=fp_eps,
        recall=detected / max(len(events), 1),
        precision=(n_eps - fp_eps) / max(n_eps, 1),
        median_delay_min=float(np.median(delays)) if delays else float("nan"),
        recall_by_magnitude={m: sum(v) / len(v) for m, v in sorted(by_mag.items())},
        mag_counts={m: (sum(v), len(v)) for m, v in sorted(by_mag.items())},
    )


def main():
    prices, events = make_synthetic(seed=42, days=30)
    n_stations = prices["station_id"].nunique()
    n_days = (prices["ts"].max() - prices["ts"].min()).days + 1
    st_events = events[events["kind"] == "station"]
    rg_events = events[events["kind"] == "region"]

    print(f"{n_stations} stations, {n_days} days, "
          f"{len(st_events)} station spikes, {len(rg_events)} regional jump(s)\n")

    for z in (3.0, 4.0, 5.0):
        res = detect(prices, z=z)
        s = score(res["station"][0], st_events)
        r = score(res["region"][0], rg_events)
        fa_rate = s["false_alarms"] / (n_stations * n_days / 30)
        print(f"--- z threshold = {z} ---")
        print(f"Station spikes: recall {s['recall']:.0%} ({s['detected']}/{s['events']}), "
              f"precision {s['precision']:.0%}, false alarms {s['false_alarms']} "
              f"({fa_rate:.2f} per station-month), median delay {s['median_delay_min']:.0f} min")
        print("  recall by size (EUR):",
              {f"{m:.2f}": f"{v:.0%}" for m, v in s["recall_by_magnitude"].items()})
        print(f"Regional jumps: recall {r['recall']:.0%} ({r['detected']}/{r['events']}), "
              f"false alarms {r['false_alarms']}, median delay {r['median_delay_min']:.0f} min\n")


if __name__ == "__main__":
    main()
