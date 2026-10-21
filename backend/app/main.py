import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="NearbyPrice API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/places/nearby")
def nearby(
    lat: float,
    lon: float,
    radius_km: float = Query(5, gt=0, le=25),
    category: str = "fuel",
    fuel: str = Query("e5", pattern="^(e5|e10|diesel)$"),
    limit: int = Query(50, ge=1, le=200),
):
    """Places near a point, with their latest price and any recent anomaly alert."""
    sql = """
        SELECT p.id, p.name, p.brand, p.street, p.city,
               ST_Y(p.geom::geometry) AS lat,
               ST_X(p.geom::geometry) AS lon,
               ST_Distance(p.geom, c.pt) / 1000 AS distance_km,
               lp.price, lp.observed_at AS price_at, lp.source AS price_source,
               al.kind AS alert_kind, al.score AS alert_score, al.evidence AS alert_evidence
        FROM places p
        CROSS JOIN (SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS pt) c
        LEFT JOIN LATERAL (
            SELECT o.price, o.observed_at, o.source
            FROM price_observations o
            WHERE o.place_id = p.id AND o.item = %(fuel)s
            ORDER BY o.observed_at DESC LIMIT 1
        ) lp ON true
        LEFT JOIN LATERAL (
            SELECT a.kind, a.score, a.evidence
            FROM alerts a
            WHERE a.place_id = p.id AND a.item = %(fuel)s
              AND a.detected_at > now() - interval '3 hours'
            ORDER BY a.detected_at DESC LIMIT 1
        ) al ON true
        WHERE p.category = %(category)s
          AND ST_DWithin(p.geom, c.pt, %(radius_m)s)
        ORDER BY distance_km
        LIMIT %(limit)s
    """
    params = {
        "lat": lat, "lon": lon, "category": category, "fuel": fuel,
        "radius_m": radius_km * 1000, "limit": limit,
    }
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"count": len(rows), "fuel": fuel, "places": rows}


# Serve the map page at /map (same origin as the API, so no CORS setup needed).
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/map", StaticFiles(directory=FRONTEND_DIR, html=True), name="map")
