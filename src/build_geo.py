"""Simplify the India boundary for the 3D map (web/public/data/india.json).

Source: datameet/maps Country/india-composite.geojson (CC BY 4.0), the
Government of India composite boundary. Douglas-Peucker simplification keeps
the outline recognisable at ~1-2% of the original size.
"""
from __future__ import annotations

import json
import math

from .config import RAW_DIR, ROOT

SRC = RAW_DIR / "geo" / "india-composite.geojson"
OUT = ROOT / "web" / "public" / "data" / "india.json"

# Home grounds (stadium coordinates) used for the 2026 home fixtures.
HOMES = {
    "CSK": ("Chennai", "MA Chidambaram Stadium", 13.0628, 80.2793),
    "DC": ("Delhi", "Arun Jaitley Stadium", 28.6379, 77.2432),
    "GT": ("Ahmedabad", "Narendra Modi Stadium", 23.0917, 72.5975),
    "KKR": ("Kolkata", "Eden Gardens", 22.5646, 88.3433),
    "LSG": ("Lucknow", "Ekana Cricket Stadium", 26.8115, 80.9466),
    "MI": ("Mumbai", "Wankhede Stadium", 18.9389, 72.8258),
    "PBKS": ("Mullanpur", "Maharaja Yadavindra Singh Stadium", 30.7680, 76.6970),
    "RR": ("Jaipur", "Sawai Mansingh Stadium", 26.8940, 75.8030),
    "RCB": ("Bengaluru", "M Chinnaswamy Stadium", 12.9788, 77.5996),
    "SRH": ("Hyderabad", "Rajiv Gandhi Intl Stadium", 17.4065, 78.5505),
}


def _perp(p, a, b) -> float:
    if a == b:
        return math.dist(p, a)
    (x, y), (x1, y1), (x2, y2) = p, a, b
    return abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / math.dist(a, b)


def simplify(pts: list, eps: float) -> list:
    """Iterative Douglas-Peucker."""
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        s, e = stack.pop()
        dmax, idx = 0.0, None
        for i in range(s + 1, e):
            d = _perp(pts[i], pts[s], pts[e])
            if d > dmax:
                dmax, idx = d, i
        if idx is not None and dmax > eps:
            keep[idx] = True
            stack += [(s, idx), (idx, e)]
    return [p for p, k in zip(pts, keep) if k]


def ring_area(r: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]))) / 2


def main(eps: float = 0.04, min_area: float = 0.02) -> None:
    gj = json.loads(SRC.read_text())
    rings = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            outer = [(round(x, 3), round(y, 3)) for x, y, *_ in poly[0]]
            if ring_area(outer) < min_area:
                continue  # drop tiny islands; keeps Andaman & Nicobar main islands
            s = simplify(outer, eps)
            if len(s) >= 4:
                rings.append(s)
    out = {"source": "datameet/maps india-composite (CC BY 4.0)", "rings": rings,
           "homes": {k: {"city": c, "ground": g, "lat": la, "lon": lo} for k, (c, g, la, lo) in HOMES.items()}}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(rings)} rings, {sum(map(len, rings))} points, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
