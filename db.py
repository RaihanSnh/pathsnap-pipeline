"""Small database helpers shared by all steps."""

import psycopg2
import psycopg2.extras

from config import DATABASE_URL


def connect():
    conn = psycopg2.connect(DATABASE_URL)

    with conn.cursor() as cur:
        cur.execute("SET search_path TO public, gis;")

    return conn


def get_source_id(cur, name):
    cur.execute("SELECT id FROM data_sources WHERE name = %s", (name,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"data_sources has no '{name}'. Did you run init_db.py?"
        )
    return row[0]


def start_run(cur, source_name, query):
    cur.execute(
        "INSERT INTO scrape_runs (source_id, query) VALUES (%s, %s) RETURNING id",
        (get_source_id(cur, source_name), query),
    )
    return cur.fetchone()[0]


def finish_run(cur, run_id, items_found):
    cur.execute(
        "UPDATE scrape_runs SET finished_at = now(), items_found = %s WHERE id = %s",
        (items_found, run_id),
    )


def bandung_city_id(cur):
    cur.execute("SELECT id FROM cities WHERE name = 'Bandung' LIMIT 1")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("City 'Bandung' not found. Did you run init_db.py?")
    return row[0]


Json = psycopg2.extras.Json