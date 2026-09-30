import argparse
import os
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

p = argparse.ArgumentParser()
p.add_argument("--source", default="VIIRS_NOAA20_NRT")
p.add_argument("--days", type=int, default=1)
p.add_argument("--area", default="68,6,97,36")
p.add_argument("--output", default="data/raw_firms.csv")
args = p.parse_args()

key = os.getenv("FIRMS_MAP_KEY") or os.getenv("MAP_KEY")
if not key:
    raise SystemExit("Set FIRMS_MAP_KEY in .env")

url = f"{BASE}/{key}/{args.source}/{args.area}/{args.days}"
response = requests.get(url, timeout=120)
response.raise_for_status()

out = Path(args.output)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(response.content)

print(f"Saved {len(response.content):,} bytes to {out}")
