# NearbyPrice

**NearbyPrice** is an open-source map that shows current fuel prices (and soon other essentials) near you, highlights unusual price jumps in your region, and ranks places using price, distance, and community reviews. It starts with Germany, using official MTS-K data via Tankerkönig and place data from OpenStreetMap.

> Alerts are statistical indicators of unusual price changes. They are not proof of overcharging or supply problems.

## Status

Early development. Current focus: OpenStreetMap station import and a nearby-places API.

## Planned features

- Map of nearby stations with price, price age, and "cheapest nearby" colors
- Anomaly alerts for sudden regional price jumps (rolling median/MAD, per station and hour of day)
- Structured community reviews and a "Best pick" ranking
- More categories: EV charging, pharmacies, groceries

## Quick start

Requirements: Docker, Python 3.11+.

```bash
cp .env.example .env            # then edit the values
docker compose up -d            # Postgres + PostGIS, schema loads automatically

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/import_osm_fuel.py Berlin
uvicorn app.main:app --reload
```

Then open <http://localhost:8000/places/nearby?lat=52.52&lon=13.405&radius_km=3> or the interactive docs at <http://localhost:8000/docs>.

## Tech stack

FastAPI, PostgreSQL + PostGIS, MapLibre GL (frontend, planned), OpenStreetMap.

## Data attribution

- Fuel price data: Tankerkönig / MTS-K, licensed under CC BY 4.0.
- Map data: © OpenStreetMap contributors (ODbL).

Respect each source's terms and rate limits.

## License

MIT, see [LICENSE](LICENSE).
