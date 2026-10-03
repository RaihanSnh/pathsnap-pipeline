"""Step B of manual enrichment: read the filled-in CSV and update the database.

    python import_filled_csv.py --table places --file places_to_fill.csv
    python import_filled_csv.py --table accommodations --file accommodations_to_fill.csv

Rules: rows are matched by `id`; only NON-EMPTY cells are written; invalid rows are skipped and reported.
"""
import argparse
import csv
from config import PLACE_PRICE_LEVELS, ACCOM_PRICE_LEVELS
from db import connect

FIELDS = {
    "places": {"rating_avg": "rating", "rating_count": "int", "price_min": "money",
               "price_max": "money", "price_level": "level"},
    "accommodations": {"rating_avg": "rating", "rating_count": "int", "price_per_night_min": "money",
                       "price_per_night_max": "money", "price_level": "level", "star_class": "star"},
}
LEVELS = {"free", "budget", "moderate", "expensive", "luxury"}


def derive_level(table, price):
    if table == "places":
        steps, top = PLACE_PRICE_LEVELS, "luxury"
        for limit, name in steps:
            if (price == 0 and name == "free") or (price > 0 and name != "free" and price < limit):
                return name
        return top
    for limit, name in ACCOM_PRICE_LEVELS:
        if price < limit:
            return name
    return "luxury"


def parse(kind, raw):
    raw = raw.strip().replace(",", ".") if kind == "rating" else raw.strip()
    if kind == "money":  # allow "25.000", "Rp 25000"
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            raise ValueError(f"not a number: {raw!r}")
        return int(digits)
    if kind == "int":
        return int(raw)
    if kind == "rating":
        v = round(float(raw), 1)
        if not 0 <= v <= 5:
            raise ValueError("rating must be between 0 and 5")
        return v
    if kind == "star":
        v = int(raw)
        if not 1 <= v <= 5:
            raise ValueError("star_class must be 1-5")
        return v
    if kind == "level":
        v = raw.lower()
        if v not in LEVELS:
            raise ValueError(f"price_level must be one of {sorted(LEVELS)}")
        return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, choices=FIELDS)
    ap.add_argument("--file", required=True)
    args = ap.parse_args()
    fields = FIELDS[args.table]
    pmin = "price_min" if args.table == "places" else "price_per_night_min"
    pmax = "price_max" if args.table == "places" else "price_per_night_max"

    conn = connect()
    cur = conn.cursor()
    ok = bad = 0
    with open(args.file, newline="", encoding="utf-8-sig") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            try:
                rid = int(row["id"])
                values = {}
                for col, kind in fields.items():
                    if (row.get(col) or "").strip():
                        values[col] = parse(kind, row[col])
                if pmin in values and pmax in values and values[pmax] < values[pmin]:
                    raise ValueError("max price is lower than min price")
                if pmin in values and "price_level" not in values:
                    values["price_level"] = derive_level(args.table, values[pmin])
                if not values:
                    continue
                sets = ", ".join(f"{c} = %s" + ("::price_level" if c == "price_level" else "") for c in values)
                cur.execute(f"UPDATE {args.table} SET {sets}, enriched_at = now() WHERE id = %s",
                            (*values.values(), rid))
                if cur.rowcount == 0:
                    raise ValueError(f"no row with id {rid}")
                ok += 1
            except (ValueError, KeyError) as e:
                bad += 1
                print(f"  line {line_no} skipped: {e}")
    conn.commit()
    conn.close()
    print(f"{args.table}: {ok} rows updated, {bad} skipped")


if __name__ == "__main__":
    main()
