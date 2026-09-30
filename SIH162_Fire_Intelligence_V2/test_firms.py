import os
import requests
import pandas as pd
from io import StringIO
from dotenv import load_dotenv

load_dotenv()

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY:
    raise RuntimeError("FIRMS_MAP_KEY not found in .env")

source = "VIIRS_NOAA20_NRT"
area = "68,6,97,36"
days = 1

url = (
    f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
    f"{MAP_KEY}/{source}/{area}/{days}"
)

print("Connecting to NASA FIRMS...")
print("Source:", source)
print("Area:", area)

response = requests.get(url, timeout=60)

print("HTTP Status:", response.status_code)

if response.status_code != 200:
    print("\nNASA FIRMS returned an error:")
    print(response.text)
    raise SystemExit(1)

df = pd.read_csv(StringIO(response.text))

print("\nNASA FIRMS CONNECTION SUCCESSFUL!")
print("Number of detections:", len(df))

print("\nFirst 5 detections:")
print(df.head().to_string())

print("\nAvailable columns:")
print(list(df.columns))