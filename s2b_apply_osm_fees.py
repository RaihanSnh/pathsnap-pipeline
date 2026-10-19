"""Optional: mark places as free when OpenStreetMap says fee=no. Safe to re-run."""
from db import connect

SQL = """
UPDATE places p SET price_min = 0, price_max = 0, price_level = 'free'
FROM raw_scraped_items r
WHERE r.content_hash = encode(sha256(('osm/' || p.osm_ref)::bytea), 'hex')
  AND r.raw_payload->'tags'->>'fee' = 'no'
  AND p.price_min IS NULL
"""

if __name__ == "__main__":
    conn = connect()
    cur = conn.cursor()
    cur.execute(SQL)
    print(f"{cur.rowcount} places marked free (fee=no in OpenStreetMap)")
    conn.commit()
    conn.close()
