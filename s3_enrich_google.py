"""Step 3 (optional, paid): add real rating, review count, price and phone/website from Google Places.

Needs GOOGLE_PLACES_API_KEY in .env. Use --limit to control cost (default 50 records per run).
Only accepts a Google result that is within GOOGLE_MATCH_RADIUS_M of the OpenStreetMap point.
"""
import argparse
import math
import time
import requests
from config import GOOGLE_PLACES_API_KEY, GOOGLE_MATCH_RADIUS_M
from db import connect

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.location", "places.rating",
    "places.userRatingCount", "places.priceLevel", "places.priceRange",
    "places.formattedAddress", "places.websiteUri", "places.nationalPhoneNumber",
])
PRICE_LEVEL = {
    "PRICE_LEVEL_FREE": "free", "PRICE_LEVEL_INEXPENSIVE": "budget",
    "PRICE_LEVEL_MODERATE": "moderate", "PRICE_LEVEL_EXPENSIVE": "expensive",
    "PRICE_LEVEL_VERY_EXPENSIVE": "luxury",
}
TABLES = {"places": ("price_min", "price_max"), "accommodations": ("price_per_night_min", "price_per_night_max")}


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search(name, lat, lon):
    body = {
        "textQuery": f"{name} Bandung",
        "maxResultCount": 1,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 500.0}},
    }
    headers = {"X-Goog-Api-Key": GOOGLE_PLACES_API_KEY, "X-Goog-FieldMask": FIELDS}
    r = requests.post(URL, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    places = r.json().get("places", [])
    if not places:
        return None
    g = places[0]
    loc = g.get("location", {})
    if "latitude" not in loc or haversine_m(lat, lon, loc["latitude"], loc["longitude"]) > GOOGLE_MATCH_RADIUS_M:
        return None
    return g


def parse_price_range(g):
    pr = g.get("priceRange")
    if not pr:
        return None, None
    lo, hi = pr.get("startPrice", {}), pr.get("endPrice", {})
    if lo.get("currencyCode") != "IDR":
        return None, None
    to_int = lambda m: int(m["units"]) if m and str(m.get("units", "")).isdigit() else None
    return to_int(lo), to_int(hi)


def enrich(table, limit):
    pmin, pmax = TABLES[table]
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT id, name, latitude, longitude FROM {table}
            WHERE enriched_at IS NULL OR enriched_at < now() - interval '30 days'
            ORDER BY id LIMIT %s""",
        (limit,),
    )
    matched = 0
    rows = cur.fetchall()
    for rid, name, lat, lon in rows:
        try:
            g = search(name, lat, lon)
        except requests.RequestException as e:
            print(f"  {name}: API error {e}")
            continue
        if g:
            lo, hi = parse_price_range(g)
            cur.execute(
                f"""UPDATE {table} SET
                      google_place_id = COALESCE(%s, google_place_id),
                      rating_avg = %s, rating_count = COALESCE(%s, 0),
                      price_level = COALESCE(%s::price_level, price_level),
                      {pmin} = COALESCE(%s, {pmin}), {pmax} = COALESCE(%s, {pmax}),
                      phone   = COALESCE(phone, %s), website = COALESCE(website, %s),
                      address = COALESCE(address, %s), enriched_at = now()
                    WHERE id = %s""",
                (g.get("id"), g.get("rating"), g.get("userRatingCount"),
                 PRICE_LEVEL.get(g.get("priceLevel")), lo, hi,
                 g.get("nationalPhoneNumber"), g.get("websiteUri"), g.get("formattedAddress"), rid),
            )
            matched += 1
        else:
            cur.execute(f"UPDATE {table} SET enriched_at = now() WHERE id = %s", (rid,))
        conn.commit()
        time.sleep(0.1)
    conn.close()
    print(f"{table}: {matched}/{len(rows)} matched on Google")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    if not GOOGLE_PLACES_API_KEY:
        raise SystemExit("GOOGLE_PLACES_API_KEY is empty - skipping. (This step is optional.)")
    for table in TABLES:
        enrich(table, args.limit)


if __name__ == "__main__":
    main()
