"""Download and pre-process the open data for a location model (UTM / NAVD88), per job config.

Generalised from Wilton's prepare_downtown.py: the DEM tiles, EPT project, Overture release,
NHD and USGS Structures files, centre and detail area now come from the job config.

Everything is written in Blender-local metres: x = E - E0, y = N - N0, z = NAVD88 (frame.py).
Every layer records its source, date and accuracy in meta.json; registration between layers is
measured, not assumed ("checks" in meta.json). Features named in the config's REDACT section
(security items at an airport) are dropped here, so no later output can carry them.

    python prepare_site.py --cache CACHE --work WORK --nhd NHD.gpkg --struct STRUCT.gpkg
"""

import argparse
import json
import math
import os
import sys

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
sys.path.insert(0, HERE)
import fetch  # noqa: E402
import frame  # noqa: E402

TEX_RES = 0.5  # ground texture m/px (about the lidar point spacing)
log = fetch.log


# --------------------------------------------------------------------------- helpers


def lonlat_box(box, pad=0.0):
    xs = [box[0] - pad, box[2] + pad, box[0] - pad, box[2] + pad]
    ys = [box[1] - pad, box[1] - pad, box[3] + pad, box[3] + pad]
    lat, lon = frame.geodetic(np.array(xs), np.array(ys))
    return (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))


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


def read_gpkg(path, layer, bbox_ll, cols, where=None):
    try:
        meta, _, geom, fields = pyogrio.raw.read(
            path,
            layer=layer,
            bbox=bbox_ll,
            columns=cols,
            return_fids=False,
            where=where,
        )
    except Exception as e:  # layer missing
        log(f"  {os.path.basename(path)}:{layer}: {e}")
        return []
    names = list(meta["fields"])
    out = []
    for i, wkb in enumerate(geom):
        if wkb is None:
            continue
        g = shapely.force_2d(shapely.from_wkb(wkb))
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
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if np.isnan(v) else float(v)
    if isinstance(v, float) and math.isnan(v):
        return None
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


def redacted(text, cat, R):
    t = (text or "").lower()
    words = set(t.replace("-", " ").replace("/", " ").split())
    return cat in R["place_categories"] or any(
        (k in words) if len(k) <= 4 else (k in t) for k in R["place_name_terms"]
    )


# --------------------------------------------------------------------------- DEM


def dem_tiles(box, url):
    """10 km UTM tiles touching box (local); tile xNNyMMM spans E NN*10 km.., N (MMM-1)*10 km..."""
    e0, e1 = box[0] + frame.E0, box[2] + frame.E0
    n0, n1 = box[1] + frame.N0, box[3] + frame.N0
    xs = range(int(e0 // 10000), int(e1 // 10000) + 1)
    ys = range(int(n0 // 10000) + 1, int(n1 // 10000) + 2)
    return [url.format(x=x, y=y) for x in xs for y in ys]


def read_dem(box, step, cache, name, url):
    """DEM samples at cell centres on a grid of `step` m covering box (local coords)."""
    path = os.path.join(cache, f"dem_{name}.npz")
    if os.path.exists(path):
        d = np.load(path)
        return (
            d["z"],
            float(d["x0"]),
            float(d["y0"]),
            float(d["step"]),
            list(d["tiles"]),
        )
    nx = int(round((box[2] - box[0]) / step))
    ny = int(round((box[3] - box[1]) / step))
    z = np.full((ny, nx), np.nan, dtype=np.float64)
    e_min, n_max = box[0] + frame.E0, box[3] + frame.N0
    used = []
    for tile in dem_tiles(box, url):
        try:
            src = rasterio.open("/vsicurl/" + tile)
        except rasterio.errors.RasterioIOError:
            log(f"  dem tile missing: {tile.rsplit('/', 1)[-1]}")
            continue
        with src:
            left, bottom, right, top = src.bounds
            ix0 = max(0, int(math.ceil((left - e_min) / step)))
            ix1 = min(nx, int(math.floor((right - e_min) / step)))
            iy0 = max(0, int(math.ceil((n_max - top) / step)))
            iy1 = min(ny, int(math.floor((n_max - bottom) / step)))
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            used.append(tile.rsplit("/", 1)[-1])
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
    np.savez_compressed(path, z=z, x0=x0, y0=y0, step=step, tiles=np.array(used))
    log(
        f"  dem {name}: {z.shape}, {np.nanmin(z):.2f}..{np.nanmax(z):.2f} m NAVD88, "
        f"nan {int(np.isnan(z).sum())}, tiles {used}"
    )
    return z, x0, y0, step, used


class Grid:
    def __init__(self, z, x0, y0, step):
        self.z, self.x0, self.y0, self.step = z, x0, y0, step

    def at(self, x, y):
        c = (np.atleast_1d(x) - self.x0) / self.step
        r = (self.y0 - np.atleast_1d(y)) / self.step
        return ndimage.map_coordinates(self.z, [r, c], order=1, mode="nearest")


def lidar_local(ll):
    x, y = frame.local(ll["lat"], ll["lon"])
    return np.column_stack([x, y, ll["z_navd88"]])


def fetch_lidar_coarse(bbox_ll, cache, base, budget=12_000_000):
    """EPT points down to the deepest level that keeps the total under `budget` (overview)."""
    path = os.path.join(cache, "lidar_coarse.npz")
    if os.path.exists(path):
        return dict(np.load(path))
    import concurrent.futures as cf
    import io

    import laspy

    x0, y0 = fetch.lonlat_to_merc(bbox_ll[0], bbox_ll[1])
    x1, y1 = fetch.lonlat_to_merc(bbox_ll[2], bbox_ll[3])
    info = fetch.get(base + "ept.json").json()
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
        for key, count in fetch.get(f"{base}ept-hierarchy/{h}.json").json().items():
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
        las = laspy.read(io.BytesIO(fetch.get(f"{base}ept-data/{key}.laz").content))
        x, y = np.asarray(las.x), np.asarray(las.y)
        m = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
        return np.column_stack(
            [x[m], y[m], np.asarray(las.z)[m], np.asarray(las.classification)[m]]
        )

    with cf.ThreadPoolExecutor(16) as ex:
        pts = np.concatenate([c for c in ex.map(load, keys) if len(c)])
    lon, lat = fetch.merc_to_lonlat(pts[:, 0], pts[:, 1])
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


# --------------------------------------------------------------------------- buildings


def lidar_buildings(footprints, p, cls, nret, ground):
    """LiDAR roof points on footprints: unclassified/building, 2-60 m above ground, single return
    inside a footprint; vegetation = above ground and away from every footprint."""
    hag = p[:, 2] - ground.at(p[:, 0], p[:, 1])
    above = np.isin(cls, (1, 6)) & (hag > 2.0) & (hag < 60.0)
    union = shapely.union_all([poly for _, poly in footprints])
    shapely.prepare(union)
    near = union.buffer(1.5)
    shapely.prepare(near)
    in_fp = np.zeros(len(p), bool)
    near_fp = np.zeros(len(p), bool)
    in_fp[above] = shapely.contains_xy(union, p[above, 0], p[above, 1])
    near_fp[above] = shapely.contains_xy(near, p[above, 0], p[above, 1])
    is_bldg = above & in_fp & (nret == 1)
    is_veg = above & ~near_fp & (cls != 6)
    return is_bldg, is_veg, hag


ROOF_CELL = 0.5  # m, roof surface raster
ROOF_SNAP = 0.25  # m, vertices this close to a roof level are set to it
ROOF_LEVEL_MIN_M2 = 40.0  # a roof level must cover at least this much area
ROOF_EDGE_IN = 1.0  # m, edge vertices read the roof this far inside the outline


def roof_grid(poly, pts_b):
    """0.5 m lidar roof surface over the footprint: per-cell max, 3x3 median, gaps and the
    strip outside the lidar edge filled from the nearest roof cell, then near-flat areas
    snapped to their roof level (the dominant heights). Returns (g, x0, y0, snapped)."""
    from scipy import ndimage

    minx, miny, maxx, maxy = poly.bounds
    nx = int(np.ceil((maxx - minx) / ROOF_CELL)) + 3
    ny = int(np.ceil((maxy - miny) / ROOF_CELL)) + 3
    x0, y0 = minx - ROOF_CELL, miny - ROOF_CELL
    ix = np.clip(((pts_b[:, 0] - x0) / ROOF_CELL).astype(int), 0, nx - 1)
    iy = np.clip(((pts_b[:, 1] - y0) / ROOF_CELL).astype(int), 0, ny - 1)
    g = np.full((ny, nx), -np.inf)
    np.maximum.at(g, (iy, ix), pts_b[:, 2])
    hole = ~np.isfinite(g)
    _, (fi, fj) = ndimage.distance_transform_edt(hole, return_indices=True)
    g = g[fi, fj]
    g = ndimage.median_filter(g, size=3, mode="nearest")
    # roof levels: histogram peaks of the filtered surface inside the footprint
    cx = x0 + (np.arange(nx) + 0.5) * ROOF_CELL
    cy = y0 + (np.arange(ny) + 0.5) * ROOF_CELL
    gx, gy = np.meshgrid(cx, cy)
    inside = shapely.contains_xy(poly, gx, gy) & ~hole
    zs = g[inside]
    snap = np.zeros(g.shape, bool)
    if len(zs):
        bins = np.arange(zs.min() - 0.05, zs.max() + 0.15, 0.1)
        h, e = np.histogram(zs, bins)
        cell_m2 = ROOF_CELL**2
        levels = []
        for k in np.argsort(-h):
            if h[k] * cell_m2 < ROOF_LEVEL_MIN_M2:
                break
            zc = 0.5 * (e[k] + e[k + 1])
            if all(abs(zc - lv) > 2 * ROOF_SNAP for lv in levels):
                near = zs[np.abs(zs - zc) <= ROOF_SNAP]
                levels.append(float(np.median(near)))
        if levels:
            lv = np.asarray(levels)
            d = np.abs(g[..., None] - lv)
            k = d.argmin(-1)
            snap = d.min(-1) <= ROOF_SNAP
            g = np.where(snap, lv[k], g)
    return g, x0, y0, snap


def roof_surface(poly, pts_b, xy):
    """Roof z at xy, read from roof_grid()."""
    g, x0, y0, _ = roof_grid(poly, pts_b)
    ny, nx = g.shape
    # vertices within ROOF_EDGE_IN of the outline read the roof 1 m in: a parapet is
    # thinner than the 1 m mesh and would otherwise draw as a zigzag band (parapet
    # heights are measured from the raw lidar in hvac_routes.py, not from this mesh)
    xy = xy.copy()
    inward = poly.buffer(-ROOF_EDGE_IN)
    if not inward.is_empty and inward.geom_type == "Polygon":
        out = np.nonzero(~shapely.contains_xy(inward, xy[:, 0], xy[:, 1]))[0]
        ext = inward.exterior
        for i in out:
            q = ext.interpolate(ext.project(shapely.Point(xy[i])))
            xy[i] = (q.x, q.y)
    jx = np.clip(((xy[:, 0] - x0) / ROOF_CELL).astype(int), 0, nx - 1)
    jy = np.clip(((xy[:, 1] - y0) / ROOF_CELL).astype(int), 0, ny - 1)
    return g[jy, jx]


BLOCK_STEP = 0.5  # m, heights off the roof levels are rounded to this
BLOCK_TOL = 0.6  # m, outline simplification (shared edges kept by coverage_simplify)
BLOCK_MIN_M2 = 2.0  # m^2, smaller pieces merge into their neighbour


def roof_blocks(poly, pts_b, base_z, top):
    """Display roof as flat blocks (LOD2-style): each roof level and each roof object is
    a polygon traced from roof_grid() and extruded from base_z, so steps between levels
    are vertical with straight edges instead of a staircased 1 m grid."""
    import rasterio.features
    from rasterio.transform import Affine
    from scipy import ndimage

    g, x0, y0, snap = roof_grid(poly, pts_b)
    q = np.where(snap, g, np.round(g / BLOCK_STEP) * BLOCK_STEP)
    q = np.clip(q, base_z + 2.2, top + 0.5)
    # pieces under BLOCK_MIN_M2 take the value of their largest neighbour region
    vals, inv = np.unique(np.round(q, 2), return_inverse=True)
    lab = inv.reshape(q.shape)
    min_cells = BLOCK_MIN_M2 / ROOF_CELL**2
    for _ in range(3):
        changed = False
        for v in range(len(vals)):
            comp, n = ndimage.label(lab == v)
            if not n:
                continue
            sizes = ndimage.sum(np.ones_like(comp), comp, np.arange(1, n + 1))
            for c in np.nonzero(sizes < min_cells)[0] + 1:
                m = comp == c
                ring = ndimage.binary_dilation(m) & ~m
                if ring.any():
                    lab[m] = np.bincount(lab[ring]).argmax()
                    changed = True
        if not changed:
            break
    tr = Affine(ROOF_CELL, 0, x0, 0, ROOF_CELL, y0)  # row 0 is the south edge
    mask = np.ones(lab.shape, bool)
    geoms, zs = [], []
    for geom, v in rasterio.features.shapes(
        lab.astype(np.int32), mask=mask, transform=tr
    ):
        geoms.append(shapely.geometry.shape(geom))
        zs.append(float(vals[int(v)]))
    if not geoms:
        return []
    geoms = shapely.coverage_simplify(np.asarray(geoms), BLOCK_TOL)
    blocks = []
    for gm, z in zip(geoms, zs):
        gm = shapely.make_valid(gm).intersection(poly)
        for part in getattr(gm, "geoms", [gm]):
            if part.geom_type != "Polygon" or part.area < BLOCK_MIN_M2:
                continue
            blocks.append(
                {
                    "rings": [coords(part.exterior)]
                    + [coords(r) for r in part.interiors],
                    "z": round(z, 3),
                }
            )
    return blocks


def prism_mesh(blocks, base_z):
    """Vertices, faces and per-face kind (0 roof, 1 wall) for blocks extruded to base_z."""
    V, F, K = [], [], []
    for b in blocks:
        poly = shapely.Polygon(b["rings"][0], b["rings"][1:])
        o = len(V)
        rings = [np.asarray(r)[:-1] for r in b["rings"]]
        top = np.concatenate(rings)
        V += [(x, y, b["z"]) for x, y in top]
        look = {(round(x, 4), round(y, 4)): o + i for i, (x, y) in enumerate(top)}
        for t in shapely.constrained_delaunay_triangles(poly).geoms:
            c = np.asarray(t.exterior.coords)[:3]
            ids = [look.get((round(x, 4), round(y, 4))) for x, y in c]
            if None not in ids:
                F.append(ids)
                K.append(0)
        s = o
        for r in rings:
            n = len(r)
            bot = len(V)
            V += [(x, y, base_z - 0.3) for x, y in r]
            for i in range(n):
                j = (i + 1) % n
                F += [[s + i, s + j, bot + j], [s + i, bot + j, bot + i]]
                K += [1, 1]
            s += n
    return np.asarray(V, float), np.asarray(F, int), np.asarray(K, np.uint8)


def roof_mesh(poly, pts_b, base_z):
    """Footprint triangulated with a 1 m interior grid; z from the roof surface raster."""
    if len(pts_b) >= 8 and len(pts_b) >= 0.15 * poly.area:
        p90, p97 = np.percentile(pts_b[:, 2], [90, 97])
        top = float(min(p97, p90 + 1.0))
        lidar_ok = True
    else:
        top, lidar_ok = None, False
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
    z = None
    if lidar_ok:
        z = roof_surface(poly, pts_b, allp)
        z = np.clip(z, base_z + 2.2, top + 0.5)
    return (
        allp,
        z,
        faces,
        len(ring),
        [len(x) for x in parts[1 : 1 + len(poly.interiors)]],
        top,
        lidar_ok,
    )


# --------------------------------------------------------------------------- centre


def resolve_center(C, struct_path, cache):
    """Centre from the data, never typed in (config CENTER_RESOLVE). Returns a report dict."""
    R = C.CENTER_RESOLVE
    seed = R["seed_struct"]
    rows = read_gpkg(
        struct_path,
        "Struct_Point",
        None,
        ["name", "address", "city", "zipcode", "ftype", "fcode"],
        where=f"zipcode LIKE '{seed['zipcode']}%'",
    )
    hits = [r for r in rows if seed["name_contains"].lower() in str(r["name"]).lower()]
    if not hits:
        raise RuntimeError("seed structure not found; give a search box in the config")
    lon = np.mean([h["geometry"].x for h in hits])
    lat = np.mean([h["geometry"].y for h in hits])
    pad = R["seed_pad_deg"]
    seed_box = (lon - pad, lat - pad, lon + pad, lat + pad)
    rel = C.DATASETS["overture_release"]
    sc = os.path.join(cache, "seed")
    os.makedirs(sc, exist_ok=True)
    places = fetch.overture_features(
        fetch.fetch_overture("places", "place", seed_box, sc, rel),
        ["names", "addresses", "basic_category", "confidence"],
    )
    blds = fetch.overture_features(
        fetch.fetch_overture("buildings", "building", seed_box, sc, rel),
        ["id", "names", "class", "num_floors"],
    )
    tb = [
        b
        for b in blds
        if (fetch.name_of(b["names"]) or "").lower()
        == R["terminal_building"]["name"].lower()
    ]
    if not tb:
        raise RuntimeError("terminal building not found in Overture buildings")
    term_ll = max(tb, key=lambda b: b["geometry"].area)["geometry"]
    term = to_local_geom(term_ll)
    tenants = [
        p
        for p in places
        if R["overture_address"] in json.dumps(p.get("addresses"), default=str).lower()
    ]
    inside = [p for p in tenants if term_ll.contains(p["geometry"])]
    named = [
        p
        for p in places
        if (fetch.name_of(p["names"]) or "") in R["overture_place_names"]
    ]
    c = term.centroid
    lat_c, lon_c = frame.geodetic(c.x, c.y)

    def dist_ft(g):
        q = to_local_geom(g)
        return round(c.distance(q) / 0.3048, 0), round(term.distance(q) / 0.3048, 0)

    usgs = []
    for h in hits:
        d, de = dist_ft(h["geometry"])
        usgs.append(
            {
                "name": h["name"],
                "address": h["address"],
                "lat": round(h["geometry"].y, 6),
                "lon": round(h["geometry"].x, 6),
                "to_center_ft": d,
                "to_terminal_edge_ft": de,
            }
        )
    ov = []
    for p in named:
        d, de = dist_ft(p["geometry"])
        ov.append(
            {
                "name": fetch.name_of(p["names"]),
                "lat": round(p["geometry"].y, 6),
                "lon": round(p["geometry"].x, 6),
                "to_center_ft": d,
                "to_terminal_edge_ft": de,
            }
        )
    tl = np.array([[p["geometry"].x, p["geometry"].y] for p in inside])
    tmed = np.median(tl, axis=0) if len(tl) else None
    report = {
        "method": "centroid of the Overture 'Terminal Building' footprint (OSM), which contains "
        f"{len(inside)} of the {len(tenants)} Overture places addressed '1 Airport Rd'",
        "lat": round(float(lat_c), 6),
        "lon": round(float(lon_c), 6),
        "local_xy": [round(c.x, 2), round(c.y, 2)],
        "terminal_area_sqft": round(term.area / 0.3048**2),
        "terminal_floors_osm": max(tb, key=lambda b: b["geometry"].area).get(
            "num_floors"
        ),
        "overture_airport_places": ov,
        "overture_tenant_median": (
            {
                "lat": round(float(tmed[1]), 6),
                "lon": round(float(tmed[0]), 6),
                "to_center_ft": dist_ft(shapely.Point(tmed))[0],
            }
            if tmed is not None
            else None
        ),
        "usgs_structures_on_airport": usgs,
        "usgs_note": "USGS National Structures has no terminal point; its only airport feature "
        "is the ARFF fire station, so the USGS check is a distance to that station.",
    }
    return report, term


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--nhd", required=True)
    ap.add_argument("--struct", required=True)
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    C = frame.load_config(a.config)
    D = C.DATASETS
    R = C.REDACT
    rel = D["overture_release"]
    os.makedirs(a.cache, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)

    log("Centre ...")
    center, term = resolve_center(C, a.struct, a.cache)
    log("  centre", center["lat"], center["lon"], center["local_xy"])
    cx, cy = center["local_xy"]
    r = frame.OVERVIEW_RADIUS
    ov = (cx - r, cy - r, cx + r, cy + r)
    ov_ll = lonlat_box(ov, 50)

    log("Overture ...")
    tables = {
        "building": fetch.fetch_overture("buildings", "building", ov_ll, a.cache, rel),
        "segment": fetch.fetch_overture(
            "transportation", "segment", ov_ll, a.cache, rel
        ),
        "place": fetch.fetch_overture("places", "place", ov_ll, a.cache, rel),
        "land_use": fetch.fetch_overture("base", "land_use", ov_ll, a.cache, rel),
        "infrastructure": fetch.fetch_overture(
            "base", "infrastructure", ov_ll, a.cache, rel
        ),
    }
    props = [
        "id", "names", "class", "subtype", "height", "num_floors", "basic_category",
        "sources", "addresses", "level", "is_underground",
    ]  # fmt: skip
    ov_feats = {k: fetch.overture_features(t, props) for k, t in tables.items()}

    # detail area: config footprints buffered by the detail radius
    anchors = [term]
    for sel in C.DETAIL["buildings"]:
        if "near_terminal_m" in sel:
            for f in ov_feats["building"]:
                if f.get("class") == sel["class"]:
                    g = to_local_geom(f["geometry"])
                    if g.distance(term) <= sel["near_terminal_m"] and g.area > 2000:
                        anchors.append(g)
    hull = shapely.union_all(anchors).buffer(frame.DETAIL_RADIUS)
    det = tuple(
        float(v)
        for v in (
            math.floor(hull.bounds[0]),
            math.floor(hull.bounds[1]),
            math.ceil(hull.bounds[2]),
            math.ceil(hull.bounds[3]),
        )
    )
    det_ll = lonlat_box(det, 30)
    log("overview box", [round(v) for v in ov], "detail box", det)
    meta = {
        "job": C.JOB,
        "crs": f"NAD83 / UTM zone 19N (EPSG:{frame.EPSG}), metres",
        "vertical": C.FRAME["vertical"],
        "origin": {"E0": frame.E0, "N0": frame.N0, "Z0": frame.Z0},
        "overview_box": ov,
        "detail_box": det,
        "center": center,
        "center_local": [cx, cy],
        "retrieved": D["retrieved"],
        "overture_release": rel,
        "layers": {},
        "checks": {},
        "redacted": {},
    }

    log("DEM ...")
    zd, x0, y0, st, td = read_dem(det, 1.0, a.cache, "detail", D["dem"]["tile_url"])
    zo, ox0, oy0, ost, to = read_dem(ov, 8.0, a.cache, "overview", D["dem"]["tile_url"])
    dem = Grid(zd, x0, y0, st)
    dem_ov = Grid(zo, ox0, oy0, ost)
    for nm, z_, x_, y_, s_ in (
        ("dem_detail.npz", zd, x0, y0, st),
        ("dem_overview.npz", zo, ox0, oy0, ost),
    ):
        np.savez_compressed(
            os.path.join(a.work, nm), z=z_.astype(np.float32), x0=x_, y0=y_, step=s_
        )
    meta["layers"]["terrain"] = {
        "source": f"USGS 3DEP 1 m DEM, project {D['dem']['project']}, tiles {sorted(set(td + to))} (s3://prd-tnm StagedProducts)",
        "detail": "native 1 m cells inside the detail box",
        "overview": "8 m block average out to the overview radius",
        "nan_cells_detail": int(np.isnan(zd).sum()),
        "accuracy": "QL2 3DEP spec: <=10 cm RMSEz non-vegetated; horizontal = 1 m cell",
        "retrieved": D["retrieved"],
    }

    log("Lidar (detail, all returns) ...")
    ll = fetch.fetch_lidar(det_ll, a.cache, D["ept"])
    project = str(ll["project"])
    p = lidar_local(ll)
    cls, inten, nret, ret = ll["cls"], ll["intensity"], ll["nret"], ll["ret"]
    keep = (
        (p[:, 0] >= det[0])
        & (p[:, 0] <= det[2])
        & (p[:, 1] >= det[1])
        & (p[:, 1] <= det[3])
    )
    p, cls, inten, nret, ret = p[keep], cls[keep], inten[keep], nret[keep], ret[keep]
    np.savez_compressed(
        os.path.join(a.work, "lidar_detail.npz"),
        p=p.astype(np.float64),
        cls=cls,
        inten=inten.astype(np.float32),
        nret=nret,
        ret=ret,
    )
    area = (det[2] - det[0]) * (det[3] - det[1])
    classes = {int(k): int(v) for k, v in zip(*np.unique(cls, return_counts=True))}
    meta["layers"]["lidar"] = {
        "source": f"USGS 3DEP lidar {project.rstrip('/').rsplit('/', 1)[-1]} (EPT, s3://usgs-lidar-public)",
        "points": len(p),
        "density_pts_m2": round(len(p) / area, 2),
        "classes": classes,
        "retrieved": D["retrieved"],
    }
    log(
        "  lidar classes", classes, "density", meta["layers"]["lidar"]["density_pts_m2"]
    )

    # ---- check 1: lidar ground vs DEM
    g = cls == 2
    gs = np.random.default_rng(0).choice(
        np.nonzero(g)[0], size=min(200000, int(g.sum())), replace=False
    )
    best = None
    for dx in np.arange(-1.5, 1.51, 0.25):
        for dy in np.arange(-1.5, 1.51, 0.25):
            rr = p[gs, 2] - dem.at(p[gs, 0] + dx, p[gs, 1] + dy)
            rms = float(np.sqrt(np.mean(np.clip(rr, -2, 2) ** 2)))
            if best is None or rms < best[0]:
                best = (rms, dx, dy)
    r0 = p[gs, 2] - dem.at(p[gs, 0], p[gs, 1])
    meta["checks"]["lidar_ground_vs_dem"] = {
        "median_dz_m": round(float(np.median(r0)), 3),
        "rms_dz_m_clipped2m": round(
            float(np.sqrt(np.mean(np.clip(r0, -2, 2) ** 2))), 3
        ),
        "best_shift_m": [float(best[1]), float(best[2])],
        "rms_at_best": round(best[0], 3),
        "samples": len(gs),
    }
    log("  check lidar vs DEM:", meta["checks"]["lidar_ground_vs_dem"])

    # ---- footprints and their registration against lidar roofs
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
    cand = np.isin(cls, (1, 6)) & (hag_all > 2.5) & (nret == 1)
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
    shift = (float(best[1]), float(best[2]))
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

    if apply_shift:
        fps = [(f, shapely.affinity.translate(q, osm_dx, osm_dy)) for f, q in fps]
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
        base_z = float(np.nanmin(dem.at(ring[:, 0], ring[:, 1])))
        allp, z, faces, n_ring, holes, top, ok = roof_mesh(poly, pin, base_z)
        blocks = roof_blocks(poly, pin, base_z, top) if ok else []
        bv, bf, bk = prism_mesh(blocks, base_z) if blocks else ([], [], [])
        buildings.append(
            {
                "id": f.get("id"),
                "name": fetch.name_of(f.get("names")),
                "class": f.get("class"),
                "subtype": f.get("subtype"),
                "num_floors": f.get("num_floors"),
                "overture_height": f.get("height"),
                "footprint": coords(poly.exterior),
                "holes": [coords(rg) for rg in poly.interiors],
                "area_m2": round(poly.area, 1),
                "base_z": round(base_z, 3),
                "top_z": round(top, 3) if top else None,
                "lidar_roof": ok,
                "n_roof_pts": len(pin),
                "roof_xy": allp.round(3).tolist(),
                "roof_z": z.round(3).tolist() if z is not None else None,
                "roof_faces": faces,
                "n_ring": n_ring,
                "hole_rings": holes,
                "blocks": blocks,
                # display mesh of the blocks: vertices, triangles, kind (0 roof, 1 wall)
                "block_mesh": {
                    "v": np.round(bv, 3).tolist() if len(bv) else [],
                    "f": np.asarray(bf).tolist(),
                    "k": np.asarray(bk).tolist(),
                },
            }
        )
    json.dump(
        jsonable(buildings), open(os.path.join(a.work, "buildings_detail.json"), "w")
    )
    meta["layers"]["buildings_detail"] = {
        "source": f"Overture Maps {rel.split('/')[-1]} footprints (OSM-derived) + roof shape/height from 2019 lidar single returns",
        "count": len(buildings),
        "with_lidar_roof": sum(b["lidar_roof"] for b in buildings),
        "accuracy": "roof z: lidar (+-0.15 m typical); outline: OSM trace, registration shift applied per checks",
        "no_lidar": "buildings without 2019 lidar roof returns get NO height (outline only) - not guessed",
    }

    log("Buildings (overview, coarse lidar heights) ...")
    cl = fetch_lidar_coarse(ov_ll, a.cache, project)
    cp = lidar_local(cl)
    chag = cp[:, 2] - dem_ov.at(cp[:, 0], cp[:, 1])
    cpa = cp[np.isin(cl["cls"], (1, 6)) & (chag > 2.5) & (chag < 60)]
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
        base = float(np.nanmin(dem_ov.at(ring[:, 0], ring[:, 1])))
        top = float(np.percentile(pin[:, 2], 85)) if len(pin) >= 3 else None
        ovb.append(
            {
                "footprint": coords(poly.exterior),
                "base_z": round(base, 2),
                "top_z": round(top, 2) if top else None,
                "n_pts": len(pin),
            }
        )
    json.dump(ovb, open(os.path.join(a.work, "buildings_overview.json"), "w"))
    meta["layers"]["buildings_overview"] = {
        "source": f"Overture footprints + lidar EPT depth<={int(cl['max_depth'])} (subsampled)",
        "count": len(ovb),
        "with_height": sum(1 for b in ovb if b["top_z"]),
        "accuracy": "context only; height = 85th pct of sparse returns; no height where <3 returns (not guessed)",
    }

    log("Trees ...")
    res = 0.5
    nx, ny = int((det[2] - det[0]) / res), int((det[3] - det[1]) / res)
    c = np.floor((p[:, 0] - det[0]) / res).astype(int)
    rr = np.floor((det[3] - p[:, 1]) / res).astype(int)
    ok = is_veg & (c >= 0) & (c < nx) & (rr >= 0) & (rr < ny)
    chm = np.zeros((ny, nx))
    np.maximum.at(chm, (rr[ok], c[ok]), hag[ok])
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
        "count": len(trees),
        "accuracy": "tree top position +-1 m, height +-0.5 m; crown size CALCULATED ESTIMATE (0.18 x height + 1.2 m)",
    }

    log("Roads, sidewalks, airfield ...")
    roads, n_red = [], 0
    for f in ov_feats["segment"]:
        gl = osm_local(f["geometry"])
        if gl.is_empty or not gl.intersects(ov_circle):
            continue
        nm = fetch.name_of(f.get("names"))
        if nm and redacted(nm, "", R):
            nm = None
            n_red += 1
        roads.append(
            {
                "subtype": f.get("subtype"),
                "class": f.get("class"),
                "name": nm,
                "line": coords(gl) if gl.geom_type == "LineString" else None,
            }
        )
    json.dump(roads, open(os.path.join(a.work, "roads.json"), "w"))
    meta["layers"]["roads"] = {
        "source": f"Overture Maps {rel.split('/')[-1]} transportation segments (OSM-derived)",
        "count": len(roads),
        "accuracy": "centrelines, OSM trace (typ. 1-3 m); widths are NOT measured",
    }
    meta["redacted"]["road_names"] = n_red

    areas = []
    n_red = 0
    for k in ("land_use", "infrastructure"):
        for f in ov_feats[k]:
            cl_ = f.get("class") or ""
            sub_ = f.get("subtype") or ""
            if (
                cl_ in R["infrastructure_classes"]
                or cl_ in R["aeroway_classes"]
                or sub_ == "barrier"
            ):
                n_red += 1
                continue
            gl = osm_local(f["geometry"])
            if gl.is_empty or not gl.intersects(ov_circle):
                continue
            if gl.geom_type in ("Polygon", "MultiPolygon", "LineString"):
                areas.append(
                    {
                        "theme": k,
                        "class": cl_,
                        "subtype": sub_,
                        "name": None,
                        "geom": shapely.geometry.mapping(gl),
                    }
                )
    json.dump(jsonable(areas), open(os.path.join(a.work, "areas.json"), "w"))
    meta["redacted"]["infrastructure_features"] = n_red
    meta["layers"]["airfield_landuse"] = {
        "source": f"Overture Maps {rel.split('/')[-1]} base land_use + infrastructure (OSM-derived): aprons, runways, taxiways, parking",
        "count": len(areas),
        "accuracy": "OSM trace; security items (gates, barriers, fences, cameras) removed by design",
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
    meta["layers"]["water"] = {
        "source": "USGS NHD High Resolution HU8 01070006 GPKG (s3://prd-tnm StagedProducts/Hydrography)",
        "names_in_area": sorted(
            {w["name"] for k in water for w in water[k] if w["name"]}
        ),
        "counts": {k: len(v) for k, v in water.items()},
    }

    log("Structures, places ...")
    structs, n_red = [], 0
    for f in read_gpkg(
        a.struct, "Struct_Point", det_ll, ["name", "address", "ftype", "fcode"]
    ):
        if redacted(f.get("name"), "", R):
            n_red += 1
            continue
        structs.append(
            {k: jsonable(v) for k, v in f.items() if k != "geometry"}
            | {"xy": coords(to_local_geom(f["geometry"]))}
        )
    places = []
    for f in ov_feats["place"]:
        nm = fetch.name_of(f.get("names"))
        cat = f.get("basic_category") or ""
        addr = json.dumps(f.get("addresses"), default=str)
        if redacted(f"{nm} {addr}", cat, R):
            n_red += 1
            continue
        xy = coords(osm_local(f["geometry"]))
        if det[0] < xy[0] < det[2] and det[1] < xy[1] < det[3]:
            places.append({"name": nm, "category": cat, "xy": xy})
    json.dump(
        jsonable({"structures": structs, "places": places}),
        open(os.path.join(a.work, "points.json"), "w"),
    )
    meta["redacted"]["points"] = n_red
    meta["checks"]["center"] = {
        "lidar_ground_z_m": round(float(dem.at(cx, cy)[0]), 2),
    }

    log("Ground texture (lidar intensity composite) ...")
    tx_n, ty_n = int((det[2] - det[0]) / TEX_RES), int((det[3] - det[1]) / TEX_RES)
    c = np.floor((p[:, 0] - det[0]) / TEX_RES).astype(int)
    rr = np.floor((det[3] - p[:, 1]) / TEX_RES).astype(int)
    ok = (
        (c >= 0)
        & (c < tx_n)
        & (rr >= 0)
        & (rr < ty_n)
        & np.isin(cls, (2, 9))
        & (ret == nret)
    )
    acc = np.zeros((ty_n, tx_n))
    cnt = np.zeros((ty_n, tx_n))
    np.add.at(acc, (rr[ok], c[ok]), inten[ok])
    np.add.at(cnt, (rr[ok], c[ok]), 1)
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
        "primary": 10, "secondary": 9, "tertiary": 8, "residential": 7, "unclassified": 6.5,
        "service": 5, "footway": 1.8, "sidewalk": 1.8, "path": 1.5, "pedestrian": 3, "steps": 1.5,
    }  # fmt: skip
    paved, foot = [], []
    for rd in roads:
        if rd["subtype"] != "road" or not rd["line"]:
            continue
        ln = shapely.LineString(rd["line"])
        w = road_w.get(rd["class"] or "", 5)
        is_foot = rd["class"] in ("footway", "sidewalk", "path", "pedestrian", "steps")
        (foot if is_foot else paved).append(ln.buffer(w / 2, cap_style="flat"))
    for ar in areas:
        if ar["class"] in (
            "parking",
            "apron",
            "runway",
            "taxiway",
            "surface",
            "parking_lot",
        ):
            gg = shapely.geometry.shape(ar["geom"])
            if gg.geom_type in ("Polygon", "MultiPolygon"):
                paved.append(gg)
    wat = [
        shapely.geometry.shape(w["geom"])
        for k in ("areas", "waterbodies")
        for w in water[k]
    ]
    wat += [
        shapely.geometry.shape(w["geom"]).buffer(3)
        for w in water["flowlines"]
        if w["name"]
    ]
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
        "source": "2019 lidar intensity (ground returns, 0.5 m) tinted by OSM roads/parking/apron and NHD water",
        "accuracy": "NOT an orthophoto. Replace with GRANIT ortho (drape_orthophoto.py)",
    }
    json.dump(jsonable(meta), open(os.path.join(a.work, "meta.json"), "w"), indent=1)
    log("done")


if __name__ == "__main__":
    main()
