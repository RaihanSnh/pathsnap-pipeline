-- =====================================================================
-- PATHSNAP DATABASE SCHEMA  (PostgreSQL 15+ with PostGIS)
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy name search / dedup

-- ---------------------------------------------------------------------
-- ENUMS
-- ---------------------------------------------------------------------
CREATE TYPE accommodation_type AS ENUM (
    'hotel', 'villa', 'resort', 'hostel', 'guesthouse',
    'homestay', 'apartment', 'glamping', 'campground', 'other'
);
CREATE TYPE price_level AS ENUM ('free', 'budget', 'moderate', 'expensive', 'luxury');
CREATE TYPE scrape_status AS ENUM ('pending', 'extracted', 'needs_review', 'approved', 'rejected', 'duplicate');
CREATE TYPE entity_kind AS ENUM ('place', 'accommodation');

-- ---------------------------------------------------------------------
-- REGION HIERARCHY
-- ---------------------------------------------------------------------
CREATE TABLE provinces (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE cities (
    id          SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id),
    name        VARCHAR(100) NOT NULL,
    type        VARCHAR(20) DEFAULT 'kota',        -- kota / kabupaten
    UNIQUE (province_id, name)
);

-- ---------------------------------------------------------------------
-- PLACES (tourist destinations, culinary, nature, culture, etc.)
-- ---------------------------------------------------------------------
CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,       -- Nature, Culinary, Culture, Shopping...
    slug        VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE places (
    id                  BIGSERIAL PRIMARY KEY,
    slug                VARCHAR(160) NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    category_id         INT REFERENCES categories(id),
    city_id             INT NOT NULL REFERENCES cities(id),
    address             TEXT,
    -- Map point: geography(Point) gives real-world distances in meters
    location            geography(Point, 4326) NOT NULL,
    latitude            DOUBLE PRECISION GENERATED ALWAYS AS (ST_Y(location::geometry)) STORED,
    longitude           DOUBLE PRECISION GENERATED ALWAYS AS (ST_X(location::geometry)) STORED,
    -- Rating
    rating_avg          NUMERIC(2,1) CHECK (rating_avg BETWEEN 0 AND 5),
    rating_count        INT NOT NULL DEFAULT 0,
    -- Price (entrance ticket / average spend), in IDR
    price_min           NUMERIC(12,0) CHECK (price_min >= 0),
    price_max           NUMERIC(12,0) CHECK (price_max >= price_min),
    price_level         price_level,
    -- Practical info
    opening_hours       JSONB,                     -- {"mon":"08:00-17:00", ...}
    phone               VARCHAR(30),
    website             TEXT,
    google_place_id     VARCHAR(100) UNIQUE,       -- helps dedup + re-sync
    -- Hidden gem
    is_hidden_gem       BOOLEAN NOT NULL DEFAULT FALSE,
    hidden_gem_score    NUMERIC(4,3) CHECK (hidden_gem_score BETWEEN 0 AND 1),
    hidden_gem_reason   TEXT,                      -- AI-written explanation
    -- Meta
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_places_location ON places USING GIST (location);
CREATE INDEX idx_places_city     ON places (city_id);
CREATE INDEX idx_places_category ON places (category_id);
CREATE INDEX idx_places_gem      ON places (hidden_gem_score DESC) WHERE is_hidden_gem;
CREATE INDEX idx_places_name_trgm ON places USING GIN (name gin_trgm_ops);

CREATE TABLE tags (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(60) NOT NULL UNIQUE            -- instagrammable, family-friendly, sunrise...
);
CREATE TABLE place_tags (
    place_id BIGINT NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    tag_id   INT    NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (place_id, tag_id)
);

CREATE TABLE place_images (
    id          BIGSERIAL PRIMARY KEY,
    place_id    BIGINT NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    caption     VARCHAR(200),
    is_cover    BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order  INT NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------
-- ACCOMMODATIONS (hotel, villa, homestay, ...)
-- ---------------------------------------------------------------------
CREATE TABLE accommodations (
    id                  BIGSERIAL PRIMARY KEY,
    slug                VARCHAR(160) NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    type                accommodation_type NOT NULL,
    star_class          SMALLINT CHECK (star_class BETWEEN 1 AND 5),
    city_id             INT NOT NULL REFERENCES cities(id),
    address             TEXT,
    location            geography(Point, 4326) NOT NULL,
    latitude            DOUBLE PRECISION GENERATED ALWAYS AS (ST_Y(location::geometry)) STORED,
    longitude           DOUBLE PRECISION GENERATED ALWAYS AS (ST_X(location::geometry)) STORED,
    rating_avg          NUMERIC(2,1) CHECK (rating_avg BETWEEN 0 AND 5),
    rating_count        INT NOT NULL DEFAULT 0,
    -- Price per night, in IDR
    price_per_night_min NUMERIC(12,0) CHECK (price_per_night_min >= 0),
    price_per_night_max NUMERIC(12,0) CHECK (price_per_night_max >= price_per_night_min),
    price_level         price_level,
    check_in_time       TIME,
    check_out_time      TIME,
    total_rooms         INT,
    max_guests          INT,                       -- useful for villas
    phone               VARCHAR(30),
    website             TEXT,
    booking_url         TEXT,
    google_place_id     VARCHAR(100) UNIQUE,
    is_hidden_gem       BOOLEAN NOT NULL DEFAULT FALSE,
    hidden_gem_score    NUMERIC(4,3) CHECK (hidden_gem_score BETWEEN 0 AND 1),
    hidden_gem_reason   TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_accom_location ON accommodations USING GIST (location);
CREATE INDEX idx_accom_city     ON accommodations (city_id);
CREATE INDEX idx_accom_type     ON accommodations (type);
CREATE INDEX idx_accom_name_trgm ON accommodations USING GIN (name gin_trgm_ops);

CREATE TABLE amenities (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(80) NOT NULL UNIQUE            -- WiFi, Pool, Breakfast, Parking, AC...
);
CREATE TABLE accommodation_amenities (
    accommodation_id BIGINT NOT NULL REFERENCES accommodations(id) ON DELETE CASCADE,
    amenity_id       INT    NOT NULL REFERENCES amenities(id)      ON DELETE CASCADE,
    PRIMARY KEY (accommodation_id, amenity_id)
);

CREATE TABLE accommodation_images (
    id               BIGSERIAL PRIMARY KEY,
    accommodation_id BIGINT NOT NULL REFERENCES accommodations(id) ON DELETE CASCADE,
    url              TEXT NOT NULL,
    caption          VARCHAR(200),
    is_cover         BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order       INT NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------
-- AI-ASSISTED SCRAPING PIPELINE (hidden gems)
-- raw scrape -> AI extraction -> review -> promoted into places/accommodations
-- ---------------------------------------------------------------------
CREATE TABLE data_sources (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,      -- google_maps, tiktok, instagram, blog, tripadvisor
    base_url    TEXT,
    notes       TEXT
);

CREATE TABLE scrape_runs (
    id          BIGSERIAL PRIMARY KEY,
    source_id   INT NOT NULL REFERENCES data_sources(id),
    query       TEXT,                              -- e.g. "hidden gem Bandung"
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    items_found INT DEFAULT 0
);

CREATE TABLE raw_scraped_items (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES scrape_runs(id) ON DELETE CASCADE,
    source_url      TEXT,
    raw_payload     JSONB NOT NULL,                -- untouched scraped data
    content_hash    CHAR(64) UNIQUE,               -- avoid storing the same item twice
    status          scrape_status NOT NULL DEFAULT 'pending',
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_raw_status ON raw_scraped_items (status);

CREATE TABLE ai_extractions (
    id                  BIGSERIAL PRIMARY KEY,
    raw_item_id         BIGINT NOT NULL REFERENCES raw_scraped_items(id) ON DELETE CASCADE,
    model_name          VARCHAR(100) NOT NULL,     -- which LLM did the extraction
    prompt_version      VARCHAR(30),
    extracted_kind      entity_kind,               -- place or accommodation
    extracted_data      JSONB NOT NULL,            -- name, lat/lng, price, category, ...
    hidden_gem_score    NUMERIC(4,3),
    hidden_gem_reason   TEXT,
    confidence          NUMERIC(4,3),
    needs_review        BOOLEAN NOT NULL DEFAULT TRUE,
    promoted_place_id           BIGINT REFERENCES places(id),
    promoted_accommodation_id   BIGINT REFERENCES accommodations(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (promoted_place_id IS NULL OR promoted_accommodation_id IS NULL)
);

-- Which sources back a given record (provenance)
CREATE TABLE place_sources (
    place_id    BIGINT NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    source_id   INT    NOT NULL REFERENCES data_sources(id),
    source_url  TEXT,
    last_synced TIMESTAMPTZ,
    PRIMARY KEY (place_id, source_id)
);

-- ---------------------------------------------------------------------
-- AUTO-UPDATE updated_at
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_places_updated  BEFORE UPDATE ON places
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_accom_updated   BEFORE UPDATE ON accommodations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- EXAMPLE QUERIES (distance-based)
-- ---------------------------------------------------------------------
-- 1) Distance between a place and every accommodation within 5 km:
--
-- SELECT a.name, a.type, a.price_per_night_min,
--        ROUND(ST_Distance(a.location, p.location)) AS distance_m
-- FROM places p
-- JOIN accommodations a
--   ON ST_DWithin(a.location, p.location, 5000)
-- WHERE p.slug = 'kawah-putih'
-- ORDER BY distance_m;
--
-- 2) Places near the user's current position (lat -6.9175, lng 107.6191), 10 km:
--
-- SELECT name, rating_avg, price_min,
--        ROUND(ST_Distance(location, ST_SetSRID(ST_MakePoint(107.6191, -6.9175), 4326)::geography)) AS distance_m
-- FROM places
-- WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(107.6191, -6.9175), 4326)::geography, 10000)
-- ORDER BY distance_m;
--
-- 3) Top hidden gems in a city:
--
-- SELECT p.name, p.hidden_gem_score, p.rating_avg
-- FROM places p JOIN cities c ON c.id = p.city_id
-- WHERE c.name = 'Bandung' AND p.is_hidden_gem
-- ORDER BY p.hidden_gem_score DESC LIMIT 20;
