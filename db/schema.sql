CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS places (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source     TEXT NOT NULL,              -- 'osm', 'tankerkoenig', 'bnetza'
  source_id  TEXT NOT NULL,
  category   TEXT NOT NULL,              -- 'fuel', 'ev_charger', 'pharmacy', ...
  name       TEXT,
  brand      TEXT,
  street     TEXT,
  post_code  TEXT,
  city       TEXT,
  geom       GEOGRAPHY(Point, 4326) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS places_geom_idx ON places USING GIST (geom);
CREATE INDEX IF NOT EXISTS places_category_idx ON places (category);

-- Store a row only when the price changes.
CREATE TABLE IF NOT EXISTS price_observations (
  place_id    UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  item        TEXT NOT NULL,             -- 'e5', 'e10', 'diesel'
  price       NUMERIC(6,3) NOT NULL,
  currency    CHAR(3) NOT NULL DEFAULT 'EUR',
  source      TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (place_id, item, observed_at)
);

CREATE TABLE IF NOT EXISTS users (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email      TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reviews (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id   UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id),
  ratings    JSONB NOT NULL,             -- {"queue":4,"cleanliness":5,...}
  comment    TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id    UUID REFERENCES places(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,             -- 'price_jump', 'regional_jump', 'stock_out'
  item        TEXT,
  score       DOUBLE PRECISION,
  evidence    JSONB,                     -- values used to explain the alert
  detected_at TIMESTAMPTZ DEFAULT now()
);
