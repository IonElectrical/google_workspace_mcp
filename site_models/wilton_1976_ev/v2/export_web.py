"""Export the v2 downtown model to a single-file browser viewer (three.js), so the Town can walk
the sites without Blender.

    python export_web.py --work WORK [--out web/Wilton_Downtown_Viewer.html]

Reads the same WORK folder as build_downtown_v2.py (prepare_downtown.py + layouts.py +
mill_roof.py outputs) and fills web/viewer_template.html. Geometry stays in the model frame
(UTM 19N minus 276000 / 4747000 m, NAVD88 m). The viewer loads three.js r147 from jsDelivr.
"""

import argparse
import base64
import io
import json
import math
import os

import numpy as np
import shapely
from PIL import Image
from scipy.spatial import Delaunay

HERE = os.path.dirname(os.path.abspath(__file__))
FT = 0.3048
OV_STEP = 3  # overview DEM 8 m -> 24 m in the browser


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


class Ground:
    """Detail 1 m DEM where available, else the 8 m overview DEM (bilinear)."""

    def __init__(self, work):
        self.g = []
        for f in ("dem_detail.npz", "dem_overview.npz"):
            d = np.load(os.path.join(work, f))
            self.g.append(
                (
                    d["z"].astype(np.float64),
                    float(d["x0"]),
                    float(d["y0"]),
                    float(d["step"]),
                )
            )

    @staticmethod
    def _bil(g, x, y):
        z, x0, y0, st = g
        c, r = (x - x0) / st, (y0 - y) / st
        ok = (c >= 0) & (r >= 0) & (c <= z.shape[1] - 1) & (r <= z.shape[0] - 1)
        c, r = np.clip(c, 0, z.shape[1] - 1.0001), np.clip(r, 0, z.shape[0] - 1.0001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        v = (
            z[r0, c0] * (1 - fc) * (1 - fr)
            + z[r0, c0 + 1] * fc * (1 - fr)
            + z[r0 + 1, c0] * (1 - fc) * fr
            + z[r0 + 1, c0 + 1] * fc * fr
        )
        return v, ok & ~np.isnan(v)

    def z(self, x, y):
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        vd, okd = self._bil(self.g[0], x, y)
        vo, _ = self._bil(self.g[1], x, y)
        return np.where(okd, vd, vo)


def quant(z, q):
    zmin = float(np.nanmin(z))
    u = np.where(np.isnan(z), 65535, np.round((z - zmin) / q)).astype("<u2")
    return zmin, u


def densify(xy, step=2.0):
    """step: metres, or a function (segment midpoint) -> metres."""
    xy = np.asarray(xy, float)
    out = [xy[0]]
    for a, b in zip(xy[:-1], xy[1:]):
        st = step((a + b) / 2) if callable(step) else step
        n = max(1, int(np.linalg.norm(b - a) / st))
        out += [a + (b - a) * (k / n) for k in range(1, n + 1)]
    return np.asarray(out)


def drape_line(xy, ground, lift, step=2.0):
    d = densify(xy, step)
    return np.round(np.column_stack([d, ground.z(d[:, 0], d[:, 1]) + lift]), 3)


def pack_lines(lines):
    """Polylines (n_i x 3 arrays) -> {"p": base64 float32 xyz, "n": [n_i]}."""
    lines = [np.asarray(ln, float).reshape(-1, 3) for ln in lines if len(ln) >= 2]
    if not lines:
        return {"p": "", "n": []}
    return {
        "p": b64(np.concatenate(lines).astype("<f4")),
        "n": [len(ln) for ln in lines],
    }


def drape_poly(ring, ground, spacing=2.0, lift=0.08):
    """Polygon draped on the DEM: boundary + interior points, Delaunay, centroid-in filter."""
    poly = shapely.Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    pts = [np.asarray(shapely.segmentize(poly.exterior, spacing).coords)[:-1]]
    minx, miny, maxx, maxy = poly.bounds
    gx, gy = np.meshgrid(np.arange(minx, maxx, spacing), np.arange(miny, maxy, spacing))
    cand = np.column_stack([gx.ravel(), gy.ravel()])
    inner = poly.buffer(-spacing * 0.4)
    if len(cand) and not inner.is_empty:
        pts.append(cand[shapely.contains_xy(inner, cand[:, 0], cand[:, 1])])
    p = np.concatenate(pts)
    tri = Delaunay(p).simplices
    cen = p[tri].mean(1)
    tri = tri[shapely.contains_xy(poly, cen[:, 0], cen[:, 1])]
    z = ground.z(p[:, 0], p[:, 1]) + lift
    return {
        "p": b64(np.column_stack([p, z]).astype("<f4")),
        "i": b64(tri.astype("<u4")),
    }


def ring_area_sqft(ring):
    return round(shapely.Polygon(ring).area / FT**2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument(
        "--out", default=os.path.join(HERE, "web", "Wilton_Downtown_Viewer.html")
    )
    ap.add_argument(
        "--bare",
        action="store_true",
        help="omit the document head (for publishing as a hosted page)",
    )
    a = ap.parse_args()
    W = a.work
    J = lambda n: json.load(open(os.path.join(W, n)))  # noqa: E731
    meta, L, MR = J("meta.json"), J("layouts.json"), J("mill_roof.json")
    ground = Ground(W)
    det = meta["detail_box"]
    D = {
        "meta": {
            k: meta[k] for k in ("crs", "vertical", "origin", "retrieved", "checks")
        }
    }
    D["meta"]["layers"] = meta["layers"]
    D["design"] = L["design"]

    # terrain: 1 m detail grid (the browser meshes every 2nd cell, samples heights at 1 m)
    d = np.load(os.path.join(W, "dem_detail.npz"))
    zmin, u = quant(d["z"].astype(np.float64), 0.01)
    D["det"] = {
        "x0": float(d["x0"]),
        "y0": float(d["y0"]),
        "step": float(d["step"]),
        "ny": int(u.shape[0]),
        "nx": int(u.shape[1]),
        "zmin": zmin,
        "q": 0.01,
        "z": b64(u),
    }
    o = np.load(os.path.join(W, "dem_overview.npz"))
    zo = o["z"].astype(np.float64)[::OV_STEP, ::OV_STEP].copy()
    st = float(o["step"]) * OV_STEP
    ox0, oy0 = float(o["x0"]), float(o["y0"])
    cx = ox0 + np.arange(zo.shape[1]) * st
    cy = oy0 - np.arange(zo.shape[0]) * st
    inside = (
        (cx[None, :] > det[0] + st)
        & (cx[None, :] < det[2] - st)
        & (cy[:, None] > det[1] + st)
        & (cy[:, None] < det[3] - st)
    )
    zo[inside] = np.nan  # the detail mesh covers it
    zmin, u = quant(zo, 0.05)
    D["ov"] = {
        "x0": ox0,
        "y0": oy0,
        "step": st,
        "ny": int(u.shape[0]),
        "nx": int(u.shape[1]),
        "zmin": zmin,
        "q": 0.05,
        "z": b64(u),
    }
    buf = io.BytesIO()
    Image.open(os.path.join(W, "ground_detail.png")).convert("RGB").save(
        buf, "JPEG", quality=78, optimize=True
    )
    D["tex"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    D["texBox"] = det

    # detail buildings: lidar roof triangles + walls to the ground
    P, IDX, K, VO, outlines, binfo = [], [], [], [], [], []
    for b in J("buildings_detail.json"):
        if not b["lidar_roof"]:
            outlines.append(
                np.round(
                    np.column_stack(
                        [
                            b["footprint"],
                            np.full(len(b["footprint"]), b["base_z"] + 0.2),
                        ]
                    ),
                    3,
                )
                .ravel()
                .tolist()
            )
            continue
        xy, z = np.asarray(b["roof_xy"]), np.asarray(b["roof_z"])
        o0 = sum(len(p) for p in P)
        verts = [np.column_stack([xy, z])]
        tris = [np.asarray(b["roof_faces"], int).reshape(-1, 3)]
        kinds = [np.zeros(len(tris[0]), np.uint8)]
        start, nv = 0, len(xy)
        for k in [b["n_ring"]] + list(b["hole_rings"]):
            ids = np.arange(start, start + k)
            verts.append(np.column_stack([xy[ids], np.full(k, b["base_z"] - 0.3)]))
            bot = nv + np.arange(k)
            nxt = np.roll(np.arange(k), -1)
            tris.append(np.column_stack([ids, ids[nxt], bot[nxt]]))
            tris.append(np.column_stack([ids, bot[nxt], bot]))
            kinds += [np.ones(k, np.uint8)] * 2
            nv += k
            start += k
        P.append(np.concatenate(verts))
        IDX.append(np.concatenate(tris))
        VO.append(o0)
        K.append(np.concatenate(kinds))
        binfo.append(
            {
                "n": b["name"],
                "h": round((b["top_z"] - b["base_z"]) / FT, 1),
                "a": round(b["area_m2"] / FT**2),
            }
        )
    tri_owner = np.concatenate([np.full(len(k), i, np.uint16) for i, k in enumerate(K)])
    assert max(len(p) for p in P) < 65535
    D["bld"] = {
        "p": b64(np.concatenate(P).astype("<f4")),
        "i": b64(np.concatenate(IDX).astype("<u2")),
        "vo": VO,
        "k": b64(np.concatenate(K)),
        "o": b64(tri_owner.astype("<u2")),
        "info": binfo,
        "outlines": outlines,
    }

    # overview buildings outside the detail box (roofs triangulated in the browser)
    rings, counts, base, top, nh = [], [], [], [], []
    for b in J("buildings_overview.json"):
        r = np.asarray(b["footprint"])[:-1]
        c = r.mean(0)
        if det[0] < c[0] < det[2] and det[1] < c[1] < det[3]:
            continue
        if b["top_z"] is None:
            nh.append(
                np.round(
                    np.column_stack(
                        [
                            b["footprint"],
                            np.full(len(b["footprint"]), b["base_z"] + 0.3),
                        ]
                    ),
                    2,
                )
                .ravel()
                .tolist()
            )
            continue
        if len(r) < 3:
            continue
        rings.append(r)
        counts.append(len(r))
        base.append(b["base_z"] - 0.5)
        top.append(b["top_z"])
    D["ovb"] = {
        "xy": b64(np.concatenate(rings).astype("<f4")),
        "n": counts,
        "base": np.round(base, 2).tolist(),
        "top": np.round(top, 2).tolist(),
        "noheight": nh,
    }

    D["trees"] = b64(np.load(os.path.join(W, "trees.npy")).astype("<f4"))

    # roads + footways (draped centrelines), street-name labels
    roads, names = {"road": [], "foot": [], "rail": []}, {}

    def step_for(_line):  # 2 m inside the detail area, 25 m in the overview
        return lambda m: (
            2.0
            if (det[0] - 20 < m[0] < det[2] + 20 and det[1] - 20 < m[1] < det[3] + 20)
            else 25.0
        )

    for r in J("roads.json"):
        line = np.asarray(r["line"])
        kind = (
            "rail"
            if r["subtype"] == "rail"
            else ("foot" if r["class"] in ("footway", "path", "steps") else "road")
        )
        roads[kind].append(drape_line(line, ground, 0.25, step_for(line)))
        if r.get("name") and kind == "road":
            length = float(np.sum(np.linalg.norm(np.diff(line, axis=0), axis=1)))
            mid = line[len(line) // 2] if len(line) > 2 else line.mean(0)
            if (
                det[0] < mid[0] < det[2]
                and det[1] < mid[1] < det[3]
                and length > names.get(r["name"], (0,))[0]
            ):
                names[r["name"]] = (length, mid)
    D["roads"] = {k: pack_lines(v) for k, v in roads.items()}
    labels = [
        {
            "t": n,
            "p": [round(m[0], 2), round(m[1], 2), round(float(ground.z(*m)[0]) + 4, 2)],
            "k": "street",
        }
        for n, (_, m) in names.items()
    ]

    # water: NHD flowlines + waterbody outlines; flat fills for ponds at their shoreline level
    Wt = J("water.json")
    wl, wfill, wnames = [], [], {}
    for f in Wt["flowlines"]:
        for line in f["geom"]["coordinates"]:
            ln2 = np.asarray(line)[:, :2]
            wl.append(drape_line(ln2, ground, 0.3, step_for(ln2)))
            if f["name"]:
                ln = np.asarray(line)[:, :2]
                inb = ln[
                    (ln[:, 0] > det[0])
                    & (ln[:, 0] < det[2])
                    & (ln[:, 1] > det[1])
                    & (ln[:, 1] < det[3])
                ]
                if len(inb) > wnames.get(f["name"], (0,))[0]:
                    wnames[f["name"]] = (len(inb), inb[len(inb) // 2])
    for f in Wt["waterbodies"] + Wt["areas"]:
        for poly in f["geom"]["coordinates"]:
            ring = np.asarray(poly[0])[:, :2]
            wz = float(np.percentile(ground.z(ring[:, 0], ring[:, 1]), 10))
            wl.append(drape_line(ring, ground, 0.3, step_for(ring)))
            if f["ftype"] != 460:  # lakes / ponds are level; rivers are not
                wfill.append(
                    {
                        "n": f["name"],
                        "z": round(wz + 0.12, 2),
                        "xy": np.round(ring, 2).ravel().tolist(),
                    }
                )
    D["water"] = {"lines": pack_lines(wl), "fills": wfill}
    labels += [
        {
            "t": n,
            "p": [round(m[0], 2), round(m[1], 2), round(float(ground.z(*m)[0]) + 3, 2)],
            "k": "water",
        }
        for n, (_, m) in wnames.items()
    ]

    # landmarks used to check the site points
    pts = J("points.json")
    for s in pts["structures"]:
        if "xy" in s and s.get("name"):
            x, y = s["xy"]
            if det[0] < x < det[2] and det[1] < y < det[3]:
                labels.append(
                    {
                        "t": s["name"] + " (USGS)",
                        "p": [x, y, float(ground.z(x, y)[0]) + 8],
                        "k": "landmark",
                    }
                )
    for p in pts["places"]:
        if p.get("category") in (
            "police_station",
            "library",
            "government_office",
            "town_hall",
            "post_office",
            "fire_station",
        ):
            x, y = p["xy"]
            labels.append(
                {
                    "t": p["name"],
                    "p": [x, y, float(ground.z(x, y)[0]) + 8],
                    "k": "landmark",
                }
            )

    # sites: layouts + overlays
    sites = []
    titles = {
        "S1_PoliceLot": "Site 1 · Police lot",
        "S2_MainStLot": "Site 2 · Main St lot",
        "S3_Library": "Site 3 · Library street-side",
        "S4_Mill": "Site 4 · Pidcock mill",
    }
    addr = {
        "S1_PoliceLot": "7 Burns Hill Rd",
        "S2_MainStLot": "Main St municipal lot (near 42 Main St)",
        "S3_Library": "Wilton Public & Gregg Free Library, Forest Rd",
        "S4_Mill": "1 Riverside Way / 21 Mill St",
    }
    for key, s in L["sites"].items():
        items = []
        for it in s["items"]:
            poly = np.asarray(it["poly"])
            z = ground.z(poly[:, 0], poly[:, 1]) + 0.05
            kind = (
                "ada"
                if ("ADA" in it["name"] and "aisle" not in it["name"])
                else ("aisle" if "aisle" in it["name"] else "stall")
            )
            items.append(
                {
                    "n": it["name"],
                    "k": kind,
                    "s": it["slope_pct"],
                    "p": np.round(np.column_stack([poly, z]), 3).ravel().tolist(),
                }
            )
        th = s["pedestals"][0]["heading_deg"]
        peds = [
            {"xy": p["xy"], "z": round(float(ground.z(*p["xy"])[0]), 3)}
            for p in s["pedestals"]
        ]
        cxy = np.mean([np.mean(it["poly"], axis=0) for it in s["items"]], axis=0)
        cz = float(ground.z(*cxy)[0])
        t = math.radians(th)
        back = np.array([-math.sin(t), math.cos(t)])
        eye = cxy + back * -30.0
        aer = cxy + back * -70.0 + np.array([20.0, -20.0])
        site = {
            "key": key,
            "title": titles[key],
            "addr": addr[key],
            "rationale": s["rationale"],
            "kind": s["kind"],
            "search": s["search"],
            "measured": s["measured"],
            "items": items,
            "heading": th,
            "peds": peds,
            "power": {
                "xy": s["power_placeholder"]["xy"],
                "z": round(float(ground.z(*s["power_placeholder"]["xy"])[0]), 3),
                "note": s["power_placeholder"]["note"],
            },
            "trenches": [
                {
                    "to": tr["to"],
                    "p": np.round(np.asarray(tr["points"]) + [0, 0, 0.06], 3)
                    .ravel()
                    .tolist(),
                    "l3": tr["length_3d_ft"],
                    "l2": tr["length_2d_ft"],
                }
                for tr in s["trenches"]
            ],
            "center": [round(float(cxy[0]), 2), round(float(cxy[1]), 2), round(cz, 2)],
            "eye": [
                round(float(eye[0]), 2),
                round(float(eye[1]), 2),
                round(float(ground.z(*eye)[0]) + 1.68, 2),
            ],
            "aerial": [
                round(float(aer[0]), 2),
                round(float(aer[1]), 2),
                round(float(ground.z(*aer)[0]) + 55.0, 2),
            ],
            "ov": [],
        }
        if "deed_area" in s:
            da = s["deed_area"]
            site["ov"].append(
                {
                    "k": "deed",
                    "mesh": drape_poly(da["poly"], ground, 2.0, 0.07),
                    "label": da["label"],
                    "area": da["area_sqft"],
                    "src": da["source"],
                    "at": [*np.asarray(da["poly"]).mean(0).round(2).tolist()],
                }
            )
        if "police_exit" in s:
            pe = s["police_exit"]
            site["ov"].append(
                {
                    "k": "exit",
                    "mesh": drape_poly(pe["zone"], ground, 1.5, 0.09),
                    "line": np.round(np.asarray(pe["points"]) + [0, 0, 0.2], 3)
                    .ravel()
                    .tolist(),
                    "label": f"POLICE EXIT keep-clear (ASSUMED) · route {pe['length_ft']} ft · zone {pe['zone_area_sqft']:,} sq ft",
                    "note": pe["note"],
                    "at": np.asarray(pe["zone"]).mean(0).round(2).tolist(),
                }
            )
        if "hazard" in s:
            site["ov"].append(
                {"k": "hazard", "at": s["hazard"]["xy"], "label": s["hazard"]["text"]}
            )
        if "bands" in s:
            bd = s["bands"]
            for r_ft in bd["rings_ft"]:
                a_ = np.linspace(0, 2 * math.pi, 145)
                ring = np.column_stack(
                    [
                        bd["center"][0] + r_ft * FT * np.cos(a_),
                        bd["center"][1] + r_ft * FT * np.sin(a_),
                    ]
                )
                site["ov"].append(
                    {
                        "k": "ring",
                        "line": drape_line(ring, ground, 0.2).ravel().tolist(),
                        "label": f"{r_ft} ft",
                        "at": ring[110].round(2).tolist(),
                    }
                )
            site["ov"].append(
                {
                    "k": "note",
                    "at": [bd["center"][0], bd["center"][1] - 30],
                    "label": bd["note"]
                    + f" Given point is {bd['given_point_to_stony_brook_ft']} ft from the Stony Brook centreline.",
                }
            )
        if "bridge_corridor" in s:
            bc = s["bridge_corridor"]
            site["ov"].append(
                {
                    "k": "bridge",
                    "line": np.round(np.asarray(bc["points"]) + [0, 0, 1.0], 3)
                    .ravel()
                    .tolist(),
                    "label": f"Pedestrian bridge corridor (CALC. EST.) {bc['length_ft']} ft, {bc['water_width_ft']} ft over water",
                    "note": bc["note"],
                    "at": np.asarray(bc["points"])[len(bc["points"]) // 2][:2]
                    .round(2)
                    .tolist(),
                }
            )
        if "dike_candidate" in s:
            dk = s["dike_candidate"]
            p3 = np.asarray(dk["points"])
            site["ov"].append(
                {
                    "k": "dike",
                    "line": np.round(p3 + [0, 0, 0.3], 3).ravel().tolist(),
                    "mask": [int(m) for m in dk["embankment_mask"]],
                    "label": f"{dk['label']} · crest {dk['crest_z_ft_range'][0]}–{dk['crest_z_ft_range'][1]} ft NAVD88, median {dk['crest_height_above_pond_ft_median']} ft above pond ({dk['pond_surface_z_ft']} ft)",
                    "at": p3[np.argmax(p3[:, 2])][:2].round(2).tolist(),
                }
            )
        if "map_point_21_mill_st" in s:
            site["ov"].append(
                {
                    "k": "note",
                    "at": s["map_point_21_mill_st"],
                    "label": "21 Mill St (OSM house point) · parcel lines and the 13-ft strip NOT MAPPED",
                }
            )
        for ov in site["ov"]:
            if "at" in ov and len(ov["at"]) == 2:
                ov["at"] = [
                    ov["at"][0],
                    ov["at"][1],
                    round(float(ground.z(*ov["at"])[0]), 2),
                ]
        sites.append(site)
    D["sites"] = sites

    # mill roof planes
    D["roof"] = {
        "patches": [
            {
                "b": p["building"],
                "pl": p["plane"],
                "abc": p["abc"],
                "r": np.round(np.asarray(p["ring"]), 3).ravel().tolist(),
            }
            for p in J("mill_roof_patches.json")
        ],
        "buildings": MR["buildings"],
        "totals": MR.get("totals"),
        "claims": MR.get("claims"),
    }
    D["labels"] = labels

    tpl = open(os.path.join(HERE, "web", "viewer_template.html")).read()
    html = tpl.replace(
        "/*__DATA__*/null", json.dumps(D, separators=(",", ":")).replace("</", "<\\/")
    )
    if not a.bare:
        html = (
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
            + html
            + "\n</body>\n</html>\n"
        )
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write(html)
    print(f"wrote {a.out} ({len(html) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
