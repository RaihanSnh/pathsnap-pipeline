"""Run the whole pipeline in order:  python run_all.py [--skip-google] [--skip-ai] [--limit 50]"""
import argparse
import subprocess
import sys


def run(script, *args):
    print(f"\n=== {script} ===")
    code = subprocess.call([sys.executable, script, *args])
    if code != 0:
        sys.exit(f"{script} failed (exit code {code}). Fix the error above, then run again.")


ap = argparse.ArgumentParser()
ap.add_argument("--skip-google", action="store_true")
ap.add_argument("--skip-ai", action="store_true")
ap.add_argument("--limit", default="50")
a = ap.parse_args()

run("init_db.py")
run("s1_harvest_osm.py")
run("s2_promote_osm.py")
if not a.skip_google:
    run("s3_enrich_google.py", "--limit", a.limit)
if not a.skip_ai:
    run("s4_score_and_ai.py", "--limit", a.limit)
print("\nAll steps finished.")
