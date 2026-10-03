"""Step 2: turn raw OSM items into rows in places / accommodations (with de-duplication)."""
import re
from config import DEDUP_RADIUS_M, DEDUP_NAME_SIMILARITY
from db import connect, bandung_city_id, Json

ACCOM_TOURISM = {
    "hotel": "hotel", "guest_house": "guesthouse", "hostel": "hostel", "motel": "other",
    "apartment": "apartment", "chalet": "villa", "camp_site": "campground",
}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:120] or "place"


def get_point(el):
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else (None, None)


def accommodation_type(tags):
    name = tags.get("name", "").lower()
    t = ACCOM_TOURISM.get(tags.get("tourism", ""))
    if tags.get("leisure") == "resort":
        t = "resort"
    if t is None:
        return None
    if "villa" in name:
        return "villa"
    if "homestay" in name:
        return "homestay"
    return t


def place_category(tags):
    name = tags.get("name", "").lower()
    if tags.get("natural") == "waterfall" or name.startswith("curug"):
        return "waterfall"
    if tags.get("natural") == "cave_entrance" or name.startswith(("gua ", "goa ")):
        return "cave"
    if tags.get("natural") == "hot_spring":
        return "hot_spring"
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    if tags.get("leisure") == "nature_reserve":
        return "nature_reserve"
    if tags.get("tourism") in ("museum", "gallery") or "historic" in tags:
        return "culture"
    return "other"


def build_address(tags):
    parts = [tags.get("addr:street"), tags.get("addr:housenumber"), tags.get("addr:city")]
    return ", ".join(p for p in parts if p) or None


def is_duplicate(cur, table, name, lat, lon):
    cur.execute(
        f"""SELECT 1 FROM {table}
            WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
              AND similarity(lower(name), lower(%s)) > %s LIMIT 1""",
        (lon, lat, DEDUP_RADIUS_M, name, DEDUP_NAME_SIMILARITY),
    )
    return cur.fetchone() is not None


def main():
    conn = connect()
    cur = conn.cursor()
    city_id = bandung_city_id(cur)
    cur.execute("""SELECT id, raw_payload FROM raw_scraped_items
                   WHERE status = 'pending' AND raw_payload->>'_source' = 'overpass_osm'""")
    rows = cur.fetchall()
    counts = {"place": 0, "accommodation": 0, "duplicate": 0, "skipped": 0}

    for raw_id, el in rows:
        tags = el.get("tags", {})
        lat, lon = get_point(el)
        name = tags.get("name")
        if not name or lat is None:
            cur.execute("UPDATE raw_scraped_items SET status='rejected' WHERE id=%s", (raw_id,))
            counts["skipped"] += 1
            continue

        osm_ref = f"{el['type']}/{el['id']}"
        slug = f"{slugify(name)}-{el['type'][0]}{el['id']}"
        phone = tags.get("phone") or tags.get("contact:phone")
        website = tags.get("website") or tags.get("contact:website")
        address = build_address(tags)
        acc_type = accommodation_type(tags)

        if acc_type:
            table = "accommodations"
            if is_duplicate(cur, table, name, lat, lon):
                cur.execute("UPDATE raw_scraped_items SET status='duplicate' WHERE id=%s", (raw_id,))
                counts["duplicate"] += 1
                continue
            stars = tags.get("stars", "")
            star = int(stars[0]) if stars[:1].isdigit() and 1 <= int(stars[0]) <= 5 else None
            rooms = int(tags["rooms"]) if tags.get("rooms", "").isdigit() else None
            cur.execute(
                """INSERT INTO accommodations
                   (slug, name, description, type, star_class, city_id, address, location,
                    total_rooms, phone, website, osm_ref)
                   VALUES (%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                           %s,%s,%s,%s)
                   ON CONFLICT (osm_ref) DO NOTHING""",
                (slug, name, tags.get("description"), acc_type, star, city_id, address,
                 lon, lat, rooms, phone, website, osm_ref),
            )
            counts["accommodation"] += 1
        else:
            table = "places"
            if is_duplicate(cur, table, name, lat, lon):
                cur.execute("UPDATE raw_scraped_items SET status='duplicate' WHERE id=%s", (raw_id,))
                counts["duplicate"] += 1
                continue
            hours = {"osm": tags["opening_hours"]} if tags.get("opening_hours") else None
            cur.execute(
                """INSERT INTO places
                   (slug, name, description, category_id, city_id, address, location,
                    phone, website, opening_hours, osm_ref)
                   VALUES (%s,%s,%s,(SELECT id FROM categories WHERE slug=%s),%s,%s,
                           ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,%s,%s,%s)
                   ON CONFLICT (osm_ref) DO NOTHING""",
                (slug, name, tags.get("description"), place_category(tags), city_id, address,
                 lon, lat, phone, website, Json(hours) if hours else None, osm_ref),
            )
            counts["place"] += 1
        cur.execute("UPDATE raw_scraped_items SET status='approved' WHERE id=%s", (raw_id,))

    conn.commit()
    conn.close()
    print("Promotion finished:", counts)


if __name__ == "__main__":
    main()
