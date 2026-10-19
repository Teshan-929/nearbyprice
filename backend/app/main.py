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
    limit: int = Query(50, ge=1, le=200),
):
    sql = """
        SELECT id, name, brand, street, city,
               ST_Y(geom::geometry) AS lat,
               ST_X(geom::geometry) AS lon,
               ST_Distance(geom, p.pt) / 1000 AS distance_km
        FROM places,
             (SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS pt) p
        WHERE category = %(category)s
          AND ST_DWithin(geom, p.pt, %(radius_m)s)
        ORDER BY distance_km
        LIMIT %(limit)s
    """
    params = {
        "lat": lat,
        "lon": lon,
        "category": category,
        "radius_m": radius_km * 1000,
        "limit": limit,
    }
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"count": len(rows), "places": rows}


# Serve the map page at /map (same origin as the API, so no CORS setup needed).
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/map", StaticFiles(directory=FRONTEND_DIR, html=True), name="map")