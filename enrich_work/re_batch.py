"""Re-cut venues into 100-venue batches, each split into 3 parallel agent parts."""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = 100
PARTS = 3

manifest = {}
for table in ("places", "accommodations"):
    rows = json.load(open(os.path.join(HERE, f"venues_{table}.json"), encoding="utf-8"))
    for b, start in enumerate(range(0, len(rows), BATCH), start=1):
        files = []
        batch_rows = rows[start:start + BATCH]
        size = math.ceil(len(batch_rows) / PARTS)
        for p, ps in enumerate(range(0, len(batch_rows), size), start=1):
            name = f"{table}_B{b:02d}_p{p}.json"
            with open(os.path.join(HERE, "chunks", name), "w", encoding="utf-8") as f:
                json.dump(batch_rows[ps:ps + size], f, ensure_ascii=False, indent=1)
            files.append({"file": name, "venues": len(batch_rows[ps:ps + size])})
        manifest[f"{table} B{b:02d}"] = {"venues": len(batch_rows), "parts": files}
json.dump(manifest, open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8"), indent=1)
for k, v in manifest.items():
    print(k, v["venues"], "->", ", ".join(f'{p["file"]} ({p["venues"]})' for p in v["parts"]))
