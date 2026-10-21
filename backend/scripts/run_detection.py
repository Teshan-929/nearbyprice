"""Run the anomaly detector on the prices in the database and store active alerts.

Usage (from the backend folder):
    python scripts/run_detection.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.anomaly import relative_views_from_wide, robust_flags   # noqa: E402
from app.regions import grid_region                              # noqa: E402

load_dotenv()
ITEMS = ["e5", "e10", "diesel"]


def build_wide(df: pd.DataFrame) -> pd.DataFrame:
    """Change-only rows -> regular 30-minute grid, carrying each price forward."""
    piv = df.pivot(index="observed_at", columns="place_id", values="price").sort_index()
    grid = pd.date_range(piv.index.min().floor("30min"),
                         pd.Timestamp.now(tz="UTC").floor("30min"), freq="30min")
    return piv.reindex(piv.index.union(grid)).ffill().reindex(grid)


def find_active_alerts(wide: pd.DataFrame, region_of: dict, recent_steps: int = 2, **kwargs):
    """Stations flagged in the most recent `recent_steps` samples."""
    station_rel, _ = relative_views_from_wide(wide, region_of)
    flags, zs, dev = robust_flags(station_rel, **kwargs)
    out = []
    for col in wide.columns:
        recent = flags[col].iloc[-recent_steps:]
        if not recent.any():
            continue
        idx = recent[recent].index[-1]
        d = float(dev.at[idx, col])
        out.append(dict(
            place_id=col, observed_at=idx,
            price=float(wide.at[idx, col]),
            region_median=float(wide.at[idx, col] - station_rel.at[idx, col]),
            deviation=d, z=float(zs.at[idx, col]),
            kind="price_jump" if d > 0 else "unusual_discount",
        ))
    return out


def main():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        places = conn.execute(
            "SELECT id::text, ST_Y(geom::geometry), ST_X(geom::geometry), name, street "
            "FROM places WHERE category = 'fuel'"
        ).fetchall()
        region_of = {pid: grid_region(lat, lon) for pid, lat, lon, _, _ in places}
        label = {pid: f"{name or 'Fuel station'}, {street or '?'}" for pid, _, _, name, street in places}

        for item in ITEMS:
            rows = conn.execute(
                "SELECT place_id::text, observed_at, price FROM price_observations "
                "WHERE item = %s AND observed_at >= now() - interval '14 days'", (item,)
            ).fetchall()
            if not rows:
                print(f"[{item}] no price data, skipping")
                continue
            df = pd.DataFrame(rows, columns=["place_id", "observed_at", "price"])
            df["price"] = df["price"].astype(float)
            df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)

            alerts = find_active_alerts(build_wide(df), region_of)
            conn.execute("DELETE FROM alerts WHERE item = %s AND evidence->>'method' = 'mad'", (item,))
            for a in alerts:
                evidence = {
                    "method": "mad", "window_days": 7,
                    "observed_at": a["observed_at"].isoformat(),
                    "price": round(a["price"], 3),
                    "region_median": round(a["region_median"], 3),
                    "deviation_eur": round(a["deviation"], 3),
                    "z": round(a["z"], 1),
                }
                conn.execute(
                    "INSERT INTO alerts (place_id, kind, item, score, evidence) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (a["place_id"], a["kind"], item, a["z"], Jsonb(evidence)),
                )
            print(f"[{item}] {len(alerts)} active alert(s)")
            if item == "e5":
                for a in sorted(alerts, key=lambda x: -abs(x["z"])):
                    print(f"   {a['deviation']:+.3f} EUR (z={a['z']:.1f})  {label[a['place_id']]}")


if __name__ == "__main__":
    main()
