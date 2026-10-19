"""Step B of manual enrichment: read the filled-in CSV and update the database.

    python import_filled_csv.py --table places --file places_to_fill.csv
    python import_filled_csv.py --table accommodations --file accommodations_to_fill.csv

Rules: rows are matched by `id`; only NON-EMPTY cells are written; invalid rows are skipped and reported.
"""

import argparse
import csv
import re
from config import PLACE_PRICE_LEVELS, ACCOM_PRICE_LEVELS
from db import connect

FIELDS = {
    "places": {
        "rating_avg": "rating",
        "rating_count": "int",
        "price_min": "money",
        "price_max": "money",
        "price_level": "level",
    },
    "accommodations": {
        "rating_avg": "rating",
        "rating_count": "int",
        "price_per_night_min": "money",
        "price_per_night_max": "money",
        "price_level": "level",
        "star_class": "star",
    },
}
LEVELS = {"free", "budget", "moderate", "expensive", "luxury"}


def derive_level(table, price):
    if table == "places":
        steps, top = PLACE_PRICE_LEVELS, "luxury"
        for limit, name in steps:
            if (price == 0 and name == "free") or (
                price > 0 and name != "free" and price < limit
            ):
                return name
        return top
    for limit, name in ACCOM_PRICE_LEVELS:
        if price < limit:
            return name
    return "luxury"


def parse_whole_number(raw):
    """Whole number from messy spreadsheet text.

    Accepts: 3   3.0   350000   350000.0   350.000   1.500.000   "Rp 350.000"
    (a trailing .0 / .00 is a spreadsheet float artefact; dots in groups of 3 are thousand separators).
    """
    s = re.sub(r"(?i)rp\.?|idr|\s", "", raw)
    if re.fullmatch(r"\d+[.,]0{1,2}", s):  # 3.0  350000.0  350000.00
        return int(re.split(r"[.,]", s)[0])
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):  # 350.000  1.500.000
        return int(re.sub(r"[.,]", "", s))
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"not a whole number: {raw!r}")


def parse(kind, raw):
    raw = raw.strip().replace(",", ".") if kind == "rating" else raw.strip()
    if kind in ("money", "int"):
        return parse_whole_number(raw)
    if kind == "rating":
        v = round(float(raw), 1)
        if not 0 <= v <= 5:
            raise ValueError("rating must be between 0 and 5")
        return v
    if kind == "star":
        v = parse_whole_number(raw)
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
                sets = ", ".join(
                    f"{c} = %s" + ("::price_level" if c == "price_level" else "")
                    for c in values
                )
                cur.execute(
                    f"UPDATE {args.table} SET {sets}, enriched_at = now() WHERE id = %s",
                    (*values.values(), rid),
                )
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
