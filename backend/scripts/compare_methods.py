"""Compare the rolling-median/MAD baseline with an Isolation Forest on synthetic data.

Usage (from the backend folder):
    python scripts/compare_methods.py

Results are pooled over several random seeds, because a single 30-day run has only
~25 injected spikes and is noisy.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.anomaly import relative_views, robust_flags   # noqa: E402
from app.iforest import iforest_flags                  # noqa: E402
from app.synthetic import make_synthetic               # noqa: E402
from evaluate_synthetic import score                   # noqa: E402

SEEDS = range(1, 6)
TRAIN_STEPS = 8 * 48          # first 8 days (no injected events), 30-minute samples
METHODS = {
    "MAD z=3": lambda rel: robust_flags(rel, z=3.0)[0],
    "MAD z=4": lambda rel: robust_flags(rel, z=4.0)[0],
    "MAD z=5": lambda rel: robust_flags(rel, z=5.0)[0],
    "IForest q=1%":    lambda rel: iforest_flags(rel, TRAIN_STEPS, quantile=0.01),
    "IForest q=0.2%":  lambda rel: iforest_flags(rel, TRAIN_STEPS, quantile=0.002),
    "IForest q=0.05%": lambda rel: iforest_flags(rel, TRAIN_STEPS, quantile=0.0005),
}


def main():
    totals = {m: dict(events=0, detected=0, episodes=0, fa=0, delays=[], mag={}) for m in METHODS}
    station_months = 0.0
    for seed in SEEDS:
        prices, events = make_synthetic(seed=seed)
        st_events = events[events["kind"] == "station"]
        rel, _ = relative_views(prices)
        station_months += prices["station_id"].nunique() * 30 / 30
        for name, fn in METHODS.items():
            r = score(fn(rel), st_events)
            t = totals[name]
            t["events"] += r["events"]; t["detected"] += r["detected"]
            t["episodes"] += r["episodes"]; t["fa"] += r["false_alarms"]
            if r["median_delay_min"] == r["median_delay_min"]:
                t["delays"].append(r["median_delay_min"])
            for m, (h, n) in r["mag_counts"].items():
                a = t["mag"].setdefault(m, [0, 0]); a[0] += h; a[1] += n

    mags = sorted({m for t in totals.values() for m in t["mag"]})
    head = f"{'method':<16}{'recall':>8}{'precision':>11}{'false alarms/station-month':>28}"
    print(f"{len(list(SEEDS))} simulated months pooled\n")
    print(head + "".join(f"{m:>7.2f}" for m in mags) + "   <- recall by spike size (EUR)")
    for name, t in totals.items():
        recall = t["detected"] / t["events"]
        precision = (t["episodes"] - t["fa"]) / max(t["episodes"], 1)
        fa_rate = t["fa"] / station_months
        by = "".join(f"{t['mag'][m][0] / t['mag'][m][1]:>7.0%}" if m in t["mag"] else f"{'-':>7}" for m in mags)
        print(f"{name:<16}{recall:>8.0%}{precision:>11.0%}{fa_rate:>28.2f}{by}")


if __name__ == "__main__":
    main()