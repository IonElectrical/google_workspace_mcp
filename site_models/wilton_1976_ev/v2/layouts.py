"""Proposed charger layouts for the four Wilton #1976 sites, plus every measurement the
layouts are judged by. Writes layouts.json (geometry for Blender) and layouts.md (tables).

Positions are DESIGN PROPOSALS for discussion; everything reported about them is measured
from the named datasets, or labelled CALCULATED ESTIMATE with its method.

    python layouts.py --work WORK
"""

import argparse
import json
import math
import os

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import nearest_points

import frame

FT = 0.3048
ASPHALT_MAX = 0.5  # normalised lidar intensity: asphalt 0.25-0.42, grass >= 0.68 (Forest Rd cross-section)
DESIGN = {
    "stall_length_ft": 18.0,  # brief
    "stall_width_ft": 9.0,  # DESIGN ASSUMPTION (typical); confirm with Wilton site-plan rules
    "ada_van_width_ft": 8.0,  # brief: van-accessible stall with 8 ft aisle (ADA 2010 sec. 502.2 option)
    "ada_aisle_ft": 8.0,
    "pedestals": 2,  # dual-port pedestals per site (brief allows 1-5)
    "pedestal_m": [
        0.40,
        0.30,
        1.80,
    ],  # generic dual-port envelope W x D x H - DESIGN ASSUMPTION, use cut sheet
    "pad_m": [0.76, 0.61, 0.15],
    "plow_buffer_ft": 3.0,  # DESIGN ASSUMPTION: bollard / clear zone around pedestals
    "drive_aisle_ft": 24.0,  # DESIGN ASSUMPTION: two-way aisle behind 90-degree stalls
}


class Dem:
    def __init__(self, path):
        d = np.load(path)
        self.z, self.x0, self.y0, self.step = (
            d["z"].astype(float),
            float(d["x0"]),
            float(d["y0"]),
            float(d["step"]),
        )

    def at(self, x, y):
        from scipy import ndimage

        c = (np.atleast_1d(x) - self.x0) / self.step
        r = (self.y0 - np.atleast_1d(y)) / self.step
        return ndimage.map_coordinates(self.z, [r, c], order=1, mode="nearest")


def unit(theta):
    return np.array([math.cos(theta), math.sin(theta)])


def rect(c, along, across, half_len, half_w):
    c = np.asarray(c)
    pts = [
        c + along * s * half_len + across * t * half_w
        for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]
    return Polygon(pts)


def drape(dem, line, step=0.5):
    """3D polyline on the DEM, densified to `step` m; returns points and 2D/3D lengths."""
    ls = shapely.segmentize(LineString(line), step)
    xy = np.asarray(ls.coords)
    z = dem.at(xy[:, 0], xy[:, 1])
    pts = np.column_stack([xy, z])
    d2 = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
    d3 = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    return pts, d2, d3


def slope_stats(dem, poly):
    """Running and cross slope (%) across a stall/aisle polygon from the 1 m DEM (plane fit)."""
    minx, miny, maxx, maxy = poly.bounds
    gx, gy = np.meshgrid(np.arange(minx, maxx, 0.5), np.arange(miny, maxy, 0.5))
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    pts = pts[shapely.contains_xy(poly, pts[:, 0], pts[:, 1])]
    if len(pts) < 6:
        return None
    z = dem.at(pts[:, 0], pts[:, 1])
    a = np.column_stack([pts, np.ones(len(pts))])
    (gxs, gys, _), *_ = np.linalg.lstsq(a, z, rcond=None)
    return float(math.hypot(gxs, gys) * 100), float(z.max() - z.min())


def row_layout(origin, theta, kind="perpendicular"):
    """Stalls along a row axis `theta`; stall depth points to theta+90 deg.
    origin = point on the row axis at the stall heads' centre line start (ADA end)."""
    along, across = unit(theta), unit(theta + math.pi / 2)
    L = DESIGN["stall_length_ft"] * FT
    if kind == "parallel":
        # stalls in line along the curb, 8 ft (2.44 m) deep from the curb
        depth = DESIGN["ada_van_width_ft"] * FT
        seq = [
            ("ADA van stall (parallel)", L),
            (
                "ADA access aisle (in-line, PROWAG R309 - design detail)",
                DESIGN["ada_aisle_ft"] * FT,
            ),
            ("EV stall 1 (parallel)", L),
            ("EV stall 2 (parallel)", L),
            ("EV stall 3 (parallel)", L),
        ]
        items, s = [], 0.0
        for name, w in seq:
            c = np.asarray(origin) + along * (s + w / 2) - across * depth / 2
            items.append(
                {"name": name, "poly": rect(c, along, across, w / 2, depth / 2)}
            )
            s += w
        heads = [
            np.asarray(origin)
            + along * (L + DESIGN["ada_aisle_ft"] * FT + L)
            + across * 0.6,
            np.asarray(origin)
            + along * (L + DESIGN["ada_aisle_ft"] * FT + 2.5 * L)
            + across * 0.6,
        ]
        return items, heads, along, across
    seq = [
        ("ADA van stall", DESIGN["ada_van_width_ft"] * FT),
        ("ADA access aisle 8 ft", DESIGN["ada_aisle_ft"] * FT),
        ("EV stall 1", DESIGN["stall_width_ft"] * FT),
        ("EV stall 2", DESIGN["stall_width_ft"] * FT),
        ("EV stall 3", DESIGN["stall_width_ft"] * FT),
    ]
    items, s, bounds = [], 0.0, []
    for name, w in seq:
        c = np.asarray(origin) + along * (s + w / 2) - across * L / 2
        items.append({"name": name, "poly": rect(c, along, across, w / 2, L / 2)})
        bounds.append(s)
        s += w
    # dual pedestals at the stall heads: one at the head of the ADA aisle (serves ADA + EV1),
    # one on the EV2/EV3 line (serves EV2 + EV3); set 0.6 m behind the head line
    ped_s = [bounds[1] + DESIGN["ada_aisle_ft"] * FT / 2, bounds[4]]
    heads = [np.asarray(origin) + along * s_ + across * 0.6 for s_ in ped_s]
    return items, heads, along, across


def route(a, b, buildings):
    """Straight trench if clear of buildings, else an L-route around them (whichever is shorter)."""
    direct = LineString([a, b])
    if not any(direct.crosses(p) or direct.within(p) for p in buildings):
        return [tuple(a), tuple(b)]
    best = None
    for corner in ((a[0], b[1]), (b[0], a[1])):
        ln = LineString([a, corner, b])
        if not any(ln.crosses(p) for p in buildings):
            if best is None or ln.length < best.length:
                best = ln
    return list((best or direct).coords)


def nearest_on(line, pt):
    return line.interpolate(line.project(Point(pt)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    W = a.work
    dem = Dem(os.path.join(W, "dem_detail.npz"))
    B = json.load(open(os.path.join(W, "buildings_detail.json")))
    bpolys = [Polygon(b["footprint"], b["holes"]) for b in B]
    roads = json.load(open(os.path.join(W, "roads.json")))
    water = json.load(open(os.path.join(W, "water.json")))
    pts = json.load(open(os.path.join(W, "points.json")))
    flow = [(w["name"], shape(w["geom"])) for w in water["flowlines"] if w["name"]]
    areas = [shape(w["geom"]) for w in water["areas"] + water["waterbodies"]]
    water_union = shapely.union_all(areas)
    footways = shapely.union_all(
        [
            LineString(r["line"])
            for r in roads
            if r["line"] and r["class"] in ("footway", "path", "pedestrian")
        ]
    )

    def named(name):
        return shapely.union_all(
            [LineString(r["line"]) for r in roads if r["line"] and r["name"] == name]
        )

    def building_at(x, y):
        p = Point(x, y)
        return min(range(len(bpolys)), key=lambda i: bpolys[i].distance(p))

    sites = {
        s["key"]: np.array([float(v) for v in frame.local(s["lat"], s["lon"])])
        for s in frame.SITES
    }
    out = {"design": DESIGN, "sites": {}}

    # ---------------- site geometry: measured search (DESIGN PROPOSALS) ----------------
    # Candidate rows are generated every 1.5 m / 2 m and at the local building or street axes, and
    # kept only if they sit on lidar-detected asphalt, clear buildings (1 m), water and footways,
    # and stay off street centrelines. The best candidate has the flattest ADA stall + aisle
    # (DEM plane fit), then the flattest stalls, then the site preference stated in the brief.
    from PIL import Image

    det = json.load(open(os.path.join(W, "meta.json")))["detail_box"]
    inten = (
        np.asarray(Image.open(os.path.join(W, "lidar_intensity.png"))).astype(float)
        / 255
    )

    def intensity(x, y):
        c = np.clip(((np.asarray(x) - det[0]) / 0.5).astype(int), 0, inten.shape[1] - 1)
        r = np.clip(((det[3] - np.asarray(y)) / 0.5).astype(int), 0, inten.shape[0] - 1)
        return inten[r, c]

    def paved_frac(poly):
        minx, miny, maxx, maxy = poly.bounds
        gx, gy = np.meshgrid(np.arange(minx, maxx, 0.5), np.arange(miny, maxy, 0.5))
        q = np.column_stack([gx.ravel(), gy.ravel()])
        q = q[shapely.contains_xy(poly, q[:, 0], q[:, 1])]
        return (
            float(np.mean(intensity(q[:, 0], q[:, 1]) < ASPHALT_MAX)) if len(q) else 0.0
        )

    bunion = shapely.union_all(bpolys)
    streets = shapely.union_all(
        [
            LineString(r["line"])
            for r in roads
            if r["line"]
            and r["subtype"] == "road"
            and r["class"]
            not in ("footway", "path", "pedestrian", "steps", "sidewalk", "service")
        ]
    )
    for g in (bunion, water_union, footways, streets):
        shapely.prepare(g)

    def evaluate(origin, theta, kind, region=None, street_gap=4.5):
        items, heads, _, _ = row_layout(origin, theta, kind)
        polys = [it["poly"] for it in items]
        u = shapely.union_all(polys)
        if region is not None and not region.contains(u):
            return None
        if (
            bunion.distance(u) < 1.0
            or water_union.intersects(u)
            or footways.distance(u) < 1.0
        ):
            return None
        if street_gap and streets.distance(u) < street_gap:
            return None
        if paved_frac(u) < 0.85:
            return None
        sl = [slope_stats(dem, q) for q in polys]
        if any(v is None for v in sl):
            return None
        return max(sl[0][0], sl[1][0]), max(v[0] for v in sl), u

    def search(anchor, thetas, half, step, kind, region, pref, street_gap=4.5):
        best = None
        for dx in np.arange(-half, half + 1e-6, step):
            for dy in np.arange(-half, half + 1e-6, step):
                o = np.asarray(anchor) + (dx, dy)
                for th in thetas:
                    r = evaluate(o, th, kind, region, street_gap)
                    if r is None:
                        continue
                    score = 4 * r[0] + r[1] + pref(r[2])
                    if best is None or score < best[0]:
                        best = (score, o, th, r)
        return best

    def axes(poly):
        m = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:2]
        a = math.atan2(*(m[1] - m[0])[::-1])
        return [a + k * math.pi / 2 for k in range(4)]

    # S1: inside the paved lot around the police building; prefer the back (far from the riverwalk
    # footway along Stony Brook = the front) and close to the building (shorter trench)
    police_pt = next(
        s["xy"] for s in pts["structures"] if "Police" in s.get("name", "")
    )
    ib = building_at(*police_pt)
    pb = bpolys[ib]
    lots = [Polygon(c) for c in json.load(open(os.path.join(W, "parking.json")))]
    lot1 = max(lots, key=lambda q: q.intersection(pb.buffer(30)).area)
    # brief: riverwalk + benches at the FRONT (NE, along Stony Brook - the OSM footway confirms it);
    # police leave via the road BEHIND the building = the SW side toward Burns Hill Rd. Keep a
    # police-exit zone clear (building SW face to Burns Hill Rd, 3 m past each corner) and put the
    # chargers toward the back half of the lot.
    burns = named("Burns Hill Road")
    mrr1 = np.asarray(pb.minimum_rotated_rectangle.exterior.coords)[:4]
    long_edges = sorted(
        [(mrr1[i], mrr1[(i + 1) % 4]) for i in range(4)],
        key=lambda e: -np.linalg.norm(e[1] - e[0]),
    )[:2]
    sw_face = min(long_edges, key=lambda e: burns.distance(LineString(e)))
    e0, e1 = sw_face
    ed = (e1 - e0) / np.linalg.norm(e1 - e0)
    ext0, ext1 = e0 - ed * 3.0, e1 + ed * 3.0
    exit_zone = Polygon(
        [
            ext0,
            ext1,
            np.asarray(nearest_on(burns, ext1).coords[0]),
            np.asarray(nearest_on(burns, ext0).coords[0]),
        ]
    ).buffer(0)
    exit_line = LineString(
        [(e0 + e1) / 2, np.asarray(nearest_on(burns, (e0 + e1) / 2).coords[0])]
    )
    # hard rule: the back half of the lot = Burns Hill Rd side of the building's long axis
    cen1 = np.asarray(pb.centroid.coords[0])
    n_sw = np.array([-ed[1], ed[0]])
    if np.dot(n_sw, (e0 + e1) / 2 - cen1) < 0:
        n_sw = -n_sw
    back_half = Polygon(
        [
            cen1 + ed * 200,
            cen1 - ed * 200,
            cen1 - ed * 200 + n_sw * 200,
            cen1 + ed * 200 + n_sw * 200,
        ]
    )
    region1 = lot1.union(pb).buffer(0.5).difference(exit_zone).intersection(back_half)
    b1 = search(
        np.asarray(pb.centroid.coords[0]),
        axes(pb),
        30,
        1.5,
        "perpendicular",
        region1,
        lambda u: -0.06 * footways.distance(u) + 0.04 * burns.distance(u),
        street_gap=0,
    )
    # S2: near the given point on the paved area off Main St; prefer close to the point, away from the brook
    s2 = sites["S2_MainStLot"]
    sb = shapely.union_all([g for n, g in flow if n == "Stony Brook"])
    main = named("Main Street")
    q2 = nearest_on(main, s2)
    t2 = main.project(q2)
    d2 = np.asarray(main.interpolate(t2 + 3).coords[0]) - np.asarray(
        main.interpolate(t2 - 3).coords[0]
    )
    a2 = math.atan2(d2[1], d2[0])
    # brief: possible FEMA AE / floodway toward Stony Brook -> keep >= 50 ft from mapped water and
    # weight distance from the brook strongly (NFHL not available in this build)
    region2 = Point(*s2).buffer(45).difference(water_union.buffer(50 * FT))
    b2 = search(
        s2,
        [a2 + k * math.pi / 2 for k in range(4)],
        36,
        2.0,
        "perpendicular",
        region2,
        lambda u: 0.03 * u.distance(Point(*s2)) - 0.10 * sb.distance(u),
    )
    # S4: paved ground near the mill's north building (holds "Computer Haven"); prefer close to it
    ch = next(p["xy"] for p in pts["places"] if p["name"] == "Computer Haven")
    im = building_at(*ch)
    mill = bpolys[im]
    nw = max(np.asarray(mill.exterior.coords), key=lambda c: c[1] - 0.3 * c[0])
    b4 = search(
        nw,
        axes(mill),
        40,
        2.0,
        "perpendicular",
        Point(*nw).buffer(55),
        lambda u: 0.05 * mill.distance(u),
    )
    # S3: parallel stalls along the library side of the road between the library and Stony Brook
    # (OSM: Forest Road). Curb line = measured pavement edge (lidar intensity / DEM break).
    forest = named("Forest Road")
    lib = np.asarray(
        next(p["xy"] for p in pts["places"] if p["name"] == "Wilton Public Library")
    )
    t_lib = forest.project(Point(*lib))
    best3, edges3 = None, []
    for st in np.arange(t_lib - 45, t_lib + 45, 2.0):
        pa, pb3 = (
            np.asarray(forest.interpolate(st - 2).coords[0]),
            np.asarray(forest.interpolate(st + 2).coords[0]),
        )
        dvec = (pb3 - pa) / np.linalg.norm(pb3 - pa)
        nrm = np.array([dvec[1], -dvec[0]])
        if np.dot(nrm, lib - pa) < 0:
            nrm = -nrm
        c0 = np.asarray(forest.interpolate(st).coords[0])
        edge = None
        for dd in np.arange(1.0, 12.0, 0.25):
            qq = c0 + nrm * dd
            dz = abs(float(dem.at(*(qq + nrm * 0.5))[0] - dem.at(*(qq - nrm * 0.5))[0]))
            if intensity(*qq) > ASPHALT_MAX + 0.05 or dz > 0.08:
                edge = dd
                break
        if edge is None:
            continue
        edges3.append([float(st), float(edge)])
        th = math.atan2(dvec[1], dvec[0])
        if np.dot(unit(th + math.pi / 2), nrm) < 0:
            th += math.pi
        origin = (
            c0
            + nrm * (edge - 0.3)
            - unit(th)
            * ((4 * DESIGN["stall_length_ft"] + DESIGN["ada_aisle_ft"]) * FT / 2)
        )
        r = evaluate(origin, th, "parallel", None, street_gap=0)
        if r is None:
            continue
        score = 4 * r[0] + r[1] + 0.03 * r[2].distance(Point(*lib))
        if best3 is None or score < best3[0]:
            best3 = (score, origin, th, r, edge)

    plan = {}
    for key, b, kind, why in (
        (
            "S1_PoliceLot",
            b1,
            "perpendicular",
            "Inside the police lot; the flattest valid row, preferring the back (away from the riverwalk front along Stony Brook) and staying near the building.",
        ),
        (
            "S2_MainStLot",
            b2,
            "perpendicular",
            "Paved area nearest the given point off Main St (SW of the Main St / Burns Hill Rd junction), preferring distance from Stony Brook.",
        ),
        (
            "S3_Library",
            best3,
            "parallel",
            "Street-side parallel stalls on the library side of the road between the library and Stony Brook (OSM: Forest Road; brief: Main St - confirm); curb line = measured pavement edge.",
        ),
        (
            "S4_Mill",
            b4,
            "perpendicular",
            "Paved area beside the mill's north building (holds Computer Haven), near the Riverside Way / Mill St entrance.",
        ),
    ):
        if b is None:
            print(f"{key}: NO candidate met the constraints - layout not placed")
            continue
        plan[key] = dict(
            origin=b[1],
            theta=b[2],
            kind=kind,
            rationale=why,
            search={
                "ada_slope_pct": round(b[3][0], 2),
                "max_slope_pct": round(b[3][1], 2),
            },
        )
    edges_note = {"S3_Library": {"pavement_edge_offsets_m": edges3[:60]}}

    for key, cfg in plan.items():
        items, heads, along, across = row_layout(
            cfg["origin"], cfg["theta"], cfg["kind"]
        )
        allp = shapely.union_all([it["poly"] for it in items])
        c = np.asarray(allp.centroid.coords[0])
        # clearance and overlap checks
        near_b = min(bpolys, key=lambda p: p.distance(allp))
        overlap_b = sum(p.intersection(allp).area for p in bpolys)
        in_water = allp.intersection(water_union).area
        fname, fl = min(flow, key=lambda f: f[1].distance(allp))
        dflow = fl.distance(allp)
        on_flow = nearest_on(fl, c)
        z_kit = float(dem.at(*c)[0])
        # water surface near the closest channel point: lowest DEM value within 6 m (hydro-flattened)
        gx, gy = np.meshgrid(np.arange(-6, 6.5, 1.0), np.arange(-6, 6.5, 1.0))
        wz = float(np.min(dem.at(on_flow.x + gx.ravel(), on_flow.y + gy.ravel())))
        dfoot = footways.distance(allp)
        slopes = {it["name"]: slope_stats(dem, it["poly"]) for it in items}
        # power source placeholder: nearest point on the nearest building wall (UNVERIFIED)
        if (
            key == "S2_MainStLot"
        ):  # no building nearby: poles usually run along the street edge
            src = np.asarray(nearest_on(main, heads[0]).coords[0])
            src = src + (heads[0] - src) / np.linalg.norm(heads[0] - src) * 5.0
            src_note = "PLACEHOLDER at the Main St edge - pole / transformer location NOT mapped"
        else:
            src_b = near_b if key != "S3_Library" else bpolys[building_at(*lib)]
            src = np.asarray(nearest_on(src_b.exterior, heads[0]).coords[0])
            src = (
                src
                + (src - np.asarray(src_b.centroid.coords[0]))
                / np.linalg.norm(src - np.asarray(src_b.centroid.coords[0]))
                * 0.6
            )
            src_note = "PLACEHOLDER on the nearest building wall - actual transformer/service location NOT mapped"
        trenches = []
        for i, h in enumerate(heads):
            path = route(src, h, [p for p in bpolys if p.distance(Point(*h)) < 60])
            p3, d2, d3 = drape(dem, path)
            trenches.append(
                {
                    "to": f"pedestal {i + 1}",
                    "points": p3.round(3).tolist(),
                    "length_2d_ft": round(d2 / FT, 1),
                    "length_3d_ft": round(d3 / FT, 1),
                }
            )
        site = {
            "rationale": cfg["rationale"],
            "kind": cfg["kind"],
            "search": cfg["search"],
            "items": [
                {
                    "name": it["name"],
                    "poly": [
                        list(map(lambda v: round(v, 3), p))
                        for p in it["poly"].exterior.coords[:-1]
                    ],
                    "z": round(float(dem.at(*it["poly"].centroid.coords[0])[0]), 3),
                    "slope_pct": round(slopes[it["name"]][0], 2)
                    if slopes[it["name"]]
                    else None,
                    "relief_m": round(slopes[it["name"]][1], 3)
                    if slopes[it["name"]]
                    else None,
                }
                for it in items
            ],
            "pedestals": [
                {
                    "xy": [round(h[0], 3), round(h[1], 3)],
                    "z": round(float(dem.at(*h)[0]), 3),
                    "heading_deg": round(math.degrees(cfg["theta"]), 2),
                }
                for h in heads
            ],
            "power_placeholder": {
                "xy": [round(src[0], 3), round(src[1], 3)],
                "z": round(float(dem.at(*src)[0]), 3),
                "note": src_note,
            },
            "trenches": trenches,
            "measured": {
                "kit_ground_z_navd88_ft": round(z_kit / FT, 2),
                "nearest_building_clearance_ft": round(near_b.distance(allp) / FT, 1),
                "building_overlap_m2": round(overlap_b, 2),
                "water_overlap_m2": round(in_water, 2),
                "nearest_named_stream": fname,
                "distance_to_stream_centreline_ft": round(dflow / FT, 1),
                "distance_to_mapped_water_edge_ft": round(
                    water_union.distance(allp) / FT, 1
                ),
                "height_above_stream_water_surface_ft": round((z_kit - wz) / FT, 1),
                "distance_to_osm_footway_riverwalk_ft": round(dfoot / FT, 1),
                "max_slope_pct_any_stall_or_aisle": round(
                    max(s[0] for s in slopes.values() if s), 2
                ),
            },
        }
        out["sites"][key] = site

    # ---------------- site-specific overlays ----------------
    # S1: whole paved lot candidate for the 40 deeded spaces = Overture parking polygon holding the
    # police building, minus the building (deed undelineated)
    lot = None
    lot_polys = []
    for p in (
        json.load(open(os.path.join(W, "parking.json")))
        if os.path.exists(os.path.join(W, "parking.json"))
        else []
    ):
        lot_polys.append(Polygon(p))
    for lp in lot_polys:
        if lp.buffer(5).intersects(pb):
            lot = lp.union(pb).buffer(0)
    if lot is not None:
        deed = lot.difference(pb)
        out["sites"]["S1_PoliceLot"]["deed_area"] = {
            "poly": [
                list(map(lambda v: round(v, 3), c)) for c in deed.exterior.coords[:-1]
            ]
            if deed.geom_type == "Polygon"
            else [
                list(map(lambda v: round(v, 3), c))
                for c in max(deed.geoms, key=lambda g: g.area).exterior.coords[:-1]
            ],
            "area_sqft": round(deed.area / FT**2),
            "source": "Overture/OSM parking polygon minus lidar-registered building footprint",
            "label": "40 SPACES DEEDED TO WILTON FALLS BLDG - DEED UNDELINEATED (whole paved lot shown)",
        }
    # S1: police exit (brief: the road behind the building) - SW face straight to Burns Hill Rd, plus
    # the keep-clear zone the layout search excluded
    p3, d2_, _ = drape(dem, list(exit_line.coords))
    out["sites"]["S1_PoliceLot"]["police_exit"] = {
        "points": p3.round(3).tolist(),
        "length_ft": round(d2_ / FT, 1),
        "zone": [
            list(map(lambda v: round(v, 3), c)) for c in exit_zone.exterior.coords[:-1]
        ],
        "zone_area_sqft": round(exit_zone.area / FT**2),
        "note": "ASSUMED from the brief (front = riverwalk side NE, exit = road behind = SW to Burns Hill Rd). Confirm with WPD.",
    }
    out["sites"]["S1_PoliceLot"]["hazard"] = {
        "xy": [round(pb.centroid.x, 2), round(pb.centroid.y, 2)],
        "text": "REPORTED: sodium cyanide vault under a concrete cap 'adjacent to the Wilton Police Department' (Abbott Trust Lot J-104-2, EPA 2023). Exact location NOT mapped - locate before any trenching.",
    }
    # S2: distance bands toward Stony Brook (150 / 250 ft from the given point) and brook offsets
    sb = shapely.union_all([g for n, g in flow if n == "Stony Brook"])
    s2 = sites["S2_MainStLot"]
    out["sites"]["S2_MainStLot"]["bands"] = {
        "given_point_to_stony_brook_ft": round(sb.distance(Point(*s2)) / FT, 1),
        "rings_ft": [150, 250],
        "center": [round(s2[0], 2), round(s2[1], 2)],
        "note": "Brief: possible FEMA AE / floodway 150-250 ft SW toward Stony Brook. NFHL not loaded - rings are distances only.",
    }
    # S4: bridge corridor Riverside Way (mill east side) <-> Howard Street across the Souhegan
    howard = named("Howard Street")
    sou = shapely.union_all([g for n, g in flow if n == "Souhegan River"])
    mill_complex = shapely.union_all(
        [p for p in bpolys if p.distance(mill) < 40 and p.centroid.y < 10]
    )
    p_m, p_h = nearest_points(
        mill_complex.exterior
        if mill_complex.geom_type == "Polygon"
        else mill_complex.boundary,
        howard,
    )
    span = LineString([p_m, p_h])
    wet = span.intersection(water_union)
    p3, d2, d3 = drape(dem, list(span.coords))
    out["sites"]["S4_Mill"]["bridge_corridor"] = {
        "points": p3.round(3).tolist(),
        "length_ft": round(d2 / FT, 1),
        "water_width_ft": round(wet.length / FT, 1),
        "crosses_souhegan": bool(span.intersects(sou)),
        "note": "CALCULATED ESTIMATE: shortest line from the mill complex to Howard St centreline (NRPC 2025: bridge 'Riverside Way & Howard Street'). Plan A / Plan B landings TBD on site.",
    }
    # S4: dike candidate = crest of the berm around the NHD Lake/Pond west of the mill
    ponds = [shape(w["geom"]) for w in water["waterbodies"]]
    if ponds:
        pond = min(
            ponds, key=lambda g: g.distance(mill)
        )  # the NHD pond beside the mill, not the reservoirs
        pond = (
            pond
            if pond.geom_type == "Polygon"
            else max(pond.geoms, key=lambda g: g.area)
        )
        ring = shapely.segmentize(pond.exterior, 2.0)
        cpts = np.asarray(ring.coords)[:-1]
        cen = np.asarray(pond.centroid.coords[0])
        crest = []
        for p in cpts:
            n = (p - cen) / np.linalg.norm(p - cen)
            ds = np.arange(0, 14, 0.5)
            zz = dem.at(p[0] + n[0] * ds, p[1] + n[1] * ds)
            k = int(np.argmax(zz))
            crest.append([p[0] + n[0] * ds[k], p[1] + n[1] * ds[k], zz[k]])
        crest = np.asarray(crest)
        pond_z = float(
            np.median(dem.at(*np.asarray(pond.representative_point().coords[0])))
        )
        rise = crest[:, 2] - pond_z
        sel = (
            rise > 1.0
        )  # keep only where a real embankment stands above the pond surface
        out["sites"]["S4_Mill"]["dike_candidate"] = {
            "points": crest.round(3).tolist(),
            "embankment_mask": sel.tolist(),
            "pond_surface_z_ft": round(pond_z / FT, 2),
            "crest_z_ft_range": [
                round(float(crest[sel, 2].min()) / FT, 2),
                round(float(crest[sel, 2].max()) / FT, 2),
            ]
            if sel.any()
            else None,
            "crest_height_above_pond_ft_median": round(
                float(np.median(rise[sel])) / FT, 1
            )
            if sel.any()
            else None,
            "pond_area_sqft": round(pond.area / FT**2),
            "source": "NHD Lake/Pond (unnamed) + crest = highest 1 m DEM cell within 14 m outward of the pond edge",
            "label": "DIKE - CALCULATED ESTIMATE (traced from lidar DEM); confirm it is the Waterworks dike",
        }
    out["sites"]["S4_Mill"]["mill_building_index"] = int(im)
    if "S3_Library" in out["sites"]:
        out["sites"]["S3_Library"].update(edges_note["S3_Library"])
    out["sites"]["S4_Mill"]["map_point_21_mill_st"] = [
        round(v, 3) for v in sites["S4_Mill"]
    ]
    out["sites"]["S1_PoliceLot"]["police_building_index"] = int(ib)

    def tolist(o):
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        return o

    json.dump(out, open(os.path.join(W, "layouts.json"), "w"), default=tolist)
    write_md(out, os.path.join(W, "layouts.md"))
    print("layouts.json written")
    for k, s in out["sites"].items():
        print(k, s["measured"], [t["length_3d_ft"] for t in s["trenches"]])


def write_md(out, path):
    L = [
        "# Site layouts - measurements (Wilton #1976, v2)",
        "",
        "Layouts are DESIGN PROPOSALS for discussion. Measured values come from the 2019 USGS 1 m DEM (NAVD88), "
        "lidar-registered OSM footprints and NHD. Trench lengths are CALCULATED ESTIMATES: they start at a placeholder "
        "on the nearest building wall because no transformer or service location is mapped yet.",
        "",
    ]
    for k, s in out["sites"].items():
        m = s["measured"]
        L += [
            f"## {k}",
            "",
            s["rationale"],
            "",
            "| Measure | Value | Source |",
            "|---|---|---|",
            f"| Ground elevation at stalls | {m['kit_ground_z_navd88_ft']} ft NAVD88 | USGS 3DEP 1 m DEM |",
            f"| Clearance to nearest building | {m['nearest_building_clearance_ft']} ft | lidar-registered OSM footprint |",
            f"| Nearest named stream | {m['nearest_named_stream']} | NHD HR |",
            f"| Distance to stream centreline | {m['distance_to_stream_centreline_ft']} ft | NHD HR |",
            f"| Distance to mapped water edge | {m['distance_to_mapped_water_edge_ft']} ft | NHD area/waterbody |",
            f"| Height above stream water surface | {m['height_above_stream_water_surface_ft']} ft | DEM (hydro-flattened) - NOT a FEMA BFE |",
            f"| Distance to riverwalk / footway | {m['distance_to_osm_footway_riverwalk_ft']} ft | OSM footway |",
            f"| Max slope, any stall or aisle | {m['max_slope_pct_any_stall_or_aisle']} % | DEM plane fit (ADA max 2.08 %) |",
        ]
        for t in s["trenches"]:
            L.append(
                f"| Trench to {t['to']} | {t['length_3d_ft']} ft along ground ({t['length_2d_ft']} ft plan) | CALCULATED ESTIMATE from placeholder |"
            )
        for extra in (
            "deed_area",
            "police_exit",
            "bands",
            "bridge_corridor",
            "dike_candidate",
            "hazard",
        ):
            if extra in s:
                e = {
                    kk: vv
                    for kk, vv in s[extra].items()
                    if kk not in ("points", "poly", "embankment_mask")
                }
                L.append(f"| {extra} | {json.dumps(e)} | see notes |")
        L.append("")
        L += ["| Stall / aisle | Slope % | Relief m |", "|---|---|---|"]
        for it in s["items"]:
            L.append(f"| {it['name']} | {it['slope_pct']} | {it['relief_m']} |")
        L.append("")
    open(path, "w").write("\n".join(L))


if __name__ == "__main__":
    main()
