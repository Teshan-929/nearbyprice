"""Poll Tankerkönig (MTS-K) for live German fuel prices and store the changes.

Usage (from the backend folder):
    python scripts/poll_tankerkoenig.py                 # one poll: central Berlin, 10 km
    python scripts/poll_tankerkoenig.py --rad 20        # bigger radius (max 25)
    python scripts/poll_tankerkoenig.py --loop          # poll every 5 minutes
    python scripts/poll_tankerkoenig.py --clear-demo    # delete simulated demo data

Data: Tankerkönig / MTS-K, CC BY 4.0. Credit it wherever prices are shown.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv()

LIST_URL = "https://creativecommons.tankerkoenig.de/json/list.php"
ITEMS = ("e5", "e10", "diesel")
MIN_INTERVAL = 300   # seconds: do not poll more often than every 5 minutes
BAD_KEYS = {"", "your-key-here", "00000000-0000-0000-0000-000000000002"}


def get_key() -> str:
    key = os.environ.get("TANKERKOENIG_API_KEY", "").strip()
    if key in BAD_KEYS:
        sys.exit("Put your own personal Tankerkönig key in .env as TANKERKOENIG_API_KEY. "
                 "The shared demo key only returns fake placeholder prices.")
    return key


def fetch_stations(key: str, lat: float, lng: float, rad: float) -> list[dict]:
    resp = requests.get(
        LIST_URL,
        params={"lat": lat, "lng": lng, "rad": rad, "type": "all", "apikey": key},
        headers={"User-Agent": "NearbyPrice/0.1 (open-source project)"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Tankerkönig error: {data.get('message', data)}")
    return data["stations"]


def valid_price(v) -> bool:
    """Prices come as numbers; closed or unknown stations give false/null/0."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 < v < 5


def poll_once(conn, stations: list[dict], now: datetime | None = None) -> dict:
    """Store new stations and any prices that changed since the last poll."""
    now = now or datetime.now(timezone.utc)
    known = dict(conn.execute(
        "SELECT source_id, id::text FROM places WHERE source = 'tankerkoenig' "
        "AND source_id = ANY(%s)", ([s["id"] for s in stations],)
    ).fetchall())

    new_stations = 0
    for s in stations:
        if s["id"] in known:
            continue
        street = " ".join(filter(None, [s.get("street"), s.get("houseNumber")])) or None
        row = conn.execute(
            "INSERT INTO places (source, source_id, category, name, brand, street, post_code, city, geom) "
            "VALUES ('tankerkoenig', %s, 'fuel', %s, %s, %s, %s, %s, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) "
            "ON CONFLICT (source, source_id) DO UPDATE SET name = EXCLUDED.name RETURNING id::text",
            (s["id"], s.get("name"), s.get("brand"), street, s.get("postCode"),
             s.get("place"), s["lng"], s["lat"]),
        ).fetchone()
        known[s["id"]] = row[0]
        new_stations += 1

    latest = {
        (pid, item): float(price)
        for pid, item, price in conn.execute(
            "SELECT DISTINCT ON (place_id, item) place_id::text, item, price "
            "FROM price_observations WHERE source = 'tankerkoenig' AND place_id = ANY(%s::uuid[]) "
            "ORDER BY place_id, item, observed_at DESC", (list(known.values()),)
        )
    }

    changed = []
    for s in stations:
        pid = known[s["id"]]
        for item in ITEMS:
            v = s.get(item)
            if not valid_price(v):
                continue
            price = round(float(v), 3)
            if latest.get((pid, item)) != price:
                changed.append((pid, item, price, "EUR", "tankerkoenig", now))

    if changed:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO price_observations (place_id, item, price, currency, source, observed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)", changed)
    return {"stations": len(stations), "new_stations": new_stations, "changed_prices": len(changed)}


def clear_demo(conn) -> None:
    prices = conn.execute("DELETE FROM price_observations WHERE source = 'simulated'").rowcount
    reviews = conn.execute("DELETE FROM reviews WHERE is_demo").rowcount
    alerts = conn.execute("DELETE FROM alerts").rowcount
    print(f"Removed {prices} simulated prices, {reviews} demo reviews, {alerts} alerts.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=52.52)
    ap.add_argument("--lng", type=float, default=13.405)
    ap.add_argument("--rad", type=float, default=10, help="radius in km (max 25)")
    ap.add_argument("--loop", action="store_true", help="keep polling")
    ap.add_argument("--interval", type=int, default=MIN_INTERVAL, help="seconds between polls (min 300)")
    ap.add_argument("--clear-demo", action="store_true", help="delete simulated demo data and exit")
    args = ap.parse_args()
    db_url = os.environ["DATABASE_URL"]

    if args.clear_demo:
        with psycopg.connect(db_url) as conn:
            clear_demo(conn)
        return

    key = get_key()
    rad = min(args.rad, 25)
    polls = 0
    while True:
        try:
            stations = fetch_stations(key, args.lat, args.lng, rad)
            e5 = {s.get("e5") for s in stations if valid_price(s.get("e5"))}
            if len(stations) > 5 and len(e5) == 1:
                print("Warning: every station has the same E5 price. This looks like placeholder data.")
            with psycopg.connect(db_url) as conn:
                result = poll_once(conn, stations)
            print(datetime.now().strftime("%H:%M:%S"), result)
        except Exception as err:
            if not args.loop:
                raise
            print("Poll failed, will retry:", err)
        polls += 1
        if not args.loop:
            print("Done. Run 'python scripts/run_detection.py' to refresh alerts.")
            break
        if polls % 12 == 0:   # about hourly at the default interval
            try:
                from run_detection import main as run_detection
                run_detection()
            except Exception as err:
                print("Detection failed:", err)
        time.sleep(max(args.interval, MIN_INTERVAL))


if __name__ == "__main__":
    main()