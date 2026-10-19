"""Step 0: create all tables. Safe to run twice (it skips if tables already exist)."""
import os
from db import connect

SQL_FILES = ["pathsnap_schema.sql", "pathsnap_patch_bandung.sql", "pathsnap_patch_pipeline.sql"]


def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.places')")
    if cur.fetchone()[0]:
        print("Tables already exist - skipping schema. (Applying pipeline patch only.)")
        files = ["pathsnap_patch_pipeline.sql"]
    else:
        files = SQL_FILES
    here = os.path.join(os.path.dirname(__file__), "sql")
    for name in files:
        with open(os.path.join(here, name), encoding="utf-8") as f:
            cur.execute(f.read())
        print("applied", name)
    conn.commit()
    conn.close()
    print("Database ready.")


if __name__ == "__main__":
    main()
