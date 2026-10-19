-- =====================================================================
-- PATHSNAP PATCH: Bandung-only scope (run AFTER pathsnap_schema.sql)
-- =====================================================================

-- 1. Boundaries: the real way to enforce "Kota Bandung only"
ALTER TABLE cities ADD COLUMN IF NOT EXISTS boundary geography(MultiPolygon, 4326);
CREATE INDEX IF NOT EXISTS idx_cities_boundary ON cities USING GIST (boundary);

-- 2. Districts (kecamatan)
CREATE TABLE districts (
    id          SERIAL PRIMARY KEY,
    city_id     INT NOT NULL REFERENCES cities(id),
    name        VARCHAR(100) NOT NULL,
    boundary    geography(MultiPolygon, 4326),     -- fill later from OSM/BPS boundary data
    UNIQUE (city_id, name)
);
CREATE INDEX idx_districts_boundary ON districts USING GIST (boundary);

ALTER TABLE places         ADD COLUMN district_id INT REFERENCES districts(id);
ALTER TABLE accommodations ADD COLUMN district_id INT REFERENCES districts(id);
CREATE INDEX idx_places_district ON places (district_id);
CREATE INDEX idx_accom_district  ON accommodations (district_id);

-- 3. Seed: Jawa Barat > Kota Bandung > 30 kecamatan
INSERT INTO provinces (name) VALUES ('Jawa Barat') ON CONFLICT DO NOTHING;

INSERT INTO cities (province_id, name, type)
SELECT id, 'Bandung', 'kota' FROM provinces WHERE name = 'Jawa Barat'
ON CONFLICT DO NOTHING;

INSERT INTO districts (city_id, name)
SELECT c.id, d
FROM cities c,
     unnest(ARRAY[
        'Andir','Antapani','Arcamanik','Astanaanyar','Babakan Ciparay',
        'Bandung Kidul','Bandung Kulon','Bandung Wetan','Batununggal','Bojongloa Kaler',
        'Bojongloa Kidul','Buahbatu','Cibeunying Kaler','Cibeunying Kidul','Cibiru',
        'Cicendo','Cidadap','Cinambo','Coblong','Gedebage',
        'Kiaracondong','Lengkong','Mandalajati','Panyileukan','Rancasari',
        'Regol','Sukajadi','Sukasari','Sumur Bandung','Ujungberung'
     ]) AS d
WHERE c.name = 'Bandung'
ON CONFLICT DO NOTHING;

-- 4. Seed categories (slugs match the friend's pipeline categories so imports join directly)
INSERT INTO categories (name, slug) VALUES
  ('Waterfall','waterfall'), ('Viewpoint','viewpoint'), ('Cave','cave'),
  ('Hot Spring','hot_spring'), ('Camp Site','camp_site'), ('Nature Reserve','nature_reserve'),
  ('Crater','crater'), ('Tea Plantation','tea_plantation'), ('Other','other'),
  ('Culinary','culinary'), ('Culture & Museum','culture'), ('Shopping','shopping')
ON CONFLICT DO NOTHING;

INSERT INTO amenities (name) VALUES
  ('WiFi'),('Pool'),('Breakfast'),('Parking'),('AC'),('Hot Water'),
  ('Restaurant'),('Kitchen'),('Family Room'),('Pet Friendly')
ON CONFLICT DO NOTHING;

-- 5. Auto-assign district once boundaries are loaded
-- UPDATE places p SET district_id = d.id
-- FROM districts d
-- WHERE p.district_id IS NULL AND d.boundary IS NOT NULL AND ST_Covers(d.boundary, p.location);
