-- Reviews without full accounts (prototype): a hashed browser token identifies a reviewer.
ALTER TABLE reviews ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS overall SMALLINT CHECK (overall BETWEEN 1 AND 5);
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS reviewer_hash TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE reviews ALTER COLUMN ratings SET DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS reviews_place_idx ON reviews (place_id, created_at DESC);
CREATE INDEX IF NOT EXISTS reviews_reviewer_idx ON reviews (reviewer_hash, created_at DESC);
