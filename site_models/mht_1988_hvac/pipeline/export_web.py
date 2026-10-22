"""Export a location model to a single-file browser viewer (three.js r147), driven by the job
config. Generalised from Wilton's export_web.py: the site content (units, routes, overlays,
facts, legend, layers) now comes from WORK/viewer_content.json, written by the job's analysis
module, and the tour from the job's web/tour.json with {placeholders} filled from it.

    python export_web.py --work WORK [--out ../web/<viewer_name>] [--bare]

Geometry stays in the model frame (UTM minus E0 / N0 m, NAVD88 m).
"""

import argparse
import base64
import io
import json
import os
import sys

import numpy as np
import shapely
from PIL import Image
from scipy.spatial import Delaunay

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frame  # noqa: E402

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


def build_tour(C, V, sites, ground, det):
    """Resolve tour.json stops: anchor "site:<key>" reuses the site's aerial camera; "overview"
    looks at the detail area. Narration may use {name} fields from viewer_content tour_vars."""
    spec = json.load(open(os.path.join(C.JOB_DIR, C.TOUR)))
    by_key = {s["key"]: s for s in sites}

    def gz(x, y):
        return round(float(ground.z(x, y)[0]), 2)

    cx, cy = (det[0] + det[2]) / 2, (det[1] + det[3]) / 2
    ov = {
        "target": [cx, cy, gz(cx, cy)],
        "camera": [cx - 330, cy - 480, gz(cx, cy) + 420],
        "park": [cx - 40, cy - 60, gz(cx - 40, cy - 60)],
    }
    stops = []
    for s in spec["stops"]:
        a = s["anchor"]
        if a.startswith("site:"):
            site = by_key[a.split(":", 1)[1]]
            px = site["center"][0] + 0.5 * (site["eye"][0] - site["center"][0])
            py = site["center"][1] + 0.5 * (site["eye"][1] - site["center"][1])
            res = {
                "target": site["center"],
                "camera": site["aerial"],
                "park": [round(px, 2), round(py, 2), gz(px, py)],
                "site": site["key"],
            }
        elif a == "overview":
            res = ov
        else:
            raise KeyError(f"tour.json: unknown anchor {a}")
        stops.append(
            {
                "id": s["id"],
                "title": s["title"],
                "narration": s["narration"].format(**V["tour_vars"]),
                **res,
            }
        )
    return stops


def zfill(p, ground, lift=0.0):
    """[x, y, z|None, ...] -> z from the ground where None."""
    p = list(p)
    for i in range(0, len(p), 3):
        if p[i + 2] is None:
            p[i + 2] = round(float(ground.z(p[i], p[i + 1])[0]) + lift, 3)
    return p


def site_features(V, ground):
    sites = []
    for s in V["sites"]:
        feats = []
        for f in s["features"]:
            f = dict(f)
            if f["t"] == "poly" and f.get("drape"):
                ring = np.asarray(f.pop("xy"))[:, :2]
                if np.allclose(ring[0], ring[-1]):
                    ring = ring[:-1]
                z = ground.z(ring[:, 0], ring[:, 1]) + 0.12
                f["p"] = np.round(np.column_stack([ring, z]), 3).ravel().tolist()
                f.pop("drape")
            elif "p" in f:
                f["p"] = zfill(f["p"], ground, 0.3)
            if f["t"] == "box":
                f["c"] = zfill(f["c"], ground)
            if f["t"] == "marker":
                f["at"] = zfill(f["at"], ground)
            if "la" in f:
                la = list(f["la"]) + ([None] if len(f["la"]) == 2 else [])
                if la[2] is None:
                    la[2] = round(float(ground.z(la[0], la[1])[0]) + 2.5, 2)
                f["la"] = la
            feats.append(f)
        s = dict(s, features=feats)
        if s["eye"][2] is None:
            s["eye"] = [
                s["eye"][0],
                s["eye"][1],
                round(float(ground.z(*s["eye"][:2])[0]) + 1.68, 2),
            ]
        sites.append(s)
    return sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument(
        "--bare",
        action="store_true",
        help="omit the document head (for publishing as a hosted page)",
    )
    a = ap.parse_args()
    C = frame.load_config(a.config)
    W = a.work
    out = a.out or os.path.join(C.JOB_DIR, "web", C.JOB["viewer_name"])
    J = lambda n: json.load(open(os.path.join(W, n)))  # noqa: E731
    meta, V = J("meta.json"), J("viewer_content.json")
    ground = Ground(W)
    det = meta["detail_box"]
    D = {
        "meta": {
            k: meta[k] for k in ("crs", "vertical", "origin", "retrieved", "checks")
        }
    }
    D["meta"]["layers"] = meta["layers"]

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
    extra = (
        J("buildings_extra.json")
        if os.path.exists(os.path.join(W, "buildings_extra.json"))
        else []
    )
    for b in J("buildings_detail.json") + extra:
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
                "h": round((b["top_z"] - b["base_z"]) / FT, 1)
                if "height_note" not in b
                else None,
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

    D["sites"] = site_features(V, ground)
    json.dump(
        D["sites"], open(os.path.join(W, "sites_resolved.json"), "w")
    )  # also read by build_blend.py
    D["overview"] = V["overview"]
    D["legend"], D["about"], D["layers"] = V["legend"], V["about"], V["layers"]
    D["ui"] = {k: C.VIEWER[k] for k in ("brand", "sub", "aria")}
    D["labels"] = labels
    D["tour"] = build_tour(C, V, D["sites"], ground, det)

    tpl = open(os.path.join(HERE, "viewer_template.html")).read()
    tpl = tpl.replace("/*__TITLE__*/", C.VIEWER["page_title"])
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
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(html)
    print(f"wrote {out} ({len(html) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
