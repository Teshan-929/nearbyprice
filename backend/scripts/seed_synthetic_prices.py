"""Fill the database with SIMULATED prices for the stations you imported.

Everything written here is tagged source='simulated' so it can be told apart from real
data and is replaced every time you run this script.

Usage (from the backend folder):
    python scripts/seed_synthetic_prices.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.regions import grid_region            # noqa: E402
from app.synthetic import simulate_market      # noqa: E402

load_dotenv()
DAYS = 14
ITEM_OFFSETS = {"e5": 0.0, "e10": -0.06, "diesel": -0.12}   # E10 and diesel vs E5


def main():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        places = conn.execute(
            "SELECT id::text, ST_Y(geom::geometry), ST_X(geom::geometry), name, street "
            "FROM places WHERE category = 'fuel'"
        ).fetchall()
        if not places:
            sys.exit("No fuel stations found. Run scripts/import_osm_fuel.py first.")

        region_of = {pid: grid_region(lat, lon) for pid, lat, lon, _, _ in places}
        label = {pid: f"{name or 'Fuel station'}, {street or '?'}" for pid, _, _, name, street in places}

        end = pd.Timestamp.now(tz="UTC").floor("30min")
        ts = pd.date_range(end=end, periods=DAYS * 48, freq="30min")
        wide, injected = simulate_market(region_of, ts)

        conn.execute("DELETE FROM price_observations WHERE source = 'simulated'")
        conn.execute("DELETE FROM alerts")
        n_rows = 0
        with conn.cursor() as cur:
            with cur.copy(
                "COPY price_observations (place_id, item, price, currency, source, observed_at) "
                "FROM STDIN"
            ) as copy:
                for item, offset in ITEM_OFFSETS.items():
                    prices = wide + offset
                    for pid in prices.columns:
                        s = prices[pid]
                        for t, v in s[s.ne(s.shift())].items():     # store changes only
                            copy.write_row((pid, item, round(float(v), 3), "EUR",
                                            "simulated", t.to_pydatetime()))
                            n_rows += 1

    print(f"Wrote {n_rows} simulated price rows for {len(places)} stations "
          f"({DAYS} days, items: {', '.join(ITEM_OFFSETS)}).")
    print("\nInjected live price spikes (the detector should find these):")
    for sp in injected:
        print(f"  +{sp['magnitude']:.2f} EUR for the last {sp['hours']:.0f} h at {label[sp['station_id']]}")


if __name__ == "__main__":
    main()
