"""Mill roof measurement table from the 2019 USGS lidar (Wilton #1976, site 4).

For every building of the mill complex (1 Riverside Way; footprints = lidar-registered OSM):
roof planes by RANSAC on single-return lidar points, each split into connected patches, with
plan + sloped area, pitch, true-north azimuth, height (NAVD88 and above ground), obstructions
(returns > 0.5 m above the plane) and usable area after a 3 ft and a 4 ft fire setback.
Solar sizing is a CALCULATED ESTIMATE with the method written into the table. No pricing.

    python mill_roof.py --work WORK --cache CACHE
"""

import argparse
import json
import math
import os

import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import Polygon

import frame

FT, SQFT = 0.3048, 0.3048**2
CELL = 0.5  # m raster for patches
CLAIMS = [
    (
        "93,000 sq ft",
        93000,
        "Ledger-Transcript 2022-09-14 ('three-story mill building houses 93,000 square feet')",
    ),
    (
        "93,890 sq ft",
        93890,
        "WRCRE broker listing 1-riverside-way-sold ('combined ... approximately 93,890 square feet')",
    ),
    (
        "94,000 sq ft",
        94000,
        "cityfeet / LoopNet listing ('Total Building Size 94,000 SF') - also Ted's figure per brief",
    ),
    (
        "100,000 sq ft",
        100000,
        "chillybears.com storage-3pl page / Pidcock LinkedIn ('100K SF')",
    ),
]
# solar assumptions (CALCULATED ESTIMATE inputs, stated in the table)
MODULE_W_PER_M2 = 215.0  # e.g. a 430 W module on 2.0 m^2 (21.5 % efficient)
GCR_FLAT = 0.70  # tilted racking rows on low-slope roofs
GCR_PITCHED = 0.85  # flush-mounted on pitched planes
FLAT_DEG = 5.0


def grid_convergence(lat, lon):
    """Angle (deg) from grid north to true north at a point, measured clockwise."""
    e1, n1 = frame.utm(lat, lon)
    e2, n2 = frame.utm(lat + 0.001, lon)
    return math.degrees(math.atan2(float(e2 - e1), float(n2 - n1)))


def ransac_planes(P, rng, dist=0.15, min_pts=120, iters=400, max_planes=14):
    remaining = np.arange(len(P))
    out = []
    for _ in range(max_planes):
        if len(remaining) < min_pts:
            break
        Q = P[remaining]
        best = None
        for _ in range(iters):
            s = Q[rng.choice(len(Q), 3, replace=False)]
            n = np.cross(s[1] - s[0], s[2] - s[0])
            nn = np.linalg.norm(n)
            if nn < 1e-6:
                continue
            n = n / nn
            if n[2] < 0:
                n = -n
            if n[2] < 0.5:  # steeper than 60 deg: walls / noise
                continue
            inl = np.abs((Q - s[0]) @ n) < dist
            if best is None or inl.sum() > best[0].sum():
                best = (inl, n)
        if best is None or best[0].sum() < min_pts:
            break
        inl = best[0]
        # least-squares refit z = ax + by + c on inliers, then re-select inliers
        A = np.column_stack([Q[inl, 0], Q[inl, 1], np.ones(inl.sum())])
        (a, b, c), *_ = np.linalg.lstsq(A, Q[inl, 2], rcond=None)
        res = Q[:, 2] - (a * Q[:, 0] + b * Q[:, 1] + c)
        inl = np.abs(res) < dist / math.sqrt(1 / (1 + a * a + b * b))
        out.append((remaining[inl], (a, b, c)))
        remaining = remaining[~inl]
    return out, remaining


def mask_of(xy, origin, shape_):
    m = np.zeros(shape_, bool)
    c = ((xy[:, 0] - origin[0]) / CELL).astype(int)
    r = ((origin[1] - xy[:, 1]) / CELL).astype(int)
    ok = (c >= 0) & (c < shape_[1]) & (r >= 0) & (r < shape_[0])
    m[r[ok], c[ok]] = True
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--cache", required=True)
    a = ap.parse_args()
    W = a.work
    B = json.load(open(os.path.join(W, "buildings_detail.json")))
    pts = json.load(open(os.path.join(W, "points.json")))
    dem = np.load(os.path.join(W, "dem_detail.npz"))
    zd, dx0, dy0 = dem["z"].astype(float), float(dem["x0"]), float(dem["y0"])

    def ground(x, y):
        c = np.clip((np.atleast_1d(x) - dx0).astype(int), 0, zd.shape[1] - 1)
        r = np.clip((dy0 - np.atleast_1d(y)).astype(int), 0, zd.shape[0] - 1)
        return zd[r, c]

    ll = np.load(os.path.join(a.cache, "lidar_points.npz"))
    x, y = frame.local(ll["lat"], ll["lon"])
    P = np.column_stack([x, y, ll["z_navd88"]])
    single = ll["nret"] == 1
    cls = ll["cls"]
    # mill complex: footprints >= 300 m2 within 60 m of the building holding "Computer Haven",
    # south of Mill St, west of the Souhegan
    ch = shapely.Point(
        *next(p["xy"] for p in pts["places"] if p["name"] == "Computer Haven")
    )
    polys = [(i, Polygon(b["footprint"], b["holes"])) for i, b in enumerate(B)]
    seed = min(polys, key=lambda t: t[1].distance(ch))[1]
    complex_ = [
        (i, p)
        for i, p in polys
        if p.area >= 300 and p.distance(seed) < 60 and p.centroid.y < 5
    ]
    lat_c, lon_c = frame.geodetic(seed.centroid.x, seed.centroid.y)
    conv = grid_convergence(float(lat_c), float(lon_c))
    rng = np.random.default_rng(1976)
    report = {
        "convergence_deg": round(conv, 3),
        "buildings": [],
        "assumptions": {
            "plane_fit": "RANSAC 0.15 m tolerance on single-return lidar points (NH_Coastal_2_2019, ~4.6 pts/m2), patches on a 0.5 m grid",
            "setback": "usable = patch eroded by 3 ft / 4 ft from every patch edge, minus obstructions +1 m (CALCULATED ESTIMATE)",
            "solar": f"kW-DC = usable m2 x {MODULE_W_PER_M2:.0f} W/m2 module power density x coverage ({GCR_FLAT} flat <{FLAT_DEG:.0f} deg on tilted rows, {GCR_PITCHED} pitched flush); north-facing pitched planes (>{FLAT_DEG:.0f} deg, azimuth 300-60 deg) excluded (CALCULATED ESTIMATE)",
        },
    }
    patches_geo = []
    for bi, poly in complex_:
        minx, miny, maxx, maxy = poly.bounds
        sel = (
            (P[:, 0] >= minx)
            & (P[:, 0] <= maxx)
            & (P[:, 1] >= miny)
            & (P[:, 1] <= maxy)
            & single
            & (cls == 1)
        )
        Q = P[sel]
        Q = Q[shapely.contains_xy(poly.buffer(-0.3), Q[:, 0], Q[:, 1])]
        g_base = float(ground(*np.asarray(poly.exterior.coords).T).min())
        Q = Q[Q[:, 2] > g_base + 2.0]
        if len(Q) < 200:
            continue
        planes, rest = ransac_planes(Q, rng)
        origin = (minx - 2, maxy + 2)
        shape_ = (int((maxy - miny + 4) / CELL) + 1, int((maxx - minx + 4) / CELL) + 1)
        fp_mask = mask_of(
            np.column_stack(
                [
                    np.repeat(
                        np.arange(shape_[1]) * CELL + origin[0] + CELL / 2, shape_[0]
                    ),
                    np.tile(
                        origin[1] - np.arange(shape_[0]) * CELL - CELL / 2, shape_[1]
                    ),
                ]
            ),
            origin,
            shape_,
        )
        rr, cc = np.nonzero(np.ones(shape_, bool))
        cxy = np.column_stack(
            [origin[0] + (cc + 0.5) * CELL, origin[1] - (rr + 0.5) * CELL]
        )
        fp_mask = shapely.contains_xy(poly, cxy[:, 0], cxy[:, 1]).reshape(shape_)
        roof_any = (
            ndimage.binary_closing(mask_of(Q[:, :2], origin, shape_), iterations=2)
            & fp_mask
        )
        tenants = [
            q["name"]
            for q in pts["places"]
            if poly.buffer(3).contains(shapely.Point(*q["xy"]))
        ]
        label_ = (
            "North building"
            if poly.centroid.y > seed.centroid.y - 1
            else "South building"
        ) + (f" ({', '.join(tenants)})" if tenants else "")
        bres = {
            "building": label_,
            "footprint_sqft": round(poly.area / SQFT),
            "footprint_m2": round(poly.area, 1),
            "lidar_roof_extent_sqft": round(roof_any.sum() * CELL**2 / SQFT),
            "eave_ground_z_ft": round(g_base / FT, 1),
            "n_roof_points": int(len(Q)),
            "planes": [],
        }
        for k, (idx, (pa, pb, pc)) in enumerate(planes):
            m = (
                ndimage.binary_closing(
                    mask_of(Q[idx, :2], origin, shape_), iterations=2
                )
                & fp_mask
            )
            lab, n = ndimage.label(m)
            for j in range(1, n + 1):
                patch = lab == j
                if patch.sum() * CELL**2 < 20:  # ignore < 20 m2 fragments
                    continue
                slope = math.degrees(math.atan(math.hypot(pa, pb)))
                grid_az = (
                    math.degrees(math.atan2(-pa, -pb)) + 360
                ) % 360  # downslope direction, grid
                true_az = (grid_az - conv) % 360 if slope >= 1.0 else None
                plan_m2 = patch.sum() * CELL**2
                pr, pc_ = np.nonzero(patch)
                px = origin[0] + (pc_ + 0.5) * CELL
                py = origin[1] - (pr + 0.5) * CELL
                zplane = pa * px + pb * py + pc
                # obstructions: returns > 0.5 m above this plane within the patch
                qr = ((origin[1] - Q[:, 1]) / CELL).astype(int)
                qc = ((Q[:, 0] - origin[0]) / CELL).astype(int)
                okq = (qr >= 0) & (qr < shape_[0]) & (qc >= 0) & (qc < shape_[1])
                onp = np.zeros(len(Q), bool)
                onp[okq] = patch[qr[okq], qc[okq]]
                above = onp & (Q[:, 2] - (pa * Q[:, 0] + pb * Q[:, 1] + pc) > 0.5)
                ob_mask = (
                    ndimage.binary_dilation(
                        mask_of(Q[above, :2], origin, shape_), iterations=2
                    )
                    & patch
                )
                ob_lab, n_ob = ndimage.label(ob_mask)
                usable = {}
                edge_dist = (
                    ndimage.distance_transform_edt(np.pad(patch, 1))[1:-1, 1:-1] * CELL
                )  # m to the patch edge
                ob_dist = (
                    ndimage.distance_transform_edt(~ob_mask) * CELL
                    if ob_mask.any()
                    else np.full(patch.shape, 1e9)
                )
                for sb_ft in (3, 4):
                    er = patch & (edge_dist > sb_ft * FT) & (ob_dist > 1.0)
                    usable[sb_ft] = er.sum() * CELL**2 / math.cos(math.radians(slope))
                north = (
                    slope > FLAT_DEG
                    and true_az is not None
                    and (true_az >= 300 or true_az <= 60)
                )
                gcr = GCR_FLAT if slope < FLAT_DEG else GCR_PITCHED
                kw = 0.0 if north else usable[4] * MODULE_W_PER_M2 * gcr / 1000.0
                bres["planes"].append(
                    {
                        "id": f"{len(bres['planes']) + 1}",
                        "plan_area_sqft": round(plan_m2 / SQFT),
                        "plan_area_m2": round(plan_m2, 1),
                        "sloped_area_sqft": round(
                            plan_m2 / math.cos(math.radians(slope)) / SQFT
                        ),
                        "sloped_area_m2": round(
                            plan_m2 / math.cos(math.radians(slope)), 1
                        ),
                        "slope_deg": round(slope, 1),
                        "pitch_in_12": round(12 * math.tan(math.radians(slope)), 1),
                        "azimuth_true_deg": round(true_az, 0)
                        if true_az is not None
                        else "flat (<1 deg)",
                        "height_navd88_ft": round(float(zplane.mean()) / FT, 1),
                        "height_above_ground_ft": round(
                            (float(zplane.mean()) - g_base) / FT, 1
                        ),
                        "obstructions": int(n_ob),
                        "obstruction_area_sqft": round(ob_mask.sum() * CELL**2 / SQFT),
                        "usable_3ft_sqft": round(usable[3] / SQFT),
                        "usable_4ft_sqft": round(usable[4] / SQFT),
                        "solar_kwdc_est": round(kw, 1),
                        "solar_note": "north-facing - excluded"
                        if north
                        else f"GCR {gcr}",
                    }
                )
                cs = shapely.unary_union(
                    [
                        shapely.box(
                            xx - CELL / 2, yy - CELL / 2, xx + CELL / 2, yy + CELL / 2
                        )
                        for xx, yy in zip(px, py)
                    ]
                ).simplify(0.3)
                for gg in [cs] if cs.geom_type == "Polygon" else list(cs.geoms):
                    patches_geo.append(
                        {
                            "building": bres["building"],
                            "plane": bres["planes"][-1]["id"],
                            "abc": [pa, pb, pc],
                            "ring": [
                                list(map(lambda v: round(v, 3), q))
                                for q in gg.exterior.coords[:-1]
                            ],
                        }
                    )
        bres["unassigned_roof_points"] = int(len(rest))
        report["buildings"].append(bres)
    tot_fp = sum(b["footprint_sqft"] for b in report["buildings"])
    tot_roof = sum(
        p["sloped_area_sqft"] for b in report["buildings"] for p in b["planes"]
    )
    tot_u3 = sum(p["usable_3ft_sqft"] for b in report["buildings"] for p in b["planes"])
    tot_u4 = sum(p["usable_4ft_sqft"] for b in report["buildings"] for p in b["planes"])
    tot_kw = sum(p["solar_kwdc_est"] for b in report["buildings"] for p in b["planes"])
    report["totals"] = {
        "footprint_sqft": tot_fp,
        "roof_planes_sloped_sqft": tot_roof,
        "usable_3ft_sqft": tot_u3,
        "usable_4ft_sqft": tot_u4,
        "solar_kwdc_est": round(tot_kw, 1),
    }
    report["claims"] = [
        {"claim": c, "source": s, "claim_over_footprint": round(v / tot_fp, 2)}
        for c, v, s in CLAIMS
    ]
    json.dump(report, open(os.path.join(W, "mill_roof.json"), "w"), indent=1)
    json.dump(patches_geo, open(os.path.join(W, "mill_roof_patches.json"), "w"))
    write_md(report, os.path.join(W, "MILL_ROOF.md"))
    print(json.dumps(report["totals"]), [len(b["planes"]) for b in report["buildings"]])


def write_md(r, path):
    t = r["totals"]
    L = [
        "# Mill roof measurements - 1 Riverside Way, Wilton (from 2019 USGS lidar)",
        "",
        f"Grid convergence at the mill: {r['convergence_deg']} deg (true azimuths below are corrected for it).",
        "",
        "## Totals",
        "",
        "| Measure | Value | Basis |",
        "|---|---|---|",
        f"| Building footprints (mill complex) | {t['footprint_sqft']:,} sq ft | lidar-registered OSM footprints, MEASURED |",
        f"| Roof planes, sloped area | {t['roof_planes_sloped_sqft']:,} sq ft | lidar plane fits, MEASURED |",
        f"| Usable after 3 ft setback | {t['usable_3ft_sqft']:,} sq ft | CALCULATED ESTIMATE |",
        f"| Usable after 4 ft setback | {t['usable_4ft_sqft']:,} sq ft | CALCULATED ESTIMATE |",
        f"| Solar, 4 ft setback | {t['solar_kwdc_est']:,} kW-DC | CALCULATED ESTIMATE (method below) |",
        "",
        "## Claimed sizes vs measured footprint",
        "",
        "The claims are floor areas (the 2022 article calls it a three-story mill); the lidar measures roofs / footprints. "
        "Claim / footprint is the floor-area ratio each claim implies - a CALCULATED ESTIMATE, not a story count.",
        "",
        "| Claim | Source | Claim / measured footprint |",
        "|---|---|---|",
    ]
    L += [
        f"| {c['claim']} | {c['source']} | {c['claim_over_footprint']} |"
        for c in r["claims"]
    ]
    for b in r["buildings"]:
        L += [
            "",
            f"## {b['building']} - footprint {b['footprint_sqft']:,} sq ft, lidar roof extent {b['lidar_roof_extent_sqft']:,} sq ft, ground {b['eave_ground_z_ft']} ft NAVD88",
            "",
            "| Plane | Plan sq ft (m²) | Sloped sq ft (m²) | Slope ° / pitch | Azimuth (true) | Height NAVD88 / above ground ft | Obstructions (sq ft) | Usable 3 ft / 4 ft sq ft | Solar kW-DC (est.) |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for p in b["planes"]:
            L.append(
                f"| {p['id']} | {p['plan_area_sqft']:,} ({p['plan_area_m2']}) | {p['sloped_area_sqft']:,} ({p['sloped_area_m2']}) | {p['slope_deg']} / {p['pitch_in_12']}:12 | {p['azimuth_true_deg']} | "
                f"{p['height_navd88_ft']} / {p['height_above_ground_ft']} | {p['obstructions']} ({p['obstruction_area_sqft']}) | {p['usable_3ft_sqft']:,} / {p['usable_4ft_sqft']:,} | {p['solar_kwdc_est']} ({p['solar_note']}) |"
            )
    L += (
        ["", "## Method and assumptions", ""]
        + [f"- **{k}**: {v}" for k, v in r["assumptions"].items()]
        + [
            "- Roof structure, membrane, age and load capacity are NOT measured - see the missing-measurements list.",
            "- Parapets, skylights and equipment under ~0.5 m tall are below the lidar's resolution here.",
        ]
    )
    open(path, "w").write("\n".join(L))


if __name__ == "__main__":
    main()
