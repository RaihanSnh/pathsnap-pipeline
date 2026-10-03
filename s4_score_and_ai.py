"""Step 4: find hidden-gem candidates with the rating/review-count filter, then ask Gemini to judge them.

Gemini only sees structured facts (name, category, rating, review count, OSM description).
It is told not to invent details; low-confidence answers go to a manual review queue.
"""
import argparse
import hashlib
import json
import re
import time
from config import (GEMINI_API_KEY, GEMINI_MODEL, OUTPUT_LANGUAGE, MIN_RATING, MIN_REVIEWS,
                    MAX_REVIEWS, AI_MIN_CONFIDENCE, PROMPT_VERSION)
from db import connect, start_run, finish_run, Json

PROMPT = """You are a careful travel curator for Bandung, Indonesia.
Decide whether the place below is a genuine "hidden gem": well liked, but not a crowded mainstream
tourist attraction. Use ONLY the facts given. Do not invent facts. If the facts are too thin to judge,
answer with low confidence. Write all text fields in {language}.

Facts (JSON):
{facts}

Return ONLY JSON with exactly these keys:
{{"is_hidden_gem": true/false, "confidence": 0.0-1.0, "reason": "one short sentence",
  "editorial_summary": "two sentences, based only on the facts",
  "vibe": ["up to 3 short keywords"], "best_time": "string or null",
  "insider_tip": "string or null", "tourist_trap_risk": "low|medium|high"}}"""


def math_score(rating, count):
    """Friend's formula: rating (45%) + how few reviews (55%), clamped to 0..1."""
    rating_factor = (float(rating) - 4.0) / 1.0
    obscurity = max(0.0, (MAX_REVIEWS - count) / MAX_REVIEWS)
    return round(max(0.0, min(1.0, rating_factor * 0.45 + obscurity * 0.55)), 3)


def call_gemini(client, facts):
    prompt = PROMPT.format(language=OUTPUT_LANGUAGE, facts=json.dumps(facts, ensure_ascii=False))
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            text = re.sub(r"^```(?:json)?|```$", "", resp.text.strip(), flags=re.M).strip()
            return json.loads(text)
        except Exception as e:
            print(f"    Gemini attempt {attempt + 1} failed: {e}")
            time.sleep(3 * (attempt + 1))
    return None


def process(table, kind, client, run_id, limit):
    conn = connect()
    cur = conn.cursor()
    type_col = "type::text" if table == "accommodations" else "(SELECT slug FROM categories c WHERE c.id = category_id)"
    cur.execute(
        f"""SELECT id, name, description, {type_col}, rating_avg, rating_count, latitude, longitude
            FROM {table}
            WHERE rating_avg >= %s AND rating_count >= %s AND rating_count < %s
            ORDER BY id LIMIT %s""",
        (MIN_RATING, MIN_REVIEWS, MAX_REVIEWS, limit),
    )
    done = 0
    for rid, name, desc, cat, rating, count, lat, lon in cur.fetchall():
        facts = {"name": name, "kind": kind, "category": cat, "rating": float(rating),
                 "review_count": count, "osm_description": desc, "latitude": lat, "longitude": lon}
        chash = hashlib.sha256(f"{kind}/{rid}/{PROMPT_VERSION}".encode()).hexdigest()
        cur.execute("SELECT 1 FROM raw_scraped_items WHERE content_hash = %s", (chash,))
        if cur.fetchone():
            continue  # already judged with this prompt version

        result = call_gemini(client, facts)
        if result is None:
            continue
        try:
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        score = math_score(rating, count)
        is_gem = bool(result.get("is_hidden_gem")) and confidence >= AI_MIN_CONFIDENCE
        needs_review = confidence < AI_MIN_CONFIDENCE

        cur.execute(
            """INSERT INTO raw_scraped_items (run_id, raw_payload, content_hash, status)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (run_id, Json(facts), chash, "needs_review" if needs_review else "approved"),
        )
        raw_id = cur.fetchone()[0]
        cur.execute(
            f"""INSERT INTO ai_extractions
                (raw_item_id, model_name, prompt_version, extracted_kind, extracted_data,
                 hidden_gem_score, hidden_gem_reason, confidence, needs_review, promoted_{kind}_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (raw_id, GEMINI_MODEL, PROMPT_VERSION, kind, Json(result), score,
             result.get("reason"), confidence, needs_review, rid),
        )
        cur.execute(
            f"UPDATE {table} SET is_hidden_gem=%s, hidden_gem_score=%s, hidden_gem_reason=%s WHERE id=%s",
            (is_gem, score, result.get("reason"), rid),
        )
        if kind == "place":
            for tag in (result.get("vibe") or [])[:3]:
                tag = str(tag).strip().lower()[:60]
                if tag:
                    cur.execute("INSERT INTO tags (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (tag,))
                    cur.execute("""INSERT INTO place_tags (place_id, tag_id)
                                   SELECT %s, id FROM tags WHERE name = %s ON CONFLICT DO NOTHING""", (rid, tag))
        conn.commit()
        done += 1
        print(f"  {name}: gem={is_gem} confidence={confidence:.2f}")
        time.sleep(0.5)
    finish_run(cur, run_id, done)
    conn.commit()
    conn.close()
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY is empty - skipping. (This step is optional.)")
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    for table, kind in (("places", "place"), ("accommodations", "accommodation")):
        conn = connect()
        cur = conn.cursor()
        run_id = start_run(cur, "gemini_scoring", f"score {table}")
        conn.commit()
        conn.close()
        print(f"{table}: {process(table, kind, client, run_id, args.limit)} judged")


if __name__ == "__main__":
    main()
