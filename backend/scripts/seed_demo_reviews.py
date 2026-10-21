"""Create DEMO reviews (flagged is_demo) so the ratings and Best-pick ranking have data.

Usage (from the backend folder):
    python scripts/seed_demo_reviews.py
Re-running replaces the previous demo reviews. Real reviews are never touched.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

load_dotenv()
SUB_KEYS = ("queue", "cleanliness", "service", "pumps")


def main():
    rng = np.random.default_rng(11)
    now = datetime.now(timezone.utc)
    brand_effect, rows = {}, []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        places = conn.execute("SELECT id::text, brand FROM places WHERE category = 'fuel'").fetchall()
        for pid, brand in places:
            quality = rng.normal(3.8, 0.55) + brand_effect.setdefault(brand or "?", rng.normal(0, 0.2))
            for _ in range(int(rng.choice([0, 0, 1, 2, 3, 5, 8, 12, 20, 30]))):
                overall = int(np.clip(round(rng.normal(quality, 0.9)), 1, 5))
                ratings = {k: int(np.clip(round(rng.normal(quality, 1.0)), 1, 5))
                           for k in SUB_KEYS if rng.random() < 0.6}
                created = now - timedelta(days=float(rng.uniform(0, 90)))
                rows.append((pid, "demo-" + uuid.uuid4().hex, overall, Jsonb(ratings), created))
        conn.execute("DELETE FROM reviews WHERE is_demo")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO reviews (place_id, reviewer_hash, overall, ratings, created_at, is_demo) "
                "VALUES (%s, %s, %s, %s, %s, true)", rows)
    print(f"Wrote {len(rows)} demo reviews for {len(places)} stations.")


if __name__ == "__main__":
    main()
