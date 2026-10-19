"""Parse pathsnap_backup.sql COPY sections into venue lists, batches and agent chunks.

Batch = 100 venues (user-defined). Each batch is split into 4 agent chunks of 25.
Reads only; never touches the database. Output goes to enrich_work/.
"""
import glob
import json
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, "..", "..", "Database", "pathsnap_backup.sql")
BATCH_SIZE = 100
AGENTS_PER_BATCH = 4


def parse_copy_blocks(path):
    """Return {table: [row-dict, ...]} from the pg_dump COPY sections."""
    with open(path, "rb") as fb:
        enc = "utf-16" if fb.read(2) == b"\xff\xfe" else "utf-8-sig"
    with open(path, encoding=enc) as f:
        lines = f.read().splitlines()
    tables, i = {}, 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("COPY public."):
            header = line.strip()
            table = header.split()[1].split(".")[1]
            cols = [c.strip() for c in header[header.index("(") + 1:header.rindex(")")].split(",")]
            rows = []
            i += 1
            while i < len(lines) and lines[i] != "\\.":
                values = []
                for field in lines[i].split("\t"):
                    if field == r"\N":
                        values.append(None)
                    else:
                        values.append(field.replace(r"\t", "\t").replace(r"\n", "\n").replace(r"\r", "\r").replace("\\\\", "\\"))
                rows.append(dict(zip(cols, values)))
                i += 1
            tables[table] = rows
        i += 1
    return tables


def point_from_hex(hexstr):
    """Decode PostGIS geography Point WKB hex -> (lat, lon)."""
    b = bytes.fromhex(hexstr)
    lon, lat = struct.unpack("<dd", b[9:25])
    return round(lat, 7), round(lon, 7)


def main():
    data = parse_copy_blocks(DUMP)
    cat_by_id = {r["id"]: r["slug"] for r in data["categories"]}

    venues = {"places": [], "accommodations": []}
    for r in data["places"]:
        lat, lon = point_from_hex(r["location"])
        venues["places"].append({
            "id": int(r["id"]), "name": r["name"], "category": cat_by_id.get(r["category_id"]),
            "address": r["address"], "latitude": lat, "longitude": lon,
            "phone": r["phone"], "website": r["website"], "osm_ref": r["osm_ref"],
        })
    for r in data["accommodations"]:
        lat, lon = point_from_hex(r["location"])
        venues["accommodations"].append({
            "id": int(r["id"]), "name": r["name"], "type": r["type"],
            "address": r["address"], "latitude": lat, "longitude": lon,
            "phone": r["phone"], "website": r["website"], "osm_ref": r["osm_ref"],
            "star_class": int(r["star_class"]) if r["star_class"] else None,
        })

    for d in ("batches", "chunks", "results"):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)
    for stale in glob.glob(os.path.join(HERE, "chunks", "*.json")) + \
               glob.glob(os.path.join(HERE, "batches", "*.json")) + \
               glob.glob(os.path.join(HERE, "pilot_*.json")):
        os.remove(stale)

    summary = {}
    for table, rows in venues.items():
        with open(os.path.join(HERE, f"venues_{table}.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        batch_files, agent_files = [], []
        for bn, start in enumerate(range(0, len(rows), BATCH_SIZE), start=1):
            batch = rows[start:start + BATCH_SIZE]
            with open(os.path.join(HERE, "batches", f"{table}_b{bn:02d}.json"), "w", encoding="utf-8") as f:
                json.dump(batch, f, ensure_ascii=False, indent=1)
            batch_files.append(f"{table}_b{bn:02d}.json")
            step = -(-len(batch) // AGENTS_PER_BATCH)  # ceil
            for an, astart in enumerate(range(0, len(batch), step), start=1):
                chunk = batch[astart:astart + step]
                name = f"{table}_b{bn:02d}_a{an}.json"
                with open(os.path.join(HERE, "chunks", name), "w", encoding="utf-8") as f:
                    json.dump(chunk, f, ensure_ascii=False, indent=1)
                agent_files.append(f"{name} ({len(chunk)})")
        summary[table] = {"total": len(rows), "batches": batch_files, "agents": agent_files}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
