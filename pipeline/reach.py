"""Reach index precompute. Spec §10.3.

Generates, once, the public-transport journey time from every London postcode
district to every role location, and inverts it into a lookup the browser can use
with no network call:

    {"E8": {"30": ["manna-society-kitchen-volunteer", ...], "45": [...], "60": [...]}}

Why precompute rather than call an isochrone API at runtime: no API key, no rate
limit, no per-request cost, works offline, and it keeps the site entirely static —
which is assumption A4, and the same reasoning that removed the runtime matcher in
spec v0.2. A few hundred KB gzipped for the whole of London.

This is a one-off. Rerun annually, or when the role set changes materially.

    # 1. Get the graph inputs (once, ~1GB, not committed)
    python pipeline/reach.py --fetch-inputs

    # 2. Build the OTP graph (needs Java 17+, ~10 min, ~8GB RAM)
    python pipeline/reach.py --build-graph

    # 3. Start OTP, then compute
    python pipeline/reach.py --serve          # leave running
    python pipeline/reach.py --compute        # in another shell

Step 3 makes roughly (districts x locations) requests against your own local
server. Nothing leaves your machine and no charity site is touched.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from config import DATA, ORGS_DIR, ROOT

OTP_DIR = ROOT / ".otp"
OTP_JAR = OTP_DIR / "otp-shaded.jar"
REACH_OUT = DATA / "reach-index.json"
DISTRICTS = DATA / "postcode-districts.json"

BANDS = [30, 45, 60]          # minutes
DEPART = "2026-10-14T09:00"   # a normal Wednesday morning, off-peak-ish

# Inputs. Both are open data; neither is committed to the repo.
INPUTS = {
    "greater-london.osm.pbf":
        "https://download.geofabrik.de/europe/united-kingdom/england/"
        "greater-london-latest.osm.pbf",
    "tfl-gtfs.zip":
        # TfL publish a GTFS feed via their open data portal. Check the current
        # URL before running — it has moved before.
        "https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/london/",
}


def fetch_inputs() -> int:
    OTP_DIR.mkdir(exist_ok=True)
    print("Downloading graph inputs. ~1GB, once.\n")
    for name, url in INPUTS.items():
        dest = OTP_DIR / name
        if dest.exists():
            print(f"  have {name}")
            continue
        print(f"  {name} <- {url}")
        subprocess.run(["curl", "-fL", "--progress-bar", "-o", str(dest), url],
                       check=True)
    if not OTP_JAR.exists():
        print("\nNow download the OTP 2.x shaded jar from "
              "https://repo1.maven.org/maven2/org/opentripplanner/otp/")
        print(f"and save it as {OTP_JAR}")
        return 1
    return 0


def build_graph() -> int:
    if not OTP_JAR.exists():
        print(f"Missing {OTP_JAR}. Run --fetch-inputs first.")
        return 2
    print("Building OTP graph. Ten minutes or so, and it wants ~8GB.\n")
    subprocess.run(["java", "-Xmx8G", "-jar", str(OTP_JAR),
                    "--build", "--save", str(OTP_DIR)], check=True)
    return 0


def serve() -> int:
    print("OTP on http://localhost:8080 — leave this running.\n")
    subprocess.run(["java", "-Xmx8G", "-jar", str(OTP_JAR),
                    "--load", str(OTP_DIR), "--serve"], check=True)
    return 0


# --------------------------------------------------------------------- compute

QUERY = """
{ plan(from: {lat: %f, lon: %f}, to: {lat: %f, lon: %f},
       date: "%s", time: "%s", transportModes: [{mode: TRANSIT}, {mode: WALK}],
       numItineraries: 1) { itineraries { duration } } }
"""


def journey_minutes(client, a: tuple, b: tuple) -> int | None:
    date, time = DEPART.split("T")
    r = client.post("http://localhost:8080/otp/routers/default/index/graphql",
                    json={"query": QUERY % (a[0], a[1], b[0], b[1], date, time)},
                    timeout=30)
    its = (r.json().get("data", {}).get("plan", {}) or {}).get("itineraries", [])
    return round(its[0]["duration"] / 60) if its else None


def load_locations() -> dict[str, tuple[float, float]]:
    """Role id -> coordinates. Only roles with real coordinates take part."""
    out = {}
    for f in sorted(ORGS_DIR.glob("*.json")):
        for o in json.loads(f.read_text(encoding="utf-8"))["opportunities"]:
            if o.get("coords") and o.get("location_type") in ("in_person", "hybrid"):
                out[o["id"]] = tuple(o["coords"])
    return out


def compute() -> int:
    import httpx

    if not DISTRICTS.exists():
        print(f"Missing {DISTRICTS}.\n"
              "It should map each London postcode district to a centroid:\n"
              '  {"E8": [51.5450, -0.0553], "SE1": [51.5010, -0.0900], ...}\n'
              "Derive it from OS Open Names or the ONS postcode directory — both "
              "are open data. The site also needs this file to resolve a typed "
              "postcode client-side without a server (spec §13).")
        return 2

    districts = json.loads(DISTRICTS.read_text(encoding="utf-8"))
    locations = load_locations()
    if not locations:
        print("No roles have coordinates yet.\n"
              "Reach is blocked on data, not on this script. Roles need `coords` "
              "populated — geocode `postcode_district` at minimum, ideally the "
              "venue address. Until then the site should keep offering boroughs.")
        return 1

    print(f"{len(districts)} districts x {len(locations)} locations "
          f"= {len(districts) * len(locations):,} journeys. This takes a while.\n")

    index: dict[str, dict[str, list[str]]] = {}
    with httpx.Client() as client:
        for i, (code, dc) in enumerate(sorted(districts.items()), 1):
            bands = {str(b): [] for b in BANDS}
            for rid, rc in locations.items():
                mins = journey_minutes(client, tuple(dc), rc)
                if mins is None:
                    continue
                for b in BANDS:
                    if mins <= b:
                        bands[str(b)].append(rid)
            index[code] = bands
            print(f"  [{i:>3}/{len(districts)}] {code:<5} "
                  + "  ".join(f"{b}m:{len(bands[str(b)]):>3}" for b in BANDS))

    REACH_OUT.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    size = REACH_OUT.stat().st_size
    print(f"\nWrote {REACH_OUT.relative_to(ROOT)} — {size / 1024:.0f} KB "
          f"({size / 1024 / 4:.0f} KB gzipped, roughly)")
    print("The site can now filter by travel time with no network call.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    for flag in ("fetch-inputs", "build-graph", "serve", "compute"):
        ap.add_argument(f"--{flag}", action="store_true")
    a = ap.parse_args()
    if a.fetch_inputs:
        return fetch_inputs()
    if a.build_graph:
        return build_graph()
    if a.serve:
        return serve()
    if a.compute:
        return compute()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
