import csv
import io
import json
import math
import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).resolve().parent
DB = ROOT / "fire_intelligence.db"
STATIC = ROOT / "static"
DATA = ROOT / "data"
STATIC.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

FACILITIES = [
    {"name": "Demo Petrochemical Complex", "type": "refinery", "latitude": 13.115, "longitude": 80.300},
    {"name": "Demo Thermal Power Station", "type": "powerplant", "latitude": 12.950, "longitude": 80.120},
    {"name": "Demo Chemical Works", "type": "chemical", "latitude": 11.020, "longitude": 76.950},
    {"name": "Demo Steel Facility", "type": "steel", "latitude": 16.520, "longitude": 80.650},
]

app = FastAPI(title="SIH 162 Fire Source Intelligence V3", version="3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS events(
        event_id TEXT PRIMARY KEY,
        created_at TEXT,
        updated_at TEXT,
        scenario TEXT,
        data_source TEXT DEFAULT 'SIMULATION',
        latitude REAL,
        longitude REAL,
        detection_count INTEGER,
        max_frp REAL,
        mean_frp REAL,
        duration_minutes REAL,
        industrial_distance_km REAL,
        facility_type TEXT,
        landcover TEXT,
        source_class TEXT,
        source_probability REAL,
        anomaly_score REAL,
        severity REAL,
        urgency TEXT,
        alert_status TEXT,
        explanation TEXT
    );

    CREATE TABLE IF NOT EXISTS detections(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT,
        timestamp TEXT,
        latitude REAL,
        longitude REAL,
        frp REAL,
        bright_ti4 REAL,
        confidence REAL,
        satellite TEXT,
        scenario TEXT,
        data_source TEXT DEFAULT 'SIMULATION'
    );

    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT,
        label TEXT,
        comment TEXT,
        created_at TEXT
    );
    """)

    # Migration for an existing database created by the old version.
    for table, column, definition in [
        ("events", "data_source", "TEXT DEFAULT 'SIMULATION'"),
        ("detections", "data_source", "TEXT DEFAULT 'SIMULATION'"),
    ]:
        cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    c.commit()
    c.close()


def hav(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest(lat, lon):
    return min(
        ((f, hav(lat, lon, f["latitude"], f["longitude"])) for f in FACILITIES),
        key=lambda x: x[1],
    )


def cluster(rows, distance_km=1.5, minutes=180):
    left = list(rows)
    groups = []

    while left:
        seed = left.pop(0)
        group = [seed]
        queue = [seed]

        while queue:
            cur = queue.pop(0)
            found = []

            for d in left:
                dist = hav(cur["latitude"], cur["longitude"], d["latitude"], d["longitude"])
                t1 = datetime.fromisoformat(cur["timestamp"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
                gap = abs((t2 - t1).total_seconds()) / 60

                if dist <= distance_km and gap <= minutes:
                    found.append(d)

            for d in found:
                left.remove(d)
                group.append(d)
                queue.append(d)

        groups.append(group)

    return groups


def classify(f):
    industrial = 0

    if f["industrial_distance_km"] <= 0.5:
        industrial += 35
    elif f["industrial_distance_km"] <= 2:
        industrial += 25
    elif f["industrial_distance_km"] <= 5:
        industrial += 10

    if f["persistence"] >= 8:
        industrial += 25
    elif f["persistence"] >= 4:
        industrial += 15
    else:
        industrial += 5

    if f["frp"] >= 100:
        industrial += 25
    elif f["frp"] >= 40:
        industrial += 15
    else:
        industrial += 5

    if f["landcover"] == "industrial":
        industrial += 15

    if f["night"]:
        industrial += 5

    industrial = min(100, industrial)
    industrial_prob = industrial / 100

    spread = 5
    if f["landcover"] in ("forest", "grassland"):
        spread += 30
    if f["wind"] >= 25:
        spread += 20
    elif f["wind"] >= 12:
        spread += 10
    if f["humidity"] <= 30:
        spread += 20
    elif f["humidity"] <= 50:
        spread += 10
    if f["persistence"] >= 6:
        spread += 15
    if f["frp"] >= 80:
        spread += 15
    spread = min(100, spread)

    severity = max(
        0,
        min(
            100,
            0.45 * min(f["frp"], 200) / 2
            + 0.25 * min(f["persistence"] * 10, 100)
            + 0.15 * min(f["duration"] / 3, 100)
            + 0.15 * spread,
        ),
    )

    anomaly = max(
        0,
        min(100, 0.6 * min(f["frp"] / 2, 100) + 0.4 * min(f["persistence"] * 10, 100)),
    )

    if industrial_prob >= 0.70:
        source = "industrial_fire"
        probability = industrial_prob
    elif f["landcover"] == "cropland":
        source = "crop_burn"
        probability = max(0.55, 1 - industrial_prob)
    elif f["landcover"] in ("forest", "grassland"):
        source = "wildfire"
        probability = max(0.55, 1 - industrial_prob)
    else:
        source = "other_thermal"
        probability = max(0.50, 1 - industrial_prob)

    urgency = (
        "CRITICAL" if severity >= 80
        else "HIGH" if severity >= 60
        else "MEDIUM" if severity >= 35
        else "LOW"
    )

    reasons = []
    if f["industrial_distance_km"] <= 2:
        reasons.append("near industrial infrastructure")
    if f["persistence"] >= 6:
        reasons.append("persistent repeated detections")
    if f["frp"] >= 100:
        reasons.append("very high FRP")
    elif f["frp"] >= 40:
        reasons.append("elevated FRP")
    if f["night"]:
        reasons.append("nighttime activity")
    if f["landcover"] == "industrial":
        reasons.append("industrial land-cover context")
    if spread >= 60:
        reasons.append("elevated spread/weather risk")

    return {
        "source_class": source,
        "source_probability": round(probability, 3),
        "anomaly_score": round(anomaly, 1),
        "severity": round(severity, 1),
        "urgency": urgency,
        "spread_risk": round(spread, 1),
        "explanation": reasons or ["limited contextual evidence"],
    }


CENTERS = {
    "industrial": (13.115, 80.300, "industrial"),
    "wildfire": (11.850, 78.550, "forest"),
    "crop_burn": (11.100, 79.100, "cropland"),
}


def generate(scenario, n=8, seed=1):
    rng = random.Random(seed)
    lat, lon, land = CENTERS[scenario]
    lat += rng.uniform(-0.03, 0.03)
    lon += rng.uniform(-0.03, 0.03)
    start = datetime.now(timezone.utc)
    rows = []

    for i in range(n):
        spread = i * (0.0015 if scenario == "wildfire" else 0.0004)

        if scenario == "industrial":
            frp = rng.uniform(60, 180)
        elif scenario == "wildfire":
            frp = 25 + i * 12 + rng.uniform(-8, 12)
        else:
            frp = rng.uniform(15, 70)

        rows.append({
            "timestamp": (start + timedelta(minutes=i * 25)).isoformat(),
            "latitude": lat + rng.uniform(-0.001, 0.001) + spread,
            "longitude": lon + rng.uniform(-0.001, 0.001) + spread,
            "frp": max(1, frp),
            "bright_ti4": rng.uniform(310, 390),
            "confidence": rng.uniform(60, 100),
            "satellite": "SIM-VIIRS",
            "scenario": scenario,
        })

    return rows


def process(rows, data_source="SIMULATION"):
    results = []
    c = db()

    for group in cluster(rows):
        eid = "EV-" + uuid.uuid4().hex[:8].upper()
        lat = sum(x["latitude"] for x in group) / len(group)
        lon = sum(x["longitude"] for x in group) / len(group)

        facility, dist = nearest(lat, lon)

        scenario = group[0].get("scenario", "unknown")
        land = {
            "industrial": "industrial",
            "wildfire": "forest",
            "crop_burn": "cropland",
        }.get(scenario, "unknown")

        # Real FIRMS observations don't contain land-cover/weather here.
        if data_source == "NASA_FIRMS":
            land = "unknown"

        weather = {
            "industrial": (10, 45),
            "wildfire": (28, 28),
            "crop_burn": (8, 55),
        }.get(scenario, (10, 45))

        times = [
            datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00"))
            for x in group
        ]
        duration = (
            (max(times) - min(times)).total_seconds() / 60
            if len(group) > 1 else 0
        )

        f = {
            "frp": max(x["frp"] for x in group),
            "persistence": len(group),
            "industrial_distance_km": dist,
            "landcover": land,
            "wind": weather[0],
            "humidity": weather[1],
            "duration": duration,
            "night": int(any(t.hour < 6 or t.hour >= 18 for t in times)),
        }

        r = classify(f)

        c.execute(
            """INSERT INTO events(
                event_id,created_at,updated_at,scenario,data_source,
                latitude,longitude,detection_count,max_frp,mean_frp,
                duration_minutes,industrial_distance_km,facility_type,
                landcover,source_class,source_probability,anomaly_score,
                severity,urgency,alert_status,explanation
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                eid,
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                scenario,
                data_source,
                lat,
                lon,
                len(group),
                f["frp"],
                sum(x["frp"] for x in group) / len(group),
                duration,
                dist,
                facility["type"],
                land,
                r["source_class"],
                r["source_probability"],
                r["anomaly_score"],
                r["severity"],
                r["urgency"],
                "NEW",
                "; ".join(r["explanation"]),
            ),
        )

        for d in group:
            c.execute(
                """INSERT INTO detections(
                    event_id,timestamp,latitude,longitude,frp,bright_ti4,
                    confidence,satellite,scenario,data_source
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    eid,
                    d["timestamp"],
                    d["latitude"],
                    d["longitude"],
                    d["frp"],
                    d.get("bright_ti4", 0),
                    d.get("confidence", 0),
                    d.get("satellite", ""),
                    d.get("scenario", "unknown"),
                    data_source,
                ),
            )

        results.append({
            "event_id": eid,
            "scenario": scenario,
            "data_source": data_source,
            "latitude": lat,
            "longitude": lon,
            "detection_count": len(group),
            "max_frp": f["frp"],
            "industrial_distance_km": round(dist, 3),
            **r,
        })

    c.commit()
    c.close()
    return results


def firms_to_rows(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []

    for x in reader:
        try:
            lat = float(x["latitude"])
            lon = float(x["longitude"])
            frp = float(x.get("frp") or 0)
            bt = float(x.get("bright_ti4") or 0)
            conf_raw = str(x.get("confidence", "")).lower()

            if conf_raw in ("h", "high"):
                confidence = 90
            elif conf_raw in ("n", "nominal"):
                confidence = 60
            elif conf_raw in ("l", "low"):
                confidence = 30
            else:
                confidence = float(conf_raw) if conf_raw.replace(".", "", 1).isdigit() else 50

            date = x.get("acq_date", "")
            time_raw = str(x.get("acq_time", "")).zfill(4)
            hh = int(time_raw[:2] or 0)
            mm = int(time_raw[2:] or 0)
            timestamp = datetime.fromisoformat(
                f"{date}T{hh:02d}:{mm:02d}:00+00:00"
            ).isoformat()

            rows.append({
                "timestamp": timestamp,
                "latitude": lat,
                "longitude": lon,
                "frp": frp,
                "bright_ti4": bt,
                "confidence": confidence,
                "satellite": x.get("satellite", "VIIRS"),
                "scenario": "firms",
            })
        except Exception:
            continue

    return rows


class SimulationRequest(BaseModel):
    scenario: str = Field("mixed", pattern="^(industrial|wildfire|crop_burn|mixed)$")
    events: int = Field(8, ge=1, le=100)
    detections_per_event: int = Field(8, ge=2, le=30)


class Verification(BaseModel):
    label: str = Field(pattern="^(confirmed|rejected|uncertain)$")
    comment: str = ""


class FirmsRequest(BaseModel):
    source: str = "VIIRS_NOAA20_NRT"
    days: int = Field(1, ge=1, le=10)
    area: str = "68,6,97,36"


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {"project": "SIH 162 Fire Source Intelligence V3", "status": "online"}


@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC / "dashboard.html")


@app.get("/events")
def events(limit: int = 500):
    c = db()
    rows = c.execute(
        "SELECT * FROM events ORDER BY updated_at DESC LIMIT ?",
        (min(limit, 1000),),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


@app.get("/events/{eid}")
def event(eid: str):
    c = db()
    e = c.execute("SELECT * FROM events WHERE event_id=?", (eid,)).fetchone()
    ds = c.execute(
        "SELECT * FROM detections WHERE event_id=? ORDER BY timestamp",
        (eid,),
    ).fetchall()
    c.close()

    if not e:
        raise HTTPException(404, "Event not found")

    x = dict(e)
    x["detections"] = [dict(d) for d in ds]
    return x


@app.post("/simulate")
def simulate(req: SimulationRequest):
    out = []

    for i in range(req.events):
        scenario = (
            ["industrial", "wildfire", "crop_burn"][i % 3]
            if req.scenario == "mixed"
            else req.scenario
        )
        out += process(
            generate(scenario, req.detections_per_event, 1000 + i),
            "SIMULATION",
        )

    return {"created": len(out), "events": out}


@app.post("/firms/fetch")
def firms_fetch(req: FirmsRequest):
    key = os.getenv("FIRMS_MAP_KEY") or os.getenv("MAP_KEY")

    if not key:
        raise HTTPException(
            500,
            "FIRMS_MAP_KEY is missing from .env",
        )

    url = f"{FIRMS_URL}/{key}/{req.source}/{req.area}/{req.days}"

    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"NASA FIRMS request failed: {e}")

    rows = firms_to_rows(response.text)

    if not rows:
        return {
            "source": "NASA_FIRMS",
            "detections": 0,
            "created_events": 0,
            "message": "NASA returned no usable detections for this area/time window.",
        }

    # Store the raw response for reproducibility.
    (DATA / "raw_firms.csv").write_text(response.text, encoding="utf-8")

    events_created = process(rows, "NASA_FIRMS")

    return {
        "source": "NASA_FIRMS",
        "detections": len(rows),
        "created_events": len(events_created),
        "source_satellite": req.source,
        "area": req.area,
        "days": req.days,
    }


@app.post("/simulation/reset")
def reset():
    c = db()
    c.execute("DELETE FROM events")
    c.execute("DELETE FROM detections")
    c.execute("DELETE FROM feedback")
    c.commit()
    c.close()
    return {"status": "cleared"}


@app.post("/events/{eid}/verify")
def verify(eid: str, v: Verification):
    c = db()

    if not c.execute(
        "SELECT 1 FROM events WHERE event_id=?", (eid,)
    ).fetchone():
        c.close()
        raise HTTPException(404, "Event not found")

    c.execute(
        "INSERT INTO feedback(event_id,label,comment,created_at) VALUES (?,?,?,datetime('now'))",
        (eid, v.label, v.comment),
    )
    c.execute(
        "UPDATE events SET alert_status=? WHERE event_id=?",
        (v.label.upper(), eid),
    )
    c.commit()
    c.close()

    return {"event_id": eid, "status": v.label}
