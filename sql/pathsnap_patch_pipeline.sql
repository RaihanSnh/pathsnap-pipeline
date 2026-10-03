-- Columns the pipeline needs (run after the Bandung patch)
ALTER TABLE places         ADD COLUMN IF NOT EXISTS osm_ref     VARCHAR(30) UNIQUE;  -- e.g. node/123
ALTER TABLE accommodations ADD COLUMN IF NOT EXISTS osm_ref     VARCHAR(30) UNIQUE;
ALTER TABLE places         ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;
ALTER TABLE accommodations ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;

INSERT INTO data_sources (name, base_url) VALUES
  ('overpass_osm',  'https://overpass-api.de'),
  ('google_places', 'https://places.googleapis.com'),
  ('gemini_scoring','https://ai.google.dev')
ON CONFLICT (name) DO NOTHING;
