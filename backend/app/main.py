import hashlib
import os
from pathlib import Path
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
SUB_KEYS = ("queue", "cleanliness", "service", "pumps")

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
    """Places near a point, with latest price, rating summary and any recent anomaly alert."""
    sql = """
        SELECT p.id, p.name, p.brand, p.street, p.city,
               ST_Y(p.geom::geometry) AS lat,
               ST_X(p.geom::geometry) AS lon,
               ST_Distance(p.geom, c.pt) / 1000 AS distance_km,
               lp.price, lp.observed_at AS price_at, lp.source AS price_source,
               al.kind AS alert_kind, al.score AS alert_score, al.evidence AS alert_evidence,
               rv.n AS rating_count, rv.avg AS rating_avg, rv.demo AS rating_demo
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
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS n, avg(r.overall)::float AS avg,
                   COALESCE(bool_or(r.is_demo), false) AS demo
            FROM reviews r WHERE r.place_id = p.id
        ) rv ON true
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


class ReviewIn(BaseModel):
    overall: int = Field(ge=1, le=5)
    ratings: dict[str, int] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("ratings")
    @classmethod
    def check_ratings(cls, v):
        for key, val in v.items():
            if key not in SUB_KEYS:
                raise ValueError(f"unknown rating '{key}'")
            if not 1 <= val <= 5:
                raise ValueError(f"rating '{key}' must be 1-5")
        return v


def _hash_token(token: str | None) -> str:
    if not token or not 16 <= len(token) <= 100:
        raise HTTPException(400, "Missing or invalid reviewer token")
    return hashlib.sha256(token.encode()).hexdigest()


@app.post("/places/{place_id}/reviews", status_code=201)
def create_review(
    place_id: UUID,
    body: ReviewIn,
    x_reviewer_token: str | None = Header(default=None),
):
    """Add a review. Prototype limits: 1 review per place per 30 days, 10 per day per reviewer."""
    reviewer = _hash_token(x_reviewer_token)
    comment = (body.comment or "").strip() or None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        if not conn.execute("SELECT 1 FROM places WHERE id = %s", (place_id,)).fetchone():
            raise HTTPException(404, "Place not found")
        if conn.execute(
            "SELECT 1 FROM reviews WHERE place_id = %s AND reviewer_hash = %s "
            "AND created_at > now() - interval '30 days'", (place_id, reviewer)
        ).fetchone():
            raise HTTPException(409, "You already reviewed this place in the last 30 days")
        today = conn.execute(
            "SELECT count(*) AS n FROM reviews WHERE reviewer_hash = %s "
            "AND created_at > now() - interval '1 day'", (reviewer,)
        ).fetchone()["n"]
        if today >= 10:
            raise HTTPException(429, "Daily review limit reached")
        row = conn.execute(
            "INSERT INTO reviews (place_id, reviewer_hash, overall, ratings, comment) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at",
            (place_id, reviewer, body.overall, Jsonb(body.ratings), comment),
        ).fetchone()
    return {"id": row["id"], "created_at": row["created_at"]}


@app.get("/places/{place_id}/reviews")
def list_reviews(place_id: UUID, limit: int = Query(20, ge=1, le=50)):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        summary = conn.execute(
            "SELECT count(*)::int AS count, avg(overall)::float AS avg "
            "FROM reviews WHERE place_id = %s", (place_id,)
        ).fetchone()
        reviews = conn.execute(
            "SELECT overall, ratings, comment, created_at, is_demo FROM reviews "
            "WHERE place_id = %s ORDER BY created_at DESC LIMIT %s", (place_id, limit)
        ).fetchall()
    return {"summary": summary, "reviews": reviews}


# Serve the map page at /map (same origin as the API, so no CORS setup needed).
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/map", StaticFiles(directory=FRONTEND_DIR, html=True), name="map")
