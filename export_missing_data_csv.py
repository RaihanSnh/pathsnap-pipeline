"""Step A of manual enrichment: export places / accommodations to CSV so the team can fill in
rating, review count and prices in a spreadsheet (Excel / Google Sheets).

    python export_missing_data_csv.py            # only rows still missing a rating or price
    python export_missing_data_csv.py --all
"""
import argparse
import csv
from db import connect

QUERIES = {
    "places": """SELECT p.id, p.osm_ref, p.name, c.slug, p.address, p.latitude, p.longitude,
                        p.rating_avg, p.rating_count, p.price_min, p.price_max, p.price_level::text
                 FROM places p LEFT JOIN categories c ON c.id = p.category_id {where} ORDER BY p.id""",
    "accommodations": """SELECT a.id, a.osm_ref, a.name, a.type::text, a.address, a.latitude, a.longitude,
                                a.rating_avg, a.rating_count, a.price_per_night_min, a.price_per_night_max,
                                a.price_level::text, a.star_class
                         FROM accommodations a {where} ORDER BY a.id""",
}
HEADERS = {
    "places": ["id", "osm_ref", "name", "category", "address", "latitude", "longitude",
               "rating_avg", "rating_count", "price_min", "price_max", "price_level", "source_note"],
    "accommodations": ["id", "osm_ref", "name", "type", "address", "latitude", "longitude",
                       "rating_avg", "rating_count", "price_per_night_min", "price_per_night_max",
                       "price_level", "star_class", "source_note"],
}
WHERE_MISSING = {"places": "WHERE p.rating_avg IS NULL OR p.price_min IS NULL",
                 "accommodations": "WHERE a.rating_avg IS NULL OR a.price_per_night_min IS NULL"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    conn = connect()
    cur = conn.cursor()
    for table in QUERIES:
        cur.execute(QUERIES[table].format(where="" if args.all else WHERE_MISSING[table]))
        rows = cur.fetchall()
        path = f"{table}_to_fill.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig opens cleanly in Excel
            w = csv.writer(f)
            w.writerow(HEADERS[table])
            for r in rows:
                w.writerow(["" if v is None else v for v in r] + [""])
        print(f"{path}: {len(rows)} rows")
    conn.close()


if __name__ == "__main__":
    main()
