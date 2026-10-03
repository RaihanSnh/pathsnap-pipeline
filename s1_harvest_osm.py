"""Step 1: download named places + accommodations inside Kota Bandung from OpenStreetMap.

Everything is stored untouched in raw_scraped_items (status = 'pending').
If every Overpass server fails we STOP with an error (no silent fake data).
"""
import hashlib
import sys
import time
import requests
from config import OVERPASS_ENDPOINTS, USER_AGENT
from db import connect, start_run, finish_run, Json

QUERY = """
[out:json][timeout:180];
area["boundary"="administrative"]["admin_level"="5"]["name"~"^(Kota )?Bandung$"]->.city;
(
  nwr["natural"~"^(waterfall|cave_entrance|hot_spring)$"]["name"](area.city);
  nwr["tourism"~"^(viewpoint|attraction|museum|gallery|zoo|theme_park)$"]["name"](area.city);
  nwr["leisure"~"^(nature_reserve|park|garden|water_park|resort)$"]["name"](area.city);
  nwr["historic"]["name"](area.city);
  nwr["tourism"~"^(hotel|guest_house|hostel|motel|apartment|chalet|camp_site)$"]["name"](area.city);
);
out center tags;
"""


def fetch_overpass():
    last_error = None
    for url in OVERPASS_ENDPOINTS:
        try:
            print(f"Querying {url} (can take 1-3 minutes)...")
            r = requests.post(url, data={"data": QUERY}, headers={"User-Agent": USER_AGENT}, timeout=240)
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as e:  # try the next server
            last_error = e
            print("  failed:", e)
            time.sleep(5)
    raise RuntimeError(f"All Overpass servers failed: {last_error}")


def element_hash(el):
    return hashlib.sha256(f"osm/{el['type']}/{el['id']}".encode()).hexdigest()


def store(elements):
    conn = connect()
    cur = conn.cursor()
    run_id = start_run(cur, "overpass_osm", "Kota Bandung places + accommodations")
    new = 0
    for el in elements:
        payload = dict(el)
        payload["_source"] = "overpass_osm"
        cur.execute(
            """INSERT INTO raw_scraped_items (run_id, source_url, raw_payload, content_hash, status)
               VALUES (%s, %s, %s, %s, 'pending') ON CONFLICT (content_hash) DO NOTHING""",
            (run_id, f"https://www.openstreetmap.org/{el['type']}/{el['id']}", Json(payload), element_hash(el)),
        )
        new += cur.rowcount
    finish_run(cur, run_id, len(elements))
    conn.commit()
    conn.close()
    return new


def main():
    elements = fetch_overpass()
    if not elements:
        sys.exit("Overpass returned 0 elements - check the area name in QUERY.")
    new = store(elements)
    print(f"Harvested {len(elements)} elements, {new} were new.")


if __name__ == "__main__":
    main()
