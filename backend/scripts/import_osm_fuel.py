"""Import fuel stations for one area from OpenStreetMap (Overpass API).

Usage:
    python scripts/import_osm_fuel.py Berlin

Data: (c) OpenStreetMap contributors, ODbL.
Be polite to the public Overpass server: run this rarely, not in a loop.
"""
import os
import sys

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "NearbyPrice/0.1 (open-source project)"}

QUERY = """
[out:json][timeout:90];
area["name"="{area}"]["boundary"="administrative"]->.a;
(
  node["amenity"="fuel"](area.a);
  way["amenity"="fuel"](area.a);
);
out center tags;
"""


def fetch(area: str) -> list[dict]:
    resp = requests.post(
        OVERPASS_URL, data={"data": QUERY.format(area=area)}, headers=HEADERS, timeout=120
    )
    resp.raise_for_status()
    return resp.json()["elements"]


def main(area: str) -> None:
    elements = fetch(area)
    rows = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        street = " ".join(
            filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")])
        )
        rows.append(
            (
                f"{el['type']}/{el['id']}",
                tags.get("name") or tags.get("brand"),
                tags.get("brand"),
                street or None,
                tags.get("addr:postcode"),
                tags.get("addr:city"),
                lon,
                lat,
            )
        )

    sql = """
        INSERT INTO places (source, source_id, category, name, brand, street, post_code, city, geom)
        VALUES ('osm', %s, 'fuel', %s, %s, %s, %s, %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)
        ON CONFLICT (source, source_id) DO UPDATE
          SET name = EXCLUDED.name, brand = EXCLUDED.brand, street = EXCLUDED.street,
              post_code = EXCLUDED.post_code, city = EXCLUDED.city, geom = EXCLUDED.geom
    """
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    print(f"Imported {len(rows)} fuel stations for '{area}'.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/import_osm_fuel.py <area name>")
    main(sys.argv[1])
