"""Download and pre-process data for the Wilton #1976 downtown v2 model (UTM 19N / NAVD88).

Everything is written in Blender-local metres: x = E - E0, y = N - N0, z = NAVD88 (frame.py).
Every layer records its source, date and accuracy in meta.json; registration between layers is
measured, not assumed (see "checks" in meta.json).

    python prepare_downtown.py --cache CACHE --work WORK [--nhd NHD.gpkg] [--struct STRUCT.gpkg]
"""

import argparse
import concurrent.futures as cf
import io
import json
import math
import os
import sys

import laspy
import numpy as np
import pyogrio
import rasterio
import shapely
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import frame  # noqa: E402
import prepare_data as v1  # noqa: E402  (tested downloaders: Overture range reads, EPT lidar)

DEM_TILE = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/"
    "NH_Coastal_2019_B19/TIFF/USGS_1M_19_x27y{}_NH_Coastal_2019_B19.tif"
)
RETRIEVED = "2026-10-20"
TEX_RES = 0.5  # ground texture m/px (about the lidar point spacing)


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------- areas


def areas():
    cx, cy = frame.local(*frame.CENTER)
    cx, cy = float(cx), float(cy)
    r = frame.OVERVIEW_RADIUS
    ov = (cx - r, cy - r, cx + r, cy + r)
    pts = np.array([frame.local(s["lat"], s["lon"]) for s in frame.SITES], dtype=float)
    d = frame.DETAIL_RADIUS
    det = (
        math.floor(pts[:, 0].min() - d),
        math.floor(pts[:, 1].min() - d),
        math.ceil(pts[:, 0].max() + d),
        math.ceil(pts[:, 1].max() + d),
    )
    return (cx, cy), ov, det


def lonlat_box(box, pad=0.0):
    xs = [box[0] - pad, box[2] + pad, box[0] - pad, box[2] + pad]
    ys = [box[1] - pad, box[1] - pad, box[3] + pad, box[3] + pad]
    lat, lon = frame.geodetic(np.array(xs), np.array(ys))
    return (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))


# --------------------------------------------------------------------------- DEM


def read_dem(box, step, cache, name):
    """DEM samples at cell centres on a grid of `step` m covering box (local coords)."""
    path = os.path.join(cache, f"dem_{name}.npz")
    if os.path.exists(path):
        d = np.load(path)
        return d["z"], float(d["x0"]), float(d["y0"]), float(d["step"])
    nx = int(round((box[2] - box[0]) / step))
    ny = int(round((box[3] - box[1]) / step))
    z = np.full((ny, nx), np.nan, dtype=np.float64)
    e_min, n_max = box[0] + frame.E0, box[3] + frame.N0
    for ytile in ("475", "476"):
        with rasterio.open("/vsicurl/" + DEM_TILE.format(ytile)) as src:
            left, bottom, right, top = src.bounds
            ix0 = max(0, int(math.ceil((left - e_min) / step)))
            ix1 = min(nx, int(math.floor((right - e_min) / step)))
            iy0 = max(0, int(math.ceil((n_max - top) / step)))
            iy1 = min(ny, int(math.floor((n_max - bottom) / step)))
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            win = from_bounds(
                e_min + ix0 * step,
                n_max - iy1 * step,
                e_min + ix1 * step,
                n_max - iy0 * step,
                src.transform,
            )
            data = src.read(
                1,
                window=win,
                out_shape=(iy1 - iy0, ix1 - ix0),
                resampling=Resampling.bilinear if step <= 1.0 else Resampling.average,
            ).astype(np.float64)
            data[data < -1000] = np.nan
            sub = z[iy0:iy1, ix0:ix1]
            np.copyto(sub, data, where=np.isnan(sub))
    x0 = box[0] + step / 2
    y0 = box[3] - step / 2  # row 0 = north
    np.savez_compressed(path, z=z, x0=x0, y0=y0, step=step)
    log(
        f"  dem {name}: {z.shape}, {np.nanmin(z):.2f}..{np.nanmax(z):.2f} m NAVD88, nan {np.isnan(z).sum()}"
    )
    return z, x0, y0, step


class Grid:
    def __init__(self, z, x0, y0, step):
        self.z, self.x0, self.y0, self.step = z, x0, y0, step

    def at(self, x, y):
        c = (np.atleast_1d(x) - self.x0) / self.step
        r = (self.y0 - np.atleast_1d(y)) / self.step
        return ndimage.map_coordinates(self.z, [r, c], order=1, mode="nearest")


# --------------------------------------------------------------------------- lidar


def lidar_local(ll):
    x, y = frame.local(ll["lat"], ll["lon"])
    return np.column_stack([x, y, ll["z_navd88"]])


def fetch_lidar_coarse(bbox_ll, cache, budget=18_000_000):
    """EPT points down to the deepest level that keeps the total under `budget` (overview heights)."""
    path = os.path.join(cache, "lidar_coarse.npz")
    if os.path.exists(path):
        return dict(np.load(path))
    x0, y0 = v1.lonlat_to_merc(bbox_ll[0], bbox_ll[1])
    x1, y1 = v1.lonlat_to_merc(bbox_ll[2], bbox_ll[3])
    base = v1.EPT_DATASETS[
        1
    ]  # NH_Coastal_2_2019 holds Wilton (NH_Coastal_1_2019 had 0 points here)
    info = v1.get(base + "ept.json").json()
    b = info["bounds"]
    span = b[3] - b[0]

    def hits(key):
        d, x, y, _ = map(int, key.split("-"))
        s = span / 2**d
        return (
            b[0] + x * s <= x1
            and b[0] + (x + 1) * s >= x0
            and b[1] + y * s <= y1
            and b[1] + (y + 1) * s >= y0
        )

    todo, nodes = ["0-0-0-0"], []
    while todo:
        h = todo.pop()
        for key, count in v1.get(f"{base}ept-hierarchy/{h}.json").json().items():
            if hits(key):
                if count == -1:
                    todo.append(key)
                elif count > 0:
                    nodes.append((int(key.split("-")[0]), key, count))
    by_depth = {}
    for d, _, c in nodes:
        by_depth[d] = by_depth.get(d, 0) + c
    total, max_d = 0, 0
    for d in sorted(by_depth):
        if total + by_depth[d] > budget:
            break
        total += by_depth[d]
        max_d = d
    keys = [k for d, k, _ in nodes if d <= max_d]

    def load(key):
        las = laspy.read(io.BytesIO(v1.get(f"{base}ept-data/{key}.laz").content))
        x, y = np.asarray(las.x), np.asarray(las.y)
        m = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
        return np.column_stack(
            [x[m], y[m], np.asarray(las.z)[m], np.asarray(las.classification)[m]]
        )

    with cf.ThreadPoolExecutor(16) as ex:
        pts = np.concatenate([c for c in ex.map(load, keys) if len(c)])
    lon, lat = v1.merc_to_lonlat(pts[:, 0], pts[:, 1])
    out = {
        "lon": lon,
        "lat": lat,
        "z_navd88": pts[:, 2],
        "cls": pts[:, 3].astype(np.uint8),
        "max_depth": max_d,
    }
    np.savez_compressed(path, **out)
    log(f"  coarse lidar: depth<={max_d}, {len(pts)} points ({len(keys)} nodes)")
    return out


# --------------------------------------------------------------------------- vectors


def to_local_geom(g):
    def tf(c):
        x, y = frame.local(c[:, 1], c[:, 0])
        return np.column_stack([x, y])

    return shapely.transform(g, tf)


def coords(g):
    if g.geom_type == "Point":
        return [round(g.x, 3), round(g.y, 3)]
    if g.geom_type in ("LineString", "LinearRing"):
        return [[round(x, 3), round(y, 3)] for x, y in g.coords]
    if g.geom_type == "Polygon":
        return [coords(g.exterior)] + [coords(r) for r in g.interiors]
    return [coords(p) for p in g.geoms]


def read_gpkg(path, layer, bbox_ll, cols):
    try:
        meta, _, geom, fields = pyogrio.raw.read(
            path, layer=layer, bbox=bbox_ll, columns=cols, return_fids=False
        )
    except Exception as e:  # layer missing
        log(f"  {os.path.basename(path)}:{layer}: {e}")
        return []
    names = list(meta["fields"])
    out = []
    for i, wkb in enumerate(geom):
        if wkb is None:
            continue
        g = shapely.from_wkb(wkb)
        g = shapely.force_2d(g)
        out.append(
            {
                "geometry": g,
                **{
                    n: (fields[j][i] if fields[j] is not None else None)
                    for j, n in enumerate(names)
                },
            }
        )
    return out


def jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf8", "replace")
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (np.datetime64, np.ndarray)) or not isinstance(
        v, (str, int, float, bool, type(None))
    ):
        return str(v)
    return v


# --------------------------------------------------------------------------- buildings


def lidar_buildings(footprints, p, cls, nret, ground, res=0.5):
    """LiDAR roofs on footprints (same method as v1, in UTM-local metres)."""
    hag = p[:, 2] - ground.at(p[:, 0], p[:, 1])
    above = (cls == 1) & (hag > 2.0) & (hag < 45.0)
    union = shapely.union_all([poly for _, poly in footprints])
    shapely.prepare(union)
    near = union.buffer(1.5)
    shapely.prepare(near)
    in_fp = np.zeros(len(p), bool)
    near_fp = np.zeros(len(p), bool)
    in_fp[above] = shapely.contains_xy(union, p[above, 0], p[above, 1])
    near_fp[above] = shapely.contains_xy(near, p[above, 0], p[above, 1])
    is_bldg = above & in_fp & (nret == 1)
    is_veg = above & ~near_fp
    return is_bldg, is_veg, hag


def roof_mesh(poly, pts_b, base_z, ground):
    """Footprint triangulated with a 1 m interior grid; z from a robust local max of roof points."""
    from scipy.spatial import cKDTree

    if len(pts_b) >= 8 and len(pts_b) >= 0.15 * poly.area:
        p90, p97 = np.percentile(pts_b[:, 2], [90, 97])
        top = float(min(p97, p90 + 1.0))
        tree = cKDTree(pts_b[:, :2])
        lidar_ok = True
    else:
        top, tree, lidar_ok = None, None, False
    ring = np.asarray(shapely.segmentize(poly.exterior, 1.0).coords)[:-1]
    parts = [ring] + [
        np.asarray(shapely.segmentize(r, 1.0).coords)[:-1] for r in poly.interiors
    ]
    minx, miny, maxx, maxy = poly.bounds
    gx, gy = np.meshgrid(
        np.arange(minx + 0.5, maxx, 1.0), np.arange(miny + 0.5, maxy, 1.0)
    )
    cand = np.column_stack([gx.ravel(), gy.ravel()])
    inner = poly.buffer(-0.5)
    if len(cand) and not inner.is_empty:
        parts.append(cand[shapely.contains_xy(inner, cand[:, 0], cand[:, 1])])
    allp = np.concatenate(parts)
    tri = shapely.delaunay_triangles(shapely.MultiPoint(allp))
    lookup = {(round(x, 4), round(y, 4)): i for i, (x, y) in enumerate(allp)}
    faces = []
    for t in tri.geoms:
        c = np.asarray(t.exterior.coords)[:3]
        if poly.contains(shapely.Point(c.mean(0))):
            faces.append([lookup[(round(x, 4), round(y, 4))] for x, y in c])
    if lidar_ok:
        inward = poly.buffer(-0.35)
        sample = allp.copy()
        if not inward.is_empty:
            outside = ~shapely.contains_xy(inward, allp[:, 0], allp[:, 1])
            for i in np.nonzero(outside)[0]:
                q = inward.exterior.interpolate(
                    inward.exterior.project(shapely.Point(allp[i]))
                )
                sample[i] = (q.x, q.y)
        idx = tree.query_ball_point(sample, r=1.0)
        z = np.array(
            [np.percentile(pts_b[j, 2], 90) if len(j) >= 2 else np.nan for j in idx]
        )
        if np.isnan(z).any():
            _, nn = tree.query(sample[np.isnan(z)])
            z[np.isnan(z)] = pts_b[nn, 2]
        z = np.clip(z, base_z + 2.2, top + 0.5)
    else:
        z = None
    return (
        allp,
        z,
        faces,
        len(ring),
        [len(x) for x in parts[1 : 1 + len(poly.interiors)]],
        top,
        lidar_ok,
    )


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--nhd", required=True)
    ap.add_argument("--struct", required=True)
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)
    (cx, cy), ov, det = areas()
    ov_ll, det_ll = lonlat_box(ov, 50), lonlat_box(det, 30)
    log("overview box", [round(v) for v in ov], "detail box", det)
    meta = {
        "crs": "NAD83 / UTM zone 19N (EPSG:26919), metres",
        "vertical": "NAVD88 metres (USGS 3DEP DEM / lidar)",
        "origin": {"E0": frame.E0, "N0": frame.N0, "Z0": frame.Z0},
        "overview_box": ov,
        "detail_box": det,
        "center_local": [cx, cy],
        "retrieved": RETRIEVED,
        "layers": {},
        "checks": {},
    }

    log("DEM ...")
    zd, x0, y0, st = read_dem(det, 1.0, a.cache, "detail")
    zo, ox0, oy0, ost = read_dem(ov, 8.0, a.cache, "overview")
    dem = Grid(zd, x0, y0, st)
    dem_ov = Grid(zo, ox0, oy0, ost)
    np.savez_compressed(
        os.path.join(a.work, "dem_detail.npz"),
        z=zd.astype(np.float32),
        x0=x0,
        y0=y0,
        step=st,
    )
    np.savez_compressed(
        os.path.join(a.work, "dem_overview.npz"),
        z=zo.astype(np.float32),
        x0=ox0,
        y0=oy0,
        step=ost,
    )
    meta["layers"]["terrain"] = {
        "source": "USGS 3DEP 1 m DEM, project NH_Coastal_2019_B19, tiles x27y475/x27y476 (s3://prd-tnm StagedProducts)",
        "detail": "native 1 m cells inside the detail box",
        "overview": "8 m block average out to 2 mi",
        "accuracy": "QL2 3DEP spec: <=10 cm RMSEz non-vegetated (check project metadata); horizontal = 1 m cell",
        "retrieved": RETRIEVED,
    }

    log("Overture ...")
    tables = {
        "building": v1.fetch_overture("buildings", "building", ov_ll, a.cache),
        "segment": v1.fetch_overture("transportation", "segment", ov_ll, a.cache),
        "place": v1.fetch_overture("places", "place", det_ll, a.cache),
        "address": v1.fetch_overture("addresses", "address", det_ll, a.cache),
        "land_use": v1.fetch_overture("base", "land_use", det_ll, a.cache),
        "infrastructure": v1.fetch_overture("base", "infrastructure", det_ll, a.cache),
    }
    props = [
        "id",
        "names",
        "class",
        "subtype",
        "height",
        "num_floors",
        "basic_category",
        "number",
        "street",
        "unit",
        "postcode",
        "sources",
        "address_levels",
    ]
    ov_feats = {k: v1.overture_features(t, props) for k, t in tables.items()}

    log("Lidar (detail, all returns) ...")
    ll = v1.fetch_lidar(det_ll, a.cache)
    p = lidar_local(ll)
    cls, inten, nret, ret = ll["cls"], ll["intensity"], ll["nret"], ll["ret"]
    keep = (
        (p[:, 0] >= det[0])
        & (p[:, 0] <= det[2])
        & (p[:, 1] >= det[1])
        & (p[:, 1] <= det[3])
    )
    p, cls, inten, nret, ret = p[keep], cls[keep], inten[keep], nret[keep], ret[keep]
    area = (det[2] - det[0]) * (det[3] - det[1])
    meta["layers"]["lidar"] = {
        "source": "USGS 3DEP lidar NH_Coastal_2_2019 (EPT, s3://usgs-lidar-public), classes 1,2,7,9,17,18,20",
        "points": int(len(p)),
        "density_pts_m2": round(len(p) / area, 2),
        "retrieved": RETRIEVED,
        "note": "only ground (2) is classified; building vs vegetation split here by footprints + return count",
    }

    # ---- check 1: lidar ground vs DEM (horizontal registration)
    g = cls == 2
    gs = np.random.default_rng(0).choice(
        np.nonzero(g)[0], size=min(200000, g.sum()), replace=False
    )
    best = None
    for dx in np.arange(-1.5, 1.51, 0.25):
        for dy in np.arange(-1.5, 1.51, 0.25):
            r = p[gs, 2] - dem.at(p[gs, 0] + dx, p[gs, 1] + dy)
            rms = float(np.sqrt(np.mean(np.clip(r, -2, 2) ** 2)))
            if best is None or rms < best[0]:
                best = (rms, dx, dy)
    r0 = p[gs, 2] - dem.at(p[gs, 0], p[gs, 1])
    meta["checks"]["lidar_ground_vs_dem"] = {
        "median_dz_m": round(float(np.median(r0)), 3),
        "rms_dz_m_clipped2m": round(
            float(np.sqrt(np.mean(np.clip(r0, -2, 2) ** 2))), 3
        ),
        "best_shift_m": [best[1], best[2]],
        "rms_at_best": round(best[0], 3),
        "samples": int(len(gs)),
    }
    log("  check lidar vs DEM:", meta["checks"]["lidar_ground_vs_dem"])

    # ---- footprints (Overture, OSM-derived) and their registration against lidar roofs
    det_box = shapely.box(*det)
    ov_circle = shapely.Point(cx, cy).buffer(frame.OVERVIEW_RADIUS, 64)
    fps = []
    for f in ov_feats["building"]:
        gl = to_local_geom(f["geometry"])
        for poly in (
            [gl] if gl.geom_type == "Polygon" else list(getattr(gl, "geoms", []))
        ):
            if (
                poly.geom_type == "Polygon"
                and poly.area >= 6
                and poly.intersects(ov_circle)
            ):
                poly = shapely.make_valid(poly.simplify(0.15))
                if poly.geom_type == "Polygon":
                    fps.append((f, poly))
    det_fps = [(f, q) for f, q in fps if q.intersects(det_box)]
    hag_all = p[:, 2] - dem.at(p[:, 0], p[:, 1])
    cand = (cls == 1) & (hag_all > 2.5) & (nret == 1)
    union = shapely.union_all([q for _, q in det_fps])
    best = None
    sub = np.nonzero(cand)[0]
    for dx in np.arange(-2.0, 2.01, 0.25):
        for dy in np.arange(-2.0, 2.01, 0.25):
            u = shapely.affinity.translate(union, dx, dy) if (dx or dy) else union
            shapely.prepare(u)
            n = int(shapely.contains_xy(u, p[sub, 0], p[sub, 1]).sum())
            if best is None or n > best[0]:
                best = (n, dx, dy)
    n0 = int(shapely.contains_xy(union, p[sub, 0], p[sub, 1]).sum())
    shift = (best[1], best[2])
    gain = (best[0] - n0) / max(n0, 1)
    apply_shift = math.hypot(*shift) >= 0.5 and gain > 0.02
    meta["checks"]["osm_footprints_vs_lidar"] = {
        "best_shift_m": list(shift),
        "roof_points_inside_at_0": n0,
        "at_best": best[0],
        "gain_pct": round(100 * gain, 1),
        "applied": apply_shift,
        "method": "grid search +-2 m / 0.25 m maximising single-return >2.5 m lidar points inside OSM footprints",
    }
    log("  check footprints vs lidar:", meta["checks"]["osm_footprints_vs_lidar"])
    osm_dx, osm_dy = shift if apply_shift else (0.0, 0.0)

    def osm_local(geom):
        gl = to_local_geom(geom)
        return shapely.affinity.translate(gl, osm_dx, osm_dy) if apply_shift else gl

    fps = (
        [(f, shapely.affinity.translate(q, osm_dx, osm_dy)) for f, q in fps]
        if apply_shift
        else fps
    )
    det_fps = [(f, q) for f, q in fps if q.intersects(det_box)]

    log("Buildings (detail, lidar roofs) ...")
    is_bldg, is_veg, hag = lidar_buildings(det_fps, p, cls, nret, dem)
    pb = p[is_bldg]
    buildings = []
    for f, poly in det_fps:
        minx, miny, maxx, maxy = poly.bounds
        sel = (
            (pb[:, 0] >= minx)
            & (pb[:, 0] <= maxx)
            & (pb[:, 1] >= miny)
            & (pb[:, 1] <= maxy)
        )
        pin = pb[sel]
        if len(pin):
            pin = pin[shapely.contains_xy(poly, pin[:, 0], pin[:, 1])]
        ring = np.asarray(shapely.segmentize(poly.exterior, 1.0).coords)[:-1]
        base_z = float(dem.at(ring[:, 0], ring[:, 1]).min())
        allp, z, faces, n_ring, holes, top, ok = roof_mesh(poly, pin, base_z, dem)
        if not ok:
            z = None
        buildings.append(
            {
                "id": f.get("id"),
                "name": v1.name_of(f.get("names")),
                "class": f.get("class"),
                "overture_height": f.get("height"),
                "footprint": coords(poly.exterior),
                "holes": [coords(r) for r in poly.interiors],
                "area_m2": round(poly.area, 1),
                "base_z": round(base_z, 3),
                "top_z": round(top, 3) if top else None,
                "lidar_roof": ok,
                "n_roof_pts": int(len(pin)),
                "roof_xy": allp.round(3).tolist(),
                "roof_z": z.round(3).tolist() if z is not None else None,
                "roof_faces": faces,
                "n_ring": n_ring,
                "hole_rings": holes,
            }
        )
    json.dump(buildings, open(os.path.join(a.work, "buildings_detail.json"), "w"))
    meta["layers"]["buildings_detail"] = {
        "source": "Overture Maps 2026-09-23.1 footprints (OSM-derived) + roof shape/height from 2019 lidar single returns",
        "count": len(buildings),
        "with_lidar_roof": sum(b["lidar_roof"] for b in buildings),
        "accuracy": "roof z: lidar (+-0.15 m typical); outline: OSM trace, registration shift applied per checks",
        "no_lidar": "buildings without 2019 lidar roof returns get NO height (drawn as outline only) - not guessed",
    }

    log("Buildings (overview, coarse lidar heights) ...")
    cl = fetch_lidar_coarse(ov_ll, a.cache)
    cp = lidar_local(cl)
    chag = cp[:, 2] - dem_ov.at(cp[:, 0], cp[:, 1])
    cabove = (cl["cls"] == 1) & (chag > 2.5) & (chag < 45)
    cpa = cp[cabove]
    ovb = []
    for f, poly in fps:
        if poly.intersects(det_box):
            continue
        minx, miny, maxx, maxy = poly.bounds
        sel = (
            (cpa[:, 0] >= minx)
            & (cpa[:, 0] <= maxx)
            & (cpa[:, 1] >= miny)
            & (cpa[:, 1] <= maxy)
        )
        pin = cpa[sel]
        if len(pin):
            pin = pin[shapely.contains_xy(poly, pin[:, 0], pin[:, 1])]
        ring = np.asarray(poly.exterior.coords)[:-1]
        base = float(dem_ov.at(ring[:, 0], ring[:, 1]).min())
        top = float(np.percentile(pin[:, 2], 85)) if len(pin) >= 3 else None
        ovb.append(
            {
                "footprint": coords(poly.exterior),
                "base_z": round(base, 2),
                "top_z": round(top, 2) if top else None,
                "n_pts": int(len(pin)),
            }
        )
    json.dump(ovb, open(os.path.join(a.work, "buildings_overview.json"), "w"))
    meta["layers"]["buildings_overview"] = {
        "source": f"Overture footprints + lidar NH_Coastal_2_2019 EPT depth<={int(cl['max_depth'])} (subsampled)",
        "count": len(ovb),
        "with_height": sum(1 for b in ovb if b["top_z"]),
        "accuracy": "context only; height = 85th pct of sparse returns; no height where <3 returns (not guessed)",
    }

    log("Trees ...")
    res = 0.5
    nx, ny = int((det[2] - det[0]) / res), int((det[3] - det[1]) / res)
    c = np.floor((p[:, 0] - det[0]) / res).astype(int)
    r = np.floor((det[3] - p[:, 1]) / res).astype(int)
    ok = is_veg & (c >= 0) & (c < nx) & (r >= 0) & (r < ny)
    chm = np.zeros((ny, nx))
    np.maximum.at(chm, (r[ok], c[ok]), hag[ok])
    density = ndimage.uniform_filter((chm > 2.0).astype(float), size=9)
    chm_s = ndimage.gaussian_filter(chm, 0.8)
    peaks = (
        (chm_s == ndimage.maximum_filter(chm_s, size=9))
        & (chm_s >= 5.0)
        & (density >= 0.35)
    )
    pr, pc = np.nonzero(peaks)
    th = chm_s[pr, pc]
    tx = det[0] + (pc + 0.5) * res
    ty = det[3] - (pr + 0.5) * res
    trees = np.column_stack(
        [tx, ty, dem.at(tx, ty), th, np.clip(1.2 + 0.18 * th, 2.0, 7.5)]
    )
    np.save(os.path.join(a.work, "trees.npy"), trees.astype(np.float32))
    meta["layers"]["trees"] = {
        "source": "2019 lidar canopy height model (0.5 m), local maxima >=5 m",
        "count": int(len(trees)),
        "accuracy": "tree top position +-1 m, height +-0.5 m; crown size CALCULATED ESTIMATE (0.18 x height + 1.2 m)",
    }

    log("Roads, sidewalks ...")
    roads = []
    for f in ov_feats["segment"]:
        gl = osm_local(f["geometry"])
        if gl.is_empty or not gl.intersects(ov_circle):
            continue
        roads.append(
            {
                "subtype": f.get("subtype"),
                "class": f.get("class"),
                "name": v1.name_of(f.get("names")),
                "line": coords(gl) if gl.geom_type == "LineString" else None,
            }
        )
    json.dump(roads, open(os.path.join(a.work, "roads.json"), "w"))
    meta["layers"]["roads"] = {
        "source": "Overture Maps 2026-09-23.1 transportation segments (OSM-derived)",
        "count": len(roads),
        "accuracy": "centrelines, OSM trace (typ. 1-3 m); widths are NOT measured",
    }

    log("NHD water ...")
    water = {"flowlines": [], "areas": [], "waterbodies": []}
    for key, layer, cols in (
        ("flowlines", "NHDFlowline", ["gnis_name", "ftype", "fcode"]),
        ("areas", "NHDArea", ["gnis_name", "ftype", "fcode"]),
        ("waterbodies", "NHDWaterbody", ["gnis_name", "ftype", "fcode"]),
    ):
        for f in read_gpkg(a.nhd, layer, ov_ll, cols):
            gl = to_local_geom(f["geometry"])
            if gl.is_empty or not gl.intersects(ov_circle):
                continue
            water[key].append(
                {
                    "name": f.get("gnis_name"),
                    "ftype": jsonable(f.get("ftype")),
                    "fcode": jsonable(f.get("fcode")),
                    "geom": shapely.geometry.mapping(gl),
                }
            )
    json.dump(jsonable(water), open(os.path.join(a.work, "water.json"), "w"))
    names = sorted({w["name"] for k in water for w in water[k] if w["name"]})
    meta["layers"]["water"] = {
        "source": "USGS NHD High Resolution HU8 01070006 GPKG (s3://prd-tnm StagedProducts/Hydrography)",
        "names_in_area": names,
        "counts": {k: len(v) for k, v in water.items()},
        "accuracy": "NHD high-res (1:24k or better); sluiceway/dike NOT in NHD - see missing list",
    }
    log("  NHD names:", names)

    log("Structures, places, addresses ...")
    structs = []
    struct_layer = "Struct_Point"
    for f in read_gpkg(a.struct, struct_layer, det_ll, None):
        gl = to_local_geom(f["geometry"])
        structs.append(
            {k: jsonable(v) for k, v in f.items() if k != "geometry"}
            | {"xy": coords(gl)}
        )
    places = [
        {
            "name": v1.name_of(f.get("names")),
            "category": f.get("basic_category"),
            "xy": coords(osm_local(f["geometry"])),
        }
        for f in ov_feats["place"]
    ]
    addrs = [
        {
            "number": f.get("number"),
            "street": f.get("street"),
            "unit": f.get("unit"),
            "sources": [s.get("dataset") for s in (f.get("sources") or [])],
            "xy": coords(to_local_geom(f["geometry"])),
        }
        for f in ov_feats["address"]
    ]
    json.dump(
        jsonable({"structures": structs, "places": places, "addresses": addrs}),
        open(os.path.join(a.work, "points.json"), "w"),
    )

    # ---- site coordinate checks
    def nearest(items, pred, sx, sy):
        best = None
        for it in items:
            if pred(it):
                d = math.hypot(it["xy"][0] - sx, it["xy"][1] - sy)
                if best is None or d < best[0]:
                    best = (d, it)
        return best

    def addr(num, street):
        return lambda it: (
            str(it.get("number") or "") == num
            and street.lower() in str(it.get("street") or "").lower()
        )

    def sname(*keys):
        return lambda it: any(k.lower() in json.dumps(it).lower() for k in keys)

    checks = {
        "S1_PoliceLot": [
            ("address 7 Burns Hill Rd", addrs, addr("7", "burns hill")),
            ("USGS structure: police", structs, sname("police")),
            ("Overture place: police", places, sname("police")),
        ],
        "S2_MainStLot": [
            ("address 42 Main St (Town Hall)", addrs, addr("42", "main")),
            ("USGS structure: town hall", structs, sname("town hall", "town office")),
            (
                "Overture place: Town Hall / Town of Wilton",
                places,
                sname("town hall", "town of wilton", "town clerk"),
            ),
        ],
        "S3_Library": [
            ("address 7 Forest Rd", addrs, addr("7", "forest")),
            ("USGS structure: library", structs, sname("library")),
            ("Overture place: library", places, sname("library")),
        ],
        "S4_Mill": [
            ("address 21 Mill St", addrs, addr("21", "mill")),
            ("address 1 Riverside Way", addrs, addr("1", "riverside")),
            (
                "Overture place: Chillybears / Label / Multi-Color",
                places,
                sname("chilly", "label", "multi-color", "multicolor"),
            ),
        ],
    }
    site_checks = {}
    for s in frame.SITES:
        sx, sy = (float(v) for v in frame.local(s["lat"], s["lon"]))
        rows = []
        for label, items, pred in checks[s["key"]]:
            n = nearest(items, pred, sx, sy)
            rows.append(
                {
                    "check": label,
                    "found": bool(n),
                    "distance_m": round(n[0], 1) if n else None,
                    "distance_ft": round(n[0] / 0.3048, 0) if n else None,
                    "xy": n[1]["xy"] if n else None,
                    "detail": {
                        k: n[1].get(k)
                        for k in ("name", "number", "street", "category", "sources")
                        if n and k in n[1]
                    },
                }
            )
        site_checks[s["key"]] = {
            "given": [round(sx, 2), round(sy, 2)],
            "ground_z": round(float(dem.at(sx, sy)[0]), 2),
            "rows": rows,
        }
        log(
            f"  {s['key']}: "
            + "; ".join(f"{r['check']}: {r['distance_m']} m" for r in rows)
        )
    meta["site_checks"] = site_checks

    log("Ground texture (lidar intensity composite) ...")
    tx_n, ty_n = int((det[2] - det[0]) / TEX_RES), int((det[3] - det[1]) / TEX_RES)
    c = np.floor((p[:, 0] - det[0]) / TEX_RES).astype(int)
    r = np.floor((det[3] - p[:, 1]) / TEX_RES).astype(int)
    ok = (
        (c >= 0)
        & (c < tx_n)
        & (r >= 0)
        & (r < ty_n)
        & np.isin(cls, (2, 9))
        & (ret == nret)
    )
    acc = np.zeros((ty_n, tx_n))
    cnt = np.zeros((ty_n, tx_n))
    np.add.at(acc, (r[ok], c[ok]), inten[ok])
    np.add.at(cnt, (r[ok], c[ok]), 1)
    img = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    holes = np.isnan(img)
    if holes.any():
        img = img[
            tuple(
                ndimage.distance_transform_edt(
                    holes, return_distances=False, return_indices=True
                )
            )
        ]
    img = ndimage.median_filter(img, size=3)
    lo, hi = np.percentile(img, [2, 98])
    t = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1)
    tf = from_origin(det[0], det[3], TEX_RES, TEX_RES)

    def mask(geoms):
        shapes = [(gg, 1) for gg in geoms if gg is not None and not gg.is_empty]
        if not shapes:
            return np.zeros((ty_n, tx_n), bool)
        return rasterize(
            shapes, out_shape=(ty_n, tx_n), transform=tf, fill=0, dtype="uint8"
        ).astype(bool)

    road_w = {
        "primary": 10,
        "secondary": 9,
        "tertiary": 8,
        "residential": 7,
        "unclassified": 6.5,
        "service": 5,
        "footway": 1.8,
        "sidewalk": 1.8,
        "path": 1.5,
        "pedestrian": 3,
        "steps": 1.5,
    }
    paved, foot = [], []
    for rd in roads:
        if rd["subtype"] != "road" or not rd["line"]:
            continue
        ln = shapely.LineString(rd["line"])
        w = road_w.get(rd["class"] or "", 5)
        (
            foot
            if rd["class"] in ("footway", "sidewalk", "path", "pedestrian", "steps")
            else paved
        ).append(ln.buffer(w / 2, cap_style="flat"))
    parking = []
    for f in ov_feats["land_use"] + ov_feats["infrastructure"]:
        if (f.get("class") or "") in (
            "parking",
            "parking_space",
            "surface",
            "parking_lot",
        ):
            gl = osm_local(f["geometry"])
            if gl.geom_type in ("Polygon", "MultiPolygon"):
                paved.append(gl)
                for pg in [gl] if gl.geom_type == "Polygon" else list(gl.geoms):
                    parking.append(coords(pg.exterior))
    json.dump(parking, open(os.path.join(a.work, "parking.json"), "w"))
    wat = []
    for k in ("areas", "waterbodies"):
        for w in water[k]:
            wat.append(shapely.geometry.shape(w["geom"]))
    for w in water["flowlines"]:
        if w["name"]:
            wat.append(shapely.geometry.shape(w["geom"]).buffer(3))
    m_paved, m_foot, m_water = mask(paved), mask(foot), mask(wat)
    tt = t[..., None]
    rgb = (
        np.array([0.30, 0.38, 0.20])
        + (np.array([0.55, 0.60, 0.38]) - np.array([0.30, 0.38, 0.20])) * tt
    )
    rgb = np.where(
        m_paved[..., None],
        np.array([0.17, 0.17, 0.18]) + np.array([0.58, 0.57, 0.52]) * tt**2.2,
        rgb,
    )
    rgb = np.where(
        m_foot[..., None], np.array([0.62, 0.61, 0.58]) * (0.8 + 0.3 * tt), rgb
    )
    rgb = np.where(
        m_water[..., None], np.array([0.16, 0.24, 0.26]) * (0.9 + 0.2 * tt), rgb
    )
    Image.fromarray((np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)).save(
        os.path.join(a.work, "ground_detail.png")
    )
    Image.fromarray((t * 255).astype(np.uint8)).save(
        os.path.join(a.work, "lidar_intensity.png")
    )
    meta["layers"]["ground_texture"] = {
        "source": "2019 lidar intensity (ground returns, 0.5 m) tinted by OSM roads/parking and NHD water",
        "accuracy": "NOT an orthophoto. Pavement markings visible where intensity shows them. Replace with GRANIT ortho (drape_orthophoto.py)",
    }
    json.dump(jsonable(meta), open(os.path.join(a.work, "meta.json"), "w"), indent=1)
    log("done")


if __name__ == "__main__":
    main()
