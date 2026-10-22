"""MHT #1988 analysis: rooftop unit candidates, roof heights, roof-edge distances, riser heights,
electrical-room placeholders, route-length check and crane staging. Replaces Wilton's layouts.py
for this job (no EV layouts).

    python hvac_routes.py --work WORK

Reads prepare_site.py outputs (lidar_detail.npz, dem_detail.npz, buildings_detail.json,
roads.json, areas.json) and writes WORK/analysis.json and WORK/ROUTE_LENGTHS.md.

Method (every number is MEASURED from the 2019 lidar / DEM, or a CALCULATED ESTIMATE whose
method is written next to it):
  * DSM: highest lidar return per 0.25 m cell, gaps filled from the nearest cell.
  * Roof surface: grey opening of the DSM (6.25 m window) inside the terminal footprint and the
    bridge corridor; equipment = cells 0.8-6 m above that surface, grouped into blobs.
  * Unit candidates: blobs whose size fits a packaged unit (config ANALYSIS["unit_detect"]).
    The lidar cannot read tags, so tags are only attached where the bid package location
    leaves one candidate; otherwise the candidates are numbered and the tag stays open.
  * Grade: median DEM in a 1.5-4 m band outside the terminal footprint.
  * Riser height = roof surface at the unit minus the room floor. Ground-floor rooms: floor =
    grade (slab on grade assumed, CALCULATED ESTIMATE). Bridge room #204: floor not visible
    to lidar; only an upper bound is given.
  * Roof-edge distance = plan distance from the unit outline to the nearest DSM cell more than
    1.5 m below the unit's roof (a drop edge), and to the nearest cell more than 1.5 m above
    it (a wall / higher roof).
"""

import argparse
import json
import math
import os
import sys

import numpy as np
import shapely
import shapely.ops
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frame  # noqa: E402

FT = 0.3048
RES = 0.25


def ft(m, nd=1):
    return round(float(m) / FT, nd)


class Dem:
    def __init__(self, path):
        d = np.load(path)
        self.z, self.x0, self.y0, self.st = (
            d["z"].astype(float),
            float(d["x0"]),
            float(d["y0"]),
            float(d["step"]),
        )

    def at(self, x, y):
        c = (np.atleast_1d(x) - self.x0) / self.st
        r = (self.y0 - np.atleast_1d(y)) / self.st
        return ndimage.map_coordinates(self.z, [r, c], order=1, mode="nearest")


def build_dsm(work, box):
    d = np.load(os.path.join(work, "lidar_detail.npz"))
    p = d["p"]
    x0, y0, x1, y1 = box
    m = (p[:, 0] > x0) & (p[:, 0] < x1) & (p[:, 1] > y0) & (p[:, 1] < y1)
    q = p[m]
    nx, ny = int((x1 - x0) / RES), int((y1 - y0) / RES)
    c = ((q[:, 0] - x0) / RES).astype(int)
    r = ((y1 - q[:, 1]) / RES).astype(int)
    k = (c >= 0) & (c < nx) & (r >= 0) & (r < ny)
    c, r, q = c[k], r[k], q[k]
    z = np.full((ny, nx), np.nan)
    o = np.argsort(q[:, 2])
    z[r[o], c[o]] = q[o, 2]
    holes = np.isnan(z)
    cover = 1.0 - float(holes.mean())
    idx = ndimage.distance_transform_edt(
        holes, return_distances=False, return_indices=True
    )
    z = z[tuple(idx)]
    gx = x0 + (np.arange(nx) + 0.5) * RES
    gy = y1 - (np.arange(ny) + 0.5) * RES
    return z, gx, gy, cover


def blobs(z, gx, gy, poly, ground, cfg):
    X, Y = np.meshgrid(gx, gy)
    inside = shapely.contains_xy(poly, X, Y) & (z - ground > 5.0)
    zz = np.where(inside, z, 1e4)
    base = ndimage.grey_opening(zz, size=(25, 25))
    base = np.where(inside, base, np.nan)
    dz = z - base
    mask = inside & (dz > 0.8) & (dz < 6.0)
    mask = ndimage.binary_opening(mask, iterations=1)
    lab, n = ndimage.label(mask)
    out = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        area = len(ys) * RES * RES
        if area < cfg["min_area_m2"]:
            continue
        mp = shapely.MultiPoint(np.column_stack([gx[xs], gy[ys]]))
        rr = mp.minimum_rotated_rectangle.buffer(RES / 2, join_style="mitre")
        cc = np.asarray(rr.exterior.coords)[:4]
        e1, e2 = cc[1] - cc[0], cc[2] - cc[1]
        long_e = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2
        length, width = (
            max(np.linalg.norm(e1), np.linalg.norm(e2)),
            min(np.linalg.norm(e1), np.linalg.norm(e2)),
        )
        h = float(np.nanpercentile(dz[ys, xs], 90))
        out.append(
            {
                "xy": [round(rr.centroid.x, 2), round(rr.centroid.y, 2)],
                "rect": np.round(cc, 2).tolist(),
                "L_m": round(length, 2),
                "W_m": round(width, 2),
                "H_m": round(h, 2),
                "heading_deg": round(
                    math.degrees(math.atan2(long_e[1], long_e[0])) % 180, 1
                ),
                "area_m2": round(area, 1),
                "roof_z": round(float(np.nanmedian(base[ys, xs])), 2),
            }
        )
    return out


def bridge_objects(work, A, B, width, PAD=22.0):
    """Objects on the bridge roof: DSM in the bridge frame (s along the axis, t across), roof
    = cubic fit of the along-axis profile (outliers removed), objects = 0.45-5 m above it.
    PAD extends the search past both faces to take in the bridge head-houses."""
    d = np.load(os.path.join(work, "lidar_detail.npz"))
    p = d["p"]
    u = (B - A) / np.linalg.norm(B - A)
    n = np.array([-u[1], u[0]])
    length = float(np.linalg.norm(B - A))
    q = p[:, :2] - A
    s, t = q @ u, q @ n
    m = (s > -PAD) & (s < length + PAD) & (np.abs(t) < width / 2 + 10)
    P, S, T = p[m], s[m], t[m]
    core = np.abs(T) < 3.0
    bins = np.arange(-PAD, length + PAD, 1.0)
    prof = []
    for b in bins:
        k = core & (S >= b) & (S < b + 1)
        prof.append(np.percentile(P[k, 2], 30) if k.sum() > 5 else np.nan)
    prof = np.array(prof)
    ok = ~np.isnan(prof) & (prof > np.nanmedian(prof) - 3)
    x, y = bins[ok] + 0.5, prof[ok]
    for _ in range(6):
        c = np.polyfit(x, y, 3)
        keep = np.abs(y - np.polyval(c, x)) < 0.15
        x, y = x[keep], y[keep]
    ns, nt = int((length + 2 * PAD) / RES), int((width + 20) / RES)
    ci = np.clip(((S + PAD) / RES).astype(int), 0, ns - 1)
    ti = np.clip(((T + width / 2 + 10) / RES).astype(int), 0, nt - 1)
    Z = np.full((nt, ns), np.nan)
    o = np.argsort(P[:, 2])
    Z[ti[o], ci[o]] = P[o, 2]
    sg = -PAD + (np.arange(ns) + 0.5) * RES
    tg = -width / 2 - 10 + (np.arange(nt) + 0.5) * RES
    dz = Z - np.polyval(c, sg)[None, :]
    mask = (dz > 0.45) & (dz < 5) & (np.abs(tg)[:, None] < width / 2 + 9)
    mask = ndimage.binary_closing(mask, iterations=1)
    lab, nl = ndimage.label(mask)
    out = []
    for k in range(1, nl + 1):
        ys, xs = np.nonzero(lab == k)
        area = len(ys) * RES * RES
        if area < 1.5:
            continue
        xy = A[None, :] + np.outer(sg[xs], u) + np.outer(tg[ys], n)
        rr = shapely.MultiPoint(xy).minimum_rotated_rectangle.buffer(
            RES / 2, join_style="mitre"
        )
        cc = np.asarray(rr.exterior.coords)[:4]
        e1, e2 = cc[1] - cc[0], cc[2] - cc[1]
        long_e = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2
        sc = float(sg[xs].mean())
        out.append(
            {
                "xy": [round(rr.centroid.x, 2), round(rr.centroid.y, 2)],
                "rect": np.round(cc, 2).tolist(),
                "L_m": round(max(np.linalg.norm(e1), np.linalg.norm(e2)), 2),
                "W_m": round(min(np.linalg.norm(e1), np.linalg.norm(e2)), 2),
                "H_m": round(float(np.nanpercentile(dz[ys, xs], 90)), 2),
                "heading_deg": round(
                    math.degrees(math.atan2(long_e[1], long_e[0])) % 180, 1
                ),
                "area_m2": round(area, 1),
                "roof_z": round(float(np.polyval(c, sc)), 2),
                "s_m": round(sc, 2),
                "span_t_m": round(float(tg[ys].max() - tg[ys].min()), 2),
                "beyond_deck": bool(np.abs(tg[ys]).max() > width / 2 + 0.5),
            }
        )
    return out


def edge_distances(z, gx, gy, rect, roof_z, reach=60.0):
    """Plan distance (m) from the unit outline to the nearest drop (>1.5 m lower) and wall
    (>1.5 m higher) cell of the DSM; returns (drop_m, drop_xy, wall_m, wall_xy)."""
    poly = shapely.Polygon(rect)
    c = poly.centroid
    j0 = max(0, int((c.x - reach - gx[0]) / RES))
    j1 = min(len(gx), int((c.x + reach - gx[0]) / RES))
    i0 = max(0, int((gy[0] - (c.y + reach)) / RES))
    i1 = min(len(gy), int((gy[0] - (c.y - reach)) / RES))
    sub = z[i0:i1, j0:j1]
    X, Y = np.meshgrid(gx[j0:j1], gy[i0:i1])
    inunit = shapely.contains_xy(poly.buffer(0.3), X, Y)
    res = []
    for sel in (sub < roof_z - 1.5, sub > roof_z + 1.5):
        sel = sel & ~inunit
        if not sel.any():
            res += [None, None]
            continue
        px, py = X[sel], Y[sel]
        d = shapely.distance(poly, shapely.points(px, py))
        k = int(np.argmin(d))
        res += [float(d[k]), [round(float(px[k]), 2), round(float(py[k]), 2)]]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    C = frame.load_config(a.config)
    W = a.work
    J = lambda n: json.load(open(os.path.join(W, n)))  # noqa: E731
    dem = Dem(os.path.join(W, "dem_detail.npz"))
    blds = J("buildings_detail.json")
    term_b = next(
        b for b in blds if b["name"] == C.CENTER_RESOLVE["terminal_building"]["name"]
    )
    term = shapely.Polygon(term_b["footprint"])
    garage_b = max(
        (b for b in blds if b["class"] == "parking"),
        key=lambda b: -shapely.Polygon(b["footprint"]).distance(term),
    )
    garage = shapely.Polygon(garage_b["footprint"])
    box = tuple(
        float(v)
        for v in shapely.box(*term.union(garage).bounds)
        .buffer(30, join_style="mitre")
        .bounds
    )
    z, gx, gy, cover = build_dsm(W, box)
    ucfg = C.ANALYSIS["unit_detect"]

    # ---- grade around the terminal (floor reference for ground-floor rooms)
    band = term.buffer(4.0).difference(term.buffer(1.5))
    minx, miny, maxx, maxy = band.bounds
    X, Y = np.meshgrid(np.arange(minx, maxx, 1.0), np.arange(miny, maxy, 1.0))
    mk = shapely.contains_xy(band, X, Y)
    gz = dem.at(X[mk], Y[mk])
    grade = float(np.median(gz))
    grade_p = np.percentile(gz, [5, 95]).round(2).tolist()

    # ---- pedestrian bridge: the elevated deck between garage and terminal. Its axis runs
    # between the two footprints; found as the longest connected run of DSM cells 7-14 m above
    # ground that touches both footprints.
    Xg, Yg = np.meshgrid(gx, gy)
    hag = z - dem.at(Xg.ravel(), Yg.ravel()).reshape(z.shape)
    elev = (hag > 7.0) & (hag < 14.5)
    elev &= ~shapely.contains_xy(term.buffer(-0.5), Xg, Yg)
    elev &= ~shapely.contains_xy(garage.buffer(-0.5), Xg, Yg)
    lab, n = ndimage.label(elev)
    near_t = shapely.contains_xy(term.buffer(2.0), Xg, Yg)
    near_g = shapely.contains_xy(garage.buffer(2.0), Xg, Yg)
    best = None
    for k in range(1, n + 1):
        sel = lab == k
        if (sel & near_t).any() and (sel & near_g).any():
            if best is None or sel.sum() > best[1]:
                best = (k, int(sel.sum()))
    bsel = lab == best[0]
    bpts = np.column_stack([Xg[bsel], Yg[bsel]])
    # principal axis
    mu = bpts.mean(0)
    _, _, vt = np.linalg.svd(bpts - mu, full_matrices=False)
    u = vt[0]
    tt = (bpts - mu) @ np.array([-u[1], u[0]])
    # axis endpoints = where the centre line meets the garage and terminal footprints
    far = shapely.LineString([mu - u * 400, mu + u * 400])
    ends = []
    for poly_ in (garage, term):
        hit_ = far.intersection(poly_.exterior)
        pts_ = [hit_] if hit_.geom_type == "Point" else list(getattr(hit_, "geoms", []))
        ends.append(min(pts_, key=lambda q: q.distance(shapely.Point(mu))))
    A, B = np.array(ends[0].coords[0]), np.array(ends[1].coords[0])
    width = float(np.percentile(np.abs(tt[np.abs(tt) < 9]), 97) * 2)
    bridge_axis = shapely.LineString([A, B])
    bridge_poly = bridge_axis.buffer(width / 2 + 1.0, cap_style="flat")
    bridge_len = bridge_axis.length

    # ---- the bridge as a structure (it has no OSM / Overture footprint): outline from the
    # elevated lidar cells, roof from lidar single returns; the underside is not visible, so the
    # drawn deck stops DECK_DRAW_M below the roof (drawing only, labelled as such).
    import rasterio.features
    import rasterio.transform

    tf = rasterio.transform.from_origin(gx[0] - RES / 2, gy[0] + RES / 2, RES, RES)
    clean = ndimage.binary_opening(
        ndimage.binary_closing(bsel, iterations=3), iterations=2
    )
    polys = [
        shapely.geometry.shape(g_)
        for g_, v_ in rasterio.features.shapes(
            clean.astype(np.uint8), mask=clean, transform=tf
        )
        if v_ == 1
    ]
    bpoly = max(polys, key=lambda q: q.area).simplify(0.4).buffer(0)
    if bpoly.geom_type == "MultiPolygon":
        bpoly = max(bpoly.geoms, key=lambda q: q.area)
    bpoly = shapely.Polygon(bpoly.exterior)
    import prepare_site

    lp_ = np.load(os.path.join(W, "lidar_detail.npz"))
    pp = lp_["p"]
    sel_ = (pp[:, 2] > grade + 6) & (lp_["nret"] == 1)
    sel_[sel_] = shapely.contains_xy(bpoly, pp[sel_, 0], pp[sel_, 1])
    allp, rz, faces, n_ring, holes, top, ok_ = prepare_site.roof_mesh(
        bpoly, pp[sel_], float(np.percentile(pp[sel_, 2], 5)) - 6.0
    )
    DECK_DRAW_M = 4.0
    extra = [
        {
            "id": "lidar-bridge",
            "name": "Pedestrian bridge (outline and roof from 2019 lidar; underside not measured)",
            "class": "bridge",
            "footprint": np.round(np.asarray(bpoly.exterior.coords), 3).tolist(),
            "holes": [],
            "area_m2": round(bpoly.area, 1),
            "base_z": round(float(np.percentile(rz, 2)) - DECK_DRAW_M, 3),
            "top_z": round(float(top), 3),
            "lidar_roof": bool(ok_),
            "n_roof_pts": int(sel_.sum()),
            "roof_xy": allp.round(3).tolist(),
            "roof_z": rz.round(3).tolist(),
            "roof_faces": faces,
            "n_ring": n_ring,
            "hole_rings": holes,
            "height_note": f"deck drawn {DECK_DRAW_M} m deep; underside not measured",
        }
    ]
    json.dump(extra, open(os.path.join(W, "buildings_extra.json"), "w"))

    # ---- equipment blobs
    t_obj = blobs(z, gx, gy, term, grade, ucfg)
    b_obj = bridge_objects(W, A, B, width)
    for o in t_obj:
        o["on"] = "terminal"
    for o in b_obj:
        o["on"] = "bridge"
    levels = np.round(np.array([o["roof_z"] for o in t_obj]), 1)

    # terminal roof levels by area (MEASURED) from the DSM inside the footprint
    inside = shapely.contains_xy(term, Xg, Yg)
    hist, edges = np.histogram(
        z[inside], bins=np.arange(math.floor(grade), math.floor(grade) + 25, 0.5)
    )
    roof_levels = [
        {
            "z_m": round(float(e + 0.25), 2),
            "above_grade_ft": ft(e + 0.25 - grade),
            "area_sqft": round(float(h) * RES * RES / FT**2),
        }
        for h, e in zip(hist, edges)
        if h * RES * RES > 400
    ]
    valley_z = min(lv["z_m"] for lv in roof_levels if lv["z_m"] - grade > 4.0)

    def is_unit(o, lo=(1.5, 1.0, 0.9), hi=(25.0, 8.0, 4.5)):
        return all(
            lo[i] <= v <= hi[i] for i, v in enumerate((o["L_m"], o["W_m"], o["H_m"]))
        )

    # AHU-5: on the low (valley) roof, unit-shaped, ranked by volume
    valley = [o for o in t_obj if abs(o["roof_z"] - valley_z) < 0.6 and is_unit(o)]
    valley.sort(key=lambda o: -(o["L_m"] * o["W_m"] * o["H_m"]))
    # bridge: arches span the deck (narrow, longer than 70 % of the width); wings reach past
    # the deck edge; units are what is left with a packaged-unit size
    arches = [o for o in b_obj if o["W_m"] < 2.2 and o["span_t_m"] > 0.7 * width]
    wings = [o for o in b_obj if o["beyond_deck"] and o not in arches]
    b_units = [
        o
        for o in b_obj
        if o not in arches
        and o not in wings
        and is_unit(o, (1.8, 1.2, 0.9), (7.5, 4.6, 2.6))
    ]
    roads = J("roads.json")
    airport_rd = [
        shapely.LineString(r["line"])
        for r in roads
        if r.get("name") == "Airport Road" and r["line"]
    ]
    ar = shapely.union_all(airport_rd)
    for o in b_units:
        o["to_airport_rd_m"] = round(shapely.Point(o["xy"]).distance(ar), 2)
        o["s_along_bridge_m"] = o["s_m"]
    b_units.sort(key=lambda o: o["s_along_bridge_m"])
    rtu5 = min(b_units, key=lambda o: o["to_airport_rd_m"])
    others = [o for o in b_units if o is not rtu5]

    # ---- road under the bridge (for clearance bound and RTU-5 closure)
    road_under = None
    for r in roads:
        if r.get("name") == "Airport Road" and r["line"]:
            ln = shapely.LineString(r["line"])
            if ln.intersects(bridge_axis):
                road_under = ln
    if road_under is None:
        road_under = min(
            airport_rd, key=lambda ln: ln.distance(shapely.Point(rtu5["xy"]))
        )
    cross = road_under.intersection(bridge_axis)
    cross = (
        cross
        if cross.geom_type == "Point"
        else road_under.interpolate(road_under.project(shapely.Point(rtu5["xy"])))
    )
    road_z = float(dem.at(cross.x, cross.y)[0])
    i = int((gy[0] - cross.y) / RES)
    j = int((cross.x - gx[0]) / RES)
    win = z[max(0, i - 8) : i + 8, max(0, j - 8) : j + 8]
    bridge_roof_at_cross = float(np.percentile(win, 30))

    units = []

    def unit_rec(tag, o, conf, note, room=None, tons=None):
        drop, drop_xy, wall, wall_xy = edge_distances(z, gx, gy, o["rect"], o["roof_z"])
        rec = {
            "tag": tag,
            "confidence": conf,
            "note": note,
            "room": room,
            "tons": tons,
            "xy": o["xy"],
            "rect": o["rect"],
            "heading_deg": o["heading_deg"],
            "size_ft": [ft(o["L_m"]), ft(o["W_m"]), ft(o["H_m"])],
            "roof_z_m": o["roof_z"],
            "roof_navd88_ft": ft(o["roof_z"]),
            "roof_above_grade_ft": ft(o["roof_z"] - grade),
            "top_above_grade_ft": ft(o["roof_z"] + o["H_m"] - grade),
            "edge_drop_ft": ft(drop) if drop is not None else None,
            "edge_drop_xy": drop_xy,
            "wall_ft": ft(wall) if wall is not None else None,
            "wall_xy": wall_xy,
            "on": o["on"],
        }
        lat, lon = frame.geodetic(o["xy"][0], o["xy"][1])
        rec["lat"], rec["lon"] = round(float(lat), 6), round(float(lon), 6)
        return rec

    units.append(
        unit_rec(
            "AHU-5",
            valley[0],
            "LIDAR CANDIDATE (largest packaged-unit-shaped object on the low roof); confirm on site",
            "Tag not readable from lidar. Alternate candidates on the same roof level are listed.",
            "erm_1077",
            184,
        )
    )
    alt = [
        unit_rec(f"AHU-5 alt {k}", o, "alternate", "", "erm_1077", None)
        for k, o in enumerate(valley[1:4], start=1)
    ]
    units.append(
        unit_rec(
            "RTU-5",
            rtu5,
            "LIDAR CANDIDATE (unit-shaped object on the bridge nearest Airport Road); confirm on site",
            "The bid package puts RTU-5 on the bridge roof over the terminal curb roadway.",
            "erm_103",
            12.5,
        )
    )
    tags = getattr(C, "BRIDGE_UNIT_TAGS", {})
    for k, o in enumerate(others, start=1):
        t = tags.get(f"B{k}")
        if t:
            rec = unit_rec(
                t["tag"],
                o,
                f"LIDAR CANDIDATE B{k}, TAGGED BY POSITION AND SIZE ({t['basis']}); "
                "nameplate not read",
                "Numbered from the garage end. RTU-1 (6 t) and RTU-2 (20 t) feed from #105 (M3); "
                "RTU-3 and RTU-4 (20 t) from #204 (M2).",
                t["room"],
                t["tons"],
            )
        else:
            rec = unit_rec(
                f"Bridge unit B{k}",
                o,
                "LIDAR CANDIDATE for one of RTU-1 to RTU-4; tag not known",
                "Numbered from the garage end. RTU-1 (6 t) and RTU-2 (20 t) feed from #105 (M3); "
                "RTU-3 and RTU-4 (20 t) from #204 (M2).",
                None,
                None,
            )
        rec["cand"] = f"B{k}"
        units.append(rec)

    # ---- bridge facts
    bridge = {
        "axis": [np.round(A, 2).tolist(), np.round(B, 2).tolist()],
        "length_ft": ft(bridge_len),
        "deck_width_ft": ft(width),
        "road_under": "Airport Road",
        "road_z_m": round(road_z, 2),
        "roof_over_road_z_m": round(bridge_roof_at_cross, 2),
        "roof_above_road_ft": ft(bridge_roof_at_cross - road_z),
        "lidar_cover_pct": None,
        "arches": len(arches),
        "arch_spacing_ft": ft(
            np.median(
                np.diff(
                    sorted(bridge_axis.project(shapely.Point(o["xy"])) for o in arches)
                )
            )
        )
        if len(arches) > 2
        else None,
        "cross_wings": [o["xy"] for o in wings],
        "outline": [np.round(np.asarray(bridge_poly.exterior.coords), 2).tolist()],
    }
    # profile of bridge roof (30th pct of DSM in 2 m bins along the axis, |t| < 2 m)
    sp = (bpts - A) @ u
    tp = (bpts - A) @ np.array([-u[1], u[0]])
    zb = z[bsel]
    prof = []
    for s_ in np.arange(0, bridge_len, 2.0):
        k = (sp >= s_) & (sp < s_ + 2) & (np.abs(tp) < 2.0)
        if k.sum() > 10:
            prof.append(
                [round(float(s_ + 1), 1), round(float(np.percentile(zb[k], 30)), 2)]
            )
    pz = np.array([p_[1] for p_ in prof])
    bridge["roof_z_range_m"] = [
        round(float(np.percentile(pz, 5)), 2),
        round(float(np.percentile(pz, 95)), 2),
    ]
    bridge["roof_rise_ft"] = ft(np.percentile(pz, 95) - np.percentile(pz, 5))
    bridge["profile"] = prof
    # lidar coverage on the deck (black EPDM returns few points)
    lp = np.load(os.path.join(W, "lidar_detail.npz"))["p"]
    mm = shapely.contains_xy(bridge_poly, lp[:, 0], lp[:, 1]) & (lp[:, 2] > grade + 7)
    bridge["lidar_pts_per_m2_on_roof"] = round(float(mm.sum()) / bridge_poly.area, 1)
    bridge["lidar_cover_pct"] = round(100 * cover, 1)

    # ---- electrical room placeholders: interior, NOT located. Drawn in a labelled row on the
    # landside lawn so nobody reads them as positions.
    rooms = {}
    row0 = np.array(term.centroid.coords[0]) + np.array([-60.0, 40.0])
    for k, (key, rm) in enumerate(C.ROOMS.items()):
        xy = row0 + np.array([k * 9.0, 0.0])
        rooms[key] = {
            **rm,
            "xy": np.round(xy, 2).tolist(),
            "status": "PLACEHOLDER: interior location not in public data",
            "floor_z_m": round(grade, 2) if rm["floor"] == "ground" else None,
        }

    # ---- routes
    est = C.ESTIMATE_ASSUMED_FT
    routes = []
    for f in C.FEEDERS:
        u_ = next((x for x in units if x["tag"] == f["unit"]), None)
        rm = rooms[f["room"]]
        r = {"unit": f["unit"], "room": f["room"], "room_label": rm["label"], **f}
        if f["room"] == "erm_204":
            cand = [x for x in units if "cand" in x]
            roof = [x["roof_z_m"] for x in cand]
            r["unit_located"] = (
                "NOT SEEN in the 2019 lidar (mid-bridge per the airport); riser bound from "
                "the bridge-roof units " + ", ".join(x["tag"] for x in cand)
            )
            r["riser_ft"] = None
            r["riser_bound_ft"] = ft(max(roof) - road_z - 14.5 * FT)
            r["riser_method"] = (
                "Room #204 floor is not visible to lidar. Upper bound = bridge roof (lidar) minus "
                "(Airport Road surface + 14.5 ft minimum vertical clearance over a roadway). "
                "Real value is less: the deck structure is not subtracted."
            )
        else:
            if u_ is None:
                cand = [x for x in units if "cand" in x]
                roof = [x["roof_z_m"] for x in cand]
                r["unit_located"] = "one of " + ", ".join(x["tag"] for x in cand)
                lo, hi = min(roof) - grade, max(roof) - grade
                r["riser_ft"] = [ft(lo), ft(hi)]
            else:
                r["unit_located"] = (
                    u_["tag"] + " (" + u_["confidence"].split(" (")[0] + ")"
                )
                r["riser_ft"] = ft(u_["roof_z_m"] - grade)
            r["riser_method"] = (
                "Roof surface at the unit (2019 lidar, measured) minus ground-floor slab, taken as "
                f"grade = median DEM around the terminal ({grade:.2f} m NAVD88). Slab-at-grade is "
                "an assumption; panel and roof-curb heights not included."
            )
        r["roof_run_ft"] = None
        r["roof_run_method"] = (
            "Roof penetration point not located (no public data); 0 ft if it is under the unit."
        )
        r["horizontal_ft"] = None
        r["horizontal_method"] = "Room location is interior and not in public data."
        r["assumed_total_ft"] = est.get(f["room"])
        rv = r["riser_ft"]
        rv_hi = rv[1] if isinstance(rv, list) else rv
        if rv_hi is not None and r["assumed_total_ft"]:
            r["left_for_horizontal_and_roof_ft"] = round(
                r["assumed_total_ft"] - rv_hi, 1
            )
        elif r["assumed_total_ft"]:
            r["left_for_horizontal_and_roof_ft"] = round(
                r["assumed_total_ft"] - r["riser_bound_ft"], 1
            )
        # plan sanity bound: farthest point of the room's building from the unit, Manhattan
        bld = term if C.ROOMS[f["room"]]["building"] == "terminal" else bridge_poly
        uxy = (
            u_["xy"]
            if u_
            else (
                np.mean(
                    [x["xy"] for x in units if "cand" in x],
                    axis=0,
                )
            ).tolist()
        )
        ring = np.asarray(bld.exterior.coords)
        man = np.abs(ring[:, 0] - uxy[0]) + np.abs(ring[:, 1] - uxy[1])
        eu = np.hypot(ring[:, 0] - uxy[0], ring[:, 1] - uxy[1])
        r["plan_max_euclid_ft"] = ft(eu.max(), 0)
        r["plan_max_manhattan_ft"] = ft(man.max(), 0)
        routes.append(r)

    # ---- crane staging: AHU-5 (daylight, ramp). Pad on the apron, on the perpendicular from
    # the unit to the nearest airside facade, 10 m out from the face, clear of lidar objects.
    ahu = units[0]
    areas = J("areas.json")
    apron = shapely.union_all(
        [shapely.geometry.shape(x["geom"]) for x in areas if x["class"] == "apron"]
    )
    p_u = shapely.Point(ahu["xy"])
    apron_near = apron.intersection(p_u.buffer(150))
    # direction: from the unit to the nearest apron point
    q_ = (
        shapely.ops.nearest_points(p_u, apron_near)[1]
        if not apron_near.is_empty
        else None
    )
    crane = None
    if q_ is not None:
        d_ = np.array([q_.x - p_u.x, q_.y - p_u.y])
        d_ = d_ / np.linalg.norm(d_)
        hit = None
        for t_ in np.arange(0, 120, 0.5):
            pt = p_u.coords[0] + d_ * t_
            if not term.contains(shapely.Point(pt)):
                hit = pt
                break
        best_pad = None
        for off in np.arange(8.0, 30.0, 1.0):
            for lat_ in (0.0, 4.0, -4.0, 8.0, -8.0, 12.0, -12.0):
                c_ = hit + d_ * off + np.array([-d_[1], d_[0]]) * lat_
                pad = shapely.Point(c_).buffer(5.5, cap_style="square")
                if not apron.contains(shapely.Point(c_)) or pad.intersects(
                    term.buffer(1.0)
                ):
                    continue
                Xs, Ys = np.meshgrid(
                    np.arange(c_[0] - 6, c_[0] + 6, 0.5),
                    np.arange(c_[1] - 6, c_[1] + 6, 0.5),
                )
                ii = ((gy[0] - Ys) / RES).astype(int)
                jj = ((Xs - gx[0]) / RES).astype(int)
                okk = (ii >= 0) & (ii < len(gy)) & (jj >= 0) & (jj < len(gx))
                zz_ = z[ii[okk], jj[okk]] - dem.at(Xs[okk], Ys[okk])
                if np.percentile(zz_, 99) < 1.0:
                    best_pad = c_
                    break
            if best_pad is not None:
                break
        if best_pad is not None:
            radius = shapely.Point(best_pad).distance(p_u)
            far = max(
                shapely.Point(best_pad).distance(shapely.Point(c)) for c in ahu["rect"]
            )
            crane = {
                "pad_xy": np.round(best_pad, 2).tolist(),
                "pad_size_ft": [ft(11.0, 0), ft(11.0, 0)],
                "pad_ring": np.round(
                    np.asarray(
                        shapely.Point(best_pad)
                        .buffer(5.5, cap_style="square")
                        .exterior.coords
                    ),
                    2,
                ).tolist(),
                "facade_xy": np.round(hit, 2).tolist(),
                "pick_radius_center_ft": ft(radius),
                "pick_radius_far_corner_ft": ft(far),
                "pick_height_above_ramp_ft": ft(
                    ahu["roof_z_m"] + 0.01 - float(dem.at(*best_pad)[0])
                ),
                "ramp_z_m": round(float(dem.at(*best_pad)[0]), 2),
                "load_lb": 57900,
                "method": "CALCULATED ESTIMATE: 36 x 36 ft pad (placeholder outrigger footprint) on the "
                "OSM apron polygon, on the line from the AHU-5 candidate to the nearest apron, the first "
                "spot clear of lidar objects over 3 ft (jet bridges, GSE). Radius measured centre of pad "
                "to unit centre and to the unit's far corner. Location to confirm with AmeriTech and "
                "airport operations; crane not selected.",
            }

    # RTU-5: crane on Airport Road beside the bridge, closure = Airport Road within 150 ft
    r5 = units[1]
    p5 = shapely.Point(r5["xy"])
    sproj = road_under.project(p5)
    spots = []
    for ds in np.arange(10.0, 40.0, 1.0):
        for sgn in (1, -1):
            pt = road_under.interpolate(sproj + sgn * ds)
            if pt.distance(bridge_poly) > 4.0:
                spots.append((pt.distance(p5), pt))
    spots.sort(key=lambda x: x[0])
    c5 = spots[0][1]
    closure_len = 45.7  # 150 ft each side of the crane spot along the centreline
    s_c = road_under.project(c5)
    seg = shapely.ops.substring(
        road_under, max(0, s_c - closure_len), min(road_under.length, s_c + closure_len)
    )
    closure = seg.buffer(
        6.1, cap_style="flat"
    )  # 40 ft wide band, roadway width NOT measured
    rtu5_crane = {
        "spot_xy": [round(c5.x, 2), round(c5.y, 2)],
        "pick_radius_ft": ft(c5.distance(p5)),
        "pick_height_above_road_ft": ft(r5["roof_z_m"] - float(dem.at(c5.x, c5.y)[0])),
        "closure_ring": np.round(np.asarray(closure.exterior.coords), 2).tolist(),
        "closure_length_ft": ft(seg.length, 0),
        "method": "CALCULATED ESTIMATE: crane spot = nearest point on the Airport Road centreline "
        "(OSM) at least 13 ft clear of the bridge outline; closure band = 150 ft each way along the "
        "centreline, 40 ft wide (roadway width NOT measured; replace with the MOT plan). Night work "
        "1:30 to 4:00 AM per the bid package (1:00 to 4:00 AM said at the pre-bid meeting).",
    }

    # alternates as records for the docs
    out = {
        "grade_m": round(grade, 2),
        "grade_p5_p95_m": grade_p,
        "terminal_roof_levels": roof_levels,
        "valley_roof_z_m": valley_z,
        "upper_roof_check": {
            "gp1_note_ft": 34,
            "lidar_main_roof_above_grade_ft": ft(
                max(roof_levels, key=lambda r: r["area_sqft"])["z_m"] - grade
            ),
            "lidar_highest_roof_above_grade_ft": ft(
                max(r["z_m"] for r in roof_levels) - grade
            ),
        },
        "units": units,
        "ahu5_alternates": alt,
        "bridge": bridge,
        "rooms": rooms,
        "routes": routes,
        "crane_ahu5": crane,
        "crane_rtu5": rtu5_crane,
        "roof_objects_detected": {
            "terminal": len(t_obj),
            "bridge": len(b_obj),
            "bridge_arches": len(arches),
        },
        "dsm_box": box,
        "levels_seen": sorted(set(levels.tolist()))[:5],
    }
    json.dump(out, open(os.path.join(W, "analysis.json"), "w"), indent=1)
    print(
        json.dumps(
            {k: v for k, v in out.items() if k not in ("routes", "rooms")}, indent=1
        )[:6000]
    )
    for r in routes:
        print(
            r["unit"],
            r["unit_located"],
            r["riser_ft"],
            r.get("riser_bound_ft"),
            r["assumed_total_ft"],
            r.get("left_for_horizontal_and_roof_ft"),
            r["plan_max_euclid_ft"],
        )


if __name__ == "__main__":
    main()
