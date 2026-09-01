"""Build the geographic borough map from ONS boundary data.

    python site/tools/build_map.py            # uses the cached download
    python site/tools/build_map.py --fetch    # re-download the source

Writes data/london-map.json — projected SVG paths, label anchors and a Thames
centreline — which site/build.py reads. The output is committed so the site build
needs no network access, and this script only runs when the boundaries change.

Source: Greater London borough boundaries, derived from ONS / Ordnance Survey
administrative geography and mirrored on GitHub. All UK administrative boundaries
originate as Crown copyright material under the Open Government Licence and the OS
OpenData Licence, which require both of these wherever the data is shown:

    Contains National Statistics data (c) Crown copyright and database right
    Contains Ordnance Survey data (c) Crown copyright and database right

The site prints them under the map. They are not optional.

Why this file rather than the ONS Local Authority District release: the Thames.
The LAD boundaries exclude the tidal river inconsistently — Tower Bridge and
Westminster fall outside every borough while Greenwich, Woolwich and Putney fall
inside one — so neither the shared boundary nor the gap yields a whole river. In
this file the boroughs meet along the middle of the channel for its full length,
so the seam between the north-bank and south-bank boroughs *is* the Thames, at
exactly the precision of the shapes it has to line up with. Roughly 1,800 shared
vertices from lon -0.393 to +0.210. A separate river dataset would be a second set
of rounding errors and would not sit on the banks.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / ".cache" / "london_boroughs.geojson"
OUT = ROOT / "data" / "london-map.json"
SOURCE = ("https://raw.githubusercontent.com/radoi90/housequest-data/master/"
          "london_boroughs.geojson")

WIDTH = 1000          # SVG user units; height follows from London's aspect ratio
PAD = 6
# ~89m. The map renders around 700px wide across roughly 60km of London, so one
# pixel is about 86m — at this tolerance the simplification error is under a pixel
# and invisible, while the payload drops from 53KB to 27KB.
TOLERANCE = 0.0005

# The river gets finer treatment than the boroughs. Its sinuosity is its whole
# character, it is the line a reader studies, and it is one path rather than 33.
# Measured rather than guessed: at 0.0005 the worst deviation from the full
# geometry is 34m (0.6px); at 0.0003 it is 20m (0.3px), for about 2KB more.
RIVER_TOLERANCE = 0.0003

BOROUGHS = [
    "City of London", "Westminster", "Kensington and Chelsea",
    "Hammersmith and Fulham", "Wandsworth", "Lambeth", "Southwark",
    "Tower Hamlets", "Hackney", "Islington", "Camden", "Brent", "Ealing",
    "Hounslow", "Richmond upon Thames", "Kingston upon Thames", "Merton",
    "Sutton", "Croydon", "Bromley", "Lewisham", "Greenwich", "Bexley",
    "Havering", "Barking and Dagenham", "Redbridge", "Newham",
    "Waltham Forest", "Haringey", "Enfield", "Barnet", "Harrow", "Hillingdon",
]

# Which bank each riverside borough sits on. Used only to find the shared seam.
NORTH = {"Hammersmith and Fulham", "Kensington and Chelsea", "Westminster",
         "City of London", "Tower Hamlets", "Newham", "Barking and Dagenham",
         "Havering", "Hillingdon", "Hounslow"}
SOUTH = {"Richmond upon Thames", "Wandsworth", "Lambeth", "Southwark",
         "Lewisham", "Greenwich", "Bexley", "Kingston upon Thames"}

# Plates carry a short label; the full name goes to assistive tech.
SHORT = {"Hammersmith and Fulham": "Hammersmith",
         "Kensington and Chelsea": "Kensington",
         "Barking and Dagenham": "Barking",
         "Richmond upon Thames": "Richmond",
         "Kingston upon Thames": "Kingston",
         "City of London": "City",
         "Waltham Forest": "Waltham F.",
         "Tower Hamlets": "Tower Hamlets"}


# ------------------------------------------------------------------ geometry

def rings(geom):
    """Every exterior ring, whatever the geometry type."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def _dp(pts, tol):
    """Douglas-Peucker on an open line."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy) or 1e-12
    worst, at = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs(dy * (px - ax) - dx * (py - ay)) / norm
        if d > worst:
            worst, at = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return _dp(pts[:at + 1], tol)[:-1] + _dp(pts[at:], tol)


def simplify(ring, tol):
    """Douglas-Peucker on a *closed* ring.

    Applying it to the ring directly collapses the whole thing to two points: the
    first and last vertex of a closed ring are identical, so the baseline has zero
    length, every perpendicular distance computes as zero, and the algorithm
    concludes the borough is a straight line. Split the ring at its two most
    distant vertices first and simplify each arc as an open line.
    """
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring[:]
    if len(pts) < 4:
        return ring
    a = pts[0]
    far = max(range(len(pts)),
              key=lambda i: (pts[i][0] - a[0]) ** 2 + (pts[i][1] - a[1]) ** 2)
    first = _dp(pts[:far + 1], tol)
    second = _dp(pts[far:] + [pts[0]], tol)
    out = first[:-1] + second
    return out if len(out) >= 4 else ring


def load(fetch=False):
    if fetch or not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetching {SOURCE}")
        subprocess.run(["curl", "-fL", "--progress-bar", "-o", str(CACHE), SOURCE],
                       check=True)
    doc = json.loads(CACHE.read_text(encoding="utf-8"))
    out = {}
    for f in doc["features"]:
        n = f["properties"].get("name") or f["properties"].get("LAD13NM")
        if n in BOROUGHS:
            out[n] = rings(f["geometry"])
    missing = [b for b in BOROUGHS if b not in out]
    if missing:
        raise SystemExit(f"boundaries missing for: {missing}")
    return out


# ------------------------------------------------------------------ the Thames

def thames(shapes, decimals=6):
    """The seam between the banks, chained into an ordered line.

    Point-based ordering was the wrong algorithm. Collecting the shared vertices
    and walking them nearest-neighbour got 85 of 1,818 points before stalling:
    where three boroughs meet the vertices cluster, and a greedy walk falls into
    the cluster and cannot get out.

    Shared *edges* are exact. For every consecutive vertex pair on a north-bank
    borough, check whether the same pair — in either direction — appears on a
    south-bank borough. Those edges are the channel. Chaining them by endpoint
    needs no distance threshold and cannot cut a corner, because adjacency is a
    fact about the data rather than a guess about the shape.
    """
    def edges(names):
        out = set()
        for n in names:
            for ring in shapes[n]:
                r = [(round(x, decimals), round(y, decimals)) for x, y in ring]
                for a, b in zip(r, r[1:]):
                    if a != b:
                        out.add((a, b) if a <= b else (b, a))
        return out

    shared = edges(NORTH & set(shapes)) & edges(SOUTH & set(shapes))
    if len(shared) < 200:
        raise SystemExit(f"only {len(shared)} shared river edges — the banks are "
                         "not meeting, so this file excludes the channel")

    # Adjacency on endpoints. Everything below is sorted, because the first
    # version walked a dict built from a set: iteration order varied between runs
    # and the river came out as two long reaches once and as a fistful of
    # fragments the next time, from identical input. A build that is not
    # reproducible is not a build.
    adj = {}
    for a, b in sorted(shared):
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    for k in adj:
        adj[k].sort()

    used = set()

    def walk(start):
        run, cur = [start], start
        while True:
            nxt = next((q for q in adj[cur]
                        if (min(cur, q), max(cur, q)) not in used), None)
            if nxt is None:
                return run
            used.add((min(cur, nxt), max(cur, nxt)))
            run.append(nxt)
            cur = nxt

    # Ends first, so a reach is traced end to end rather than from its middle.
    ends = sorted(p for p in adj if len(adj[p]) == 1)
    runs = []
    for start in ends + sorted(adj):
        if all((min(start, q), max(start, q)) in used for q in adj[start]):
            continue
        r = walk(start)
        if len(r) > 1:
            runs.append(r)

    # A junction — three boroughs meeting at the water — ends one walk and starts
    # another, so a single reach arrives as several runs. Stitch any whose ends
    # coincide back together.
    merged = True
    while merged:
        merged = False
        for i in range(len(runs)):
            for j in range(len(runs)):
                if i == j:
                    continue
                a, b = runs[i], runs[j]
                if a[-1] == b[0]:
                    runs[i] = a + b[1:]
                elif a[-1] == b[-1]:
                    runs[i] = a + b[::-1][1:]
                elif a[0] == b[-1]:
                    runs[i] = b + a[1:]
                elif a[0] == b[0]:
                    runs[i] = b[::-1] + a[1:]
                else:
                    continue
                runs.pop(j)
                merged = True
                break
            if merged:
                break

    runs.sort(key=len, reverse=True)
    return runs


# ------------------------------------------------------------------ projection

def build(fetch=False):
    shapes = load(fetch)
    river = thames(shapes)

    lons = [x for rs in shapes.values() for r in rs for x, y in r]
    lats = [y for rs in shapes.values() for r in rs for x, y in r]
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    midlat = math.radians((lat0 + lat1) / 2)

    # Equirectangular with longitude squeezed by cos(latitude). Over 60km of
    # London the difference from a proper Mercator is far under a pixel, and it
    # keeps the output readable.
    kx = math.cos(midlat)
    span_x = (lon1 - lon0) * kx
    span_y = lat1 - lat0
    scale = (WIDTH - 2 * PAD) / span_x
    height = round(span_y * scale + 2 * PAD, 1)

    def proj(x, y):
        return (round(PAD + (x - lon0) * kx * scale, 1),
                round(PAD + (lat1 - y) * scale, 1))   # SVG y grows downward

    def path(rs):
        out = []
        for ring in rs:
            s = simplify(ring, TOLERANCE)
            if len(s) < 3:
                continue
            pts = [proj(*p) for p in s]
            out.append("M" + " ".join(f"{x},{y}" for x, y in pts) + "Z")
        return "".join(out)

    def anchor(rs):
        """Label anchor: centroid of the largest ring, by shoelace area."""
        big = max(rs, key=lambda r: abs(sum(
            r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
            for i in range(len(r) - 1))))
        a = cx = cy = 0.0
        for i in range(len(big) - 1):
            x0, y0 = big[i]
            x1, y1 = big[i + 1]
            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        if a == 0:
            return proj(*big[0])
        return proj(cx / (3 * a), cy / (3 * a))

    boroughs = []
    for name in BOROUGHS:
        rs = shapes[name]
        ax, ay = anchor(rs)
        boroughs.append({
            "name": name,
            "short": SHORT.get(name, name),
            "d": path(rs),
            # percentages, so HTML badges can be placed over the SVG without
            # any text living inside a scaled viewBox
            "cx": round(ax / WIDTH * 100, 2),
            "cy": round(ay / height * 100, 2),
        })

    # The main channel is the longest run. Shorter runs are creek mouths and
    # boundary quirks; keeping the first few traces the estuary without the noise.
    kept = [_dp(r, RIVER_TOLERANCE) for r in river
            if len(r) >= max(12, len(river[0]) // 12)][:6]
    river_d = "".join(
        "M" + " ".join(f"{x},{y}" for x, y in (proj(*p) for p in run))
        for run in kept)
    rpts = [p for run in kept for p in run]
    doc = {
        "width": WIDTH,
        "height": height,
        "attribution": [
            "Contains National Statistics data \u00a9 Crown copyright and "
            "database right",
            "Contains Ordnance Survey data \u00a9 Crown copyright and "
            "database right",
        ],
        "source": SOURCE,
        "generated_with": {"tolerance": TOLERANCE,
                           "river_tolerance": RIVER_TOLERANCE,
                           "width": WIDTH},
        "boroughs": boroughs,
        "thames": river_d,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")

    total = sum(len(b["d"]) for b in boroughs)
    print(f"{len(boroughs)} boroughs, {WIDTH}x{height} units")
    print(f"  river: {len(kept)} reach(es), {len(rpts)} points "
          f"from {sum(len(r) for r in river)} on the shared bank seam")
    print(f"  paths: {total / 1024:.0f} KB of path data")
    print(f"  wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="re-download the source")
    build(ap.parse_args().fetch)
