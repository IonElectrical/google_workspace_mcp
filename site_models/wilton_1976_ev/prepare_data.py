"""Download and pre-process open data for the Wilton #1976 site models.

Sources (all free, no API key):
  * USGS 3DEP lidar point cloud, NH_Coastal 2019 (EPT on s3://usgs-lidar-public), classified
  * USGS 3DEP 1 m bare-earth DEM, NH_Coastal_2019_B19 tile x27y475 (s3://prd-tnm)
  * Overture Maps (s3://overturemaps-us-west-2): buildings, roads, places, infrastructure,
    land use and water - largely OpenStreetMap-derived

Output: one folder per site under --work containing numpy/json files that are already in
the Blosm 3D-Tiles frame for that site (see sites.py), consumed by build_site_blend.py.

Run with a normal Python 3.11+ that has: numpy scipy shapely pyproj pyarrow laspy lazrs
rasterio requests pillow
"""

import argparse
import concurrent.futures as cf
import io
import json
import math
import os
import xml.etree.ElementTree as ET

import laspy
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
import requests
import shapely
from PIL import Image
from pyproj import Transformer
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import box, mapping

import sites

OVERTURE = "https://overturemaps-us-west-2.s3.amazonaws.com"
OVERTURE_RELEASE = "release/2026-09-23.1"
EPT_DATASETS = [
    "https://usgs-lidar-public.s3.amazonaws.com/NH_Coastal_1_2019/",
    "https://usgs-lidar-public.s3.amazonaws.com/NH_Coastal_2_2019/",
]
DEM_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/"
    "NH_Coastal_2019_B19/TIFF/USGS_1M_19_x27y475_NH_Coastal_2019_B19.tif"
)
# NAVD88 -> WGS84 ellipsoid. Approximate GEOID18 separation for Wilton NH (+-1 m); the
# align_google_tiles text block in each .blend removes any residual once Google tiles exist.
GEOID_N = -28.4

GROUND_RES = 0.25  # metres per pixel for the ground texture
TERRAIN_STEP = 1.0  # metres between terrain vertices

session = requests.Session()


# --------------------------------------------------------------------------- helpers


def log(*args):
    print(*args, flush=True)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = session.get(url, timeout=120, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise


def merc_to_lonlat(x, y):
    r = 6378137.0
    lon = np.degrees(x / r)
    lat = np.degrees(2.0 * np.arctan(np.exp(y / r)) - math.pi / 2.0)
    return lon, lat


def lonlat_to_merc(lon, lat):
    r = 6378137.0
    return r * math.radians(lon), r * math.log(
        math.tan(math.pi / 4 + math.radians(lat) / 2)
    )


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests (for parquet footers/row groups)."""

    def __init__(self, url, size):
        self.url, self.size, self.pos = url, size, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = (
            off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        )
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        data = get(
            self.url, headers={"Range": f"bytes={self.pos}-{self.pos + n - 1}"}
        ).content
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def s3_list(base, prefix):
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    out, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        root = ET.fromstring(get(base + "/", params=params).content)
        for c in root.findall("s3:Contents", ns):
            out.append((c.find("s3:Key", ns).text, int(c.find("s3:Size", ns).text)))
        token_el = root.find("s3:NextContinuationToken", ns)
        if token_el is None:
            return out
        token = token_el.text


# --------------------------------------------------------------------------- Overture


def fetch_overture(theme, otype, bbox, cache):
    """Rows of one Overture type intersecting bbox=(minlon,minlat,maxlon,maxlat)."""
    path = os.path.join(cache, f"overture_{otype}.parquet")
    if os.path.exists(path):
        return pq.read_table(path)
    files = [
        (k, s)
        for k, s in s3_list(OVERTURE, f"{OVERTURE_RELEASE}/theme={theme}/type={otype}/")
        if k.endswith(".parquet")
    ]
    minx, miny, maxx, maxy = bbox

    def scan(item):
        key, size = item
        f = pq.ParquetFile(
            pa.PythonFile(HttpRangeFile(f"{OVERTURE}/{key}", size), mode="r")
        )
        md = f.metadata
        names = [md.schema.column(i).path for i in range(md.num_columns)]
        idx = {n: names.index(f"bbox.{n}") for n in ("xmin", "xmax", "ymin", "ymax")}
        hits = []
        for rg in range(md.num_row_groups):
            st = {n: md.row_group(rg).column(i).statistics for n, i in idx.items()}
            if any(s is None or not s.has_min_max for s in st.values()):
                hits.append(rg)
                continue
            if (
                st["xmin"].min <= maxx
                and st["xmax"].max >= minx
                and st["ymin"].min <= maxy
                and st["ymax"].max >= miny
            ):
                hits.append(rg)
        return key, size, hits

    tables = []
    with cf.ThreadPoolExecutor(16) as ex:
        for key, size, hits in ex.map(scan, files):
            if not hits:
                continue
            f = pq.ParquetFile(
                pa.PythonFile(HttpRangeFile(f"{OVERTURE}/{key}", size), mode="r")
            )
            t = f.read_row_groups(hits)
            b = t.column("bbox").combine_chunks()
            keep = (
                (np.asarray(b.field("xmin")) <= maxx)
                & (np.asarray(b.field("xmax")) >= minx)
                & (np.asarray(b.field("ymin")) <= maxy)
                & (np.asarray(b.field("ymax")) >= miny)
            )
            tables.append(t.filter(pa.array(keep)))
    table = pa.concat_tables(tables) if tables else None
    if table is None:
        raise RuntimeError(f"no Overture {otype} rows in bbox")
    pq.write_table(table, path)
    log(f"  overture {otype}: {table.num_rows} rows")
    return table


def overture_features(table, props):
    geoms = shapely.from_wkb(table.column("geometry").to_numpy(zero_copy_only=False))
    cols = {p: table.column(p).to_pylist() for p in props if p in table.column_names}
    out = []
    for i, g in enumerate(geoms):
        out.append({"geometry": g, **{p: v[i] for p, v in cols.items()}})
    return out


def name_of(names):
    return (names or {}).get("primary") if isinstance(names, dict) else None


# --------------------------------------------------------------------------- lidar (EPT)


def fetch_lidar(bbox, cache):
    path = os.path.join(cache, "lidar_points.npz")
    if os.path.exists(path):
        return dict(np.load(path))
    x0, y0 = lonlat_to_merc(bbox[0], bbox[1])
    x1, y1 = lonlat_to_merc(bbox[2], bbox[3])
    parts = []
    for base in EPT_DATASETS:
        info = get(base + "ept.json").json()
        b = info["bounds"]
        span = b[3] - b[0]

        def node_box(key):
            d, x, y, _z = map(int, key.split("-"))
            size = span / (2**d)
            return (
                b[0] + x * size,
                b[1] + y * size,
                b[0] + (x + 1) * size,
                b[1] + (y + 1) * size,
            )

        def hits(key):
            nx0, ny0, nx1, ny1 = node_box(key)
            return nx0 <= x1 and nx1 >= x0 and ny0 <= y1 and ny1 >= y0

        todo, data_keys = ["0-0-0-0"], []
        while todo:
            hkey = todo.pop()
            for key, count in get(f"{base}ept-hierarchy/{hkey}.json").json().items():
                if not hits(key):
                    continue
                if count == -1:
                    todo.append(key)
                elif count > 0:
                    data_keys.append(key)

        def load(key):
            las = laspy.read(io.BytesIO(get(f"{base}ept-data/{key}.laz").content))
            x, y = np.asarray(las.x), np.asarray(las.y)
            m = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
            return np.column_stack(
                [
                    x[m],
                    y[m],
                    np.asarray(las.z)[m],
                    np.asarray(las.intensity)[m].astype(np.float64),
                    np.asarray(las.classification)[m].astype(np.float64),
                    np.asarray(las.return_number)[m].astype(np.float64),
                    np.asarray(las.number_of_returns)[m].astype(np.float64),
                ]
            )

        with cf.ThreadPoolExecutor(16) as ex:
            chunks = [c for c in ex.map(load, data_keys) if len(c)]
        n = sum(len(c) for c in chunks)
        log(
            f"  lidar {base.rsplit('/', 2)[-2]}: {len(data_keys)} nodes, {n} points in bbox"
        )
        parts.extend(chunks)
    pts = np.concatenate(parts)
    lon, lat = merc_to_lonlat(pts[:, 0], pts[:, 1])
    out = {
        "lon": lon,
        "lat": lat,
        "z_navd88": pts[:, 2],
        "intensity": pts[:, 3],
        "cls": pts[:, 4].astype(np.uint8),
        "ret": pts[:, 5].astype(np.uint8),
        "nret": pts[:, 6].astype(np.uint8),
    }
    np.savez_compressed(path, **out)
    return out


# --------------------------------------------------------------------------- DEM


def fetch_dem(bbox, cache):
    path = os.path.join(cache, "dem_utm19.npz")
    if os.path.exists(path):
        d = np.load(path)
        return d["z"], tuple(d["transform"])
    to_utm = Transformer.from_crs(4326, 26919, always_xy=True)
    xs, ys = to_utm.transform(
        [bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]]
    )
    with rasterio.open("/vsicurl/" + DEM_URL) as src:
        win = (
            from_bounds(
                min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5, src.transform
            )
            .round_offsets()
            .round_lengths()
        )
        z = src.read(1, window=win).astype(np.float64)
        t = src.window_transform(win)
        nodata = src.nodata
    if nodata is not None:
        z[z == nodata] = np.nan
    transform = (t.a, t.b, t.c, t.d, t.e, t.f)
    np.savez_compressed(path, z=z, transform=np.array(transform))
    log(f"  dem window {z.shape}, z {np.nanmin(z):.1f}..{np.nanmax(z):.1f} m NAVD88")
    return z, transform


class DemSampler:
    def __init__(self, z, transform):
        self.z = z
        self.a, _, self.c, _, self.e, self.f = transform
        self.to_utm = Transformer.from_crs(4326, 26919, always_xy=True)

    def navd88(self, lat, lon):
        x, y = self.to_utm.transform(lon, lat)
        col = (np.asarray(x) - self.c) / self.a - 0.5
        row = (np.asarray(y) - self.f) / self.e - 0.5
        return ndimage.map_coordinates(self.z, [row, col], order=1, mode="nearest")


# --------------------------------------------------------------------------- per site


def grid_local(frame, half, step, z_guess):
    """Regular XY grid in the local frame and its lat/lon (z_guess only affects ~mm tilt)."""
    n = int(round(2 * half / step)) + 1
    xs = np.linspace(-half, half, n)
    gx, gy = np.meshgrid(xs, xs[::-1])  # row 0 = north
    lat, lon, _ = frame.to_geodetic(np.stack([gx, gy, np.full_like(gx, z_guess)], -1))
    return xs, gx, gy, lat, lon


def to_local_xy(frame, geom, z_guess):
    """Shapely geometry in lon/lat -> same geometry in local XY metres."""

    def tf(coords):
        c = np.asarray(coords)
        p = frame.from_geodetic(c[:, 1], c[:, 0], np.full(len(c), z_guess))
        return p[:, :2]

    return shapely.transform(geom, tf)


def rasterize(geoms, res, shape_hw, half):
    """Boolean mask of local-XY geometries on the ground texture grid (row 0 = north)."""
    from rasterio.features import rasterize as rio_rasterize
    from rasterio.transform import from_origin

    t = from_origin(-half, half, res, res)
    shapes = [(g, 1) for g in geoms if g is not None and not g.is_empty]
    if not shapes:
        return np.zeros(shape_hw, bool)
    return rio_rasterize(
        shapes, out_shape=shape_hw, transform=t, fill=0, dtype="uint8"
    ).astype(bool)


def build_site(site, lidar, dem, ov, work):
    out = os.path.join(work, site["key"])
    os.makedirs(out, exist_ok=True)
    frame = sites.BlosmFrame(site["lat"], site["lon"])
    half = sites.RADIUS_M
    z_guess = (
        float(
            np.nanmedian(dem.navd88(np.array([site["lat"]]), np.array([site["lon"]])))
        )
        + GEOID_N
    )

    # ---- terrain grid (1 m), ellipsoidal heights, in the Blosm frame
    xs, gx, gy, lat, lon = grid_local(frame, half, TERRAIN_STEP, z_guess)
    h = dem.navd88(lat, lon) + GEOID_N
    terrain = frame.from_geodetic(lat, lon, h)
    np.save(os.path.join(out, "terrain_xyz.npy"), terrain.astype(np.float32))

    # ---- lidar points in local frame
    p = frame.from_geodetic(lidar["lat"], lidar["lon"], lidar["z_navd88"] + GEOID_N)
    inside = (np.abs(p[:, 0]) <= half + 20) & (np.abs(p[:, 1]) <= half + 20)
    p = p[inside]
    cls = lidar["cls"][inside]
    inten = lidar["intensity"][inside]
    single = (
        lidar["nret"][inside] == 1
    )  # roofs give single returns, canopy mostly multiple

    # ground elevation under any local xy (from the terrain grid, 1 m)
    def ground_at(x, y):
        col = (np.atleast_1d(x) + half) / TERRAIN_STEP
        row = (half - np.atleast_1d(y)) / TERRAIN_STEP
        return ndimage.map_coordinates(
            terrain[..., 2], [row, col], order=1, mode="nearest"
        )

    # ---- building footprints (Overture) in the local frame
    clip_box = box(-half, -half, half, half)
    footprints = []
    for f in ov["building"]:
        g = to_local_xy(frame, f["geometry"], z_guess)
        if g.is_empty or not g.intersects(clip_box):
            continue
        for poly in [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", [])):
            if poly.geom_type != "Polygon" or poly.area < 6:
                continue
            poly = shapely.make_valid(poly.simplify(0.15))
            if poly.geom_type == "Polygon":
                footprints.append((f, poly))

    # ---- split lidar returns. This collection only classifies ground (2); everything
    # else is class 1, so non-ground returns inside a footprint are building, and returns
    # clear of every footprint are vegetation (or wires, filtered by density below).
    hag = p[:, 2] - ground_at(p[:, 0], p[:, 1])
    above = (cls == 1) & (hag > 2.0) & (hag < 45.0)
    fp_union = shapely.union_all([poly for _, poly in footprints])
    near = fp_union.buffer(1.5)
    shapely.prepare(fp_union)
    shapely.prepare(near)
    in_fp = np.zeros(len(p), bool)
    near_fp = np.zeros(len(p), bool)
    in_fp[above] = shapely.contains_xy(fp_union, p[above, 0], p[above, 1])
    near_fp[above] = shapely.contains_xy(near, p[above, 0], p[above, 1])
    is_bldg = above & in_fp & single
    is_veg = above & ~near_fp

    # ---- canopy / building height rasters (0.5 m)
    res = 0.5
    n = int(round(2 * half / res))

    def cell(x, y):
        c = np.floor((x + half) / res).astype(int)
        r = np.floor((half - y) / res).astype(int)
        ok = (c >= 0) & (c < n) & (r >= 0) & (r < n)
        return r, c, ok

    def max_raster(mask):
        r, c, ok = cell(p[mask, 0], p[mask, 1])
        z = p[mask, 2][ok]
        img = np.full((n, n), -np.inf)
        np.maximum.at(img, (r[ok], c[ok]), z)
        img[np.isinf(img)] = np.nan
        return img

    cx = -half + (np.arange(n) + 0.5) * res
    ccx, ccy = np.meshgrid(cx, cx[::-1])
    gnd = ground_at(ccx, ccy)
    veg = max_raster(is_veg) - gnd
    bld = max_raster(is_bldg)

    # ---- trees: local maxima of the canopy height model, ignoring sparse hits (wires)
    chm = np.nan_to_num(veg, nan=0.0)
    density = ndimage.uniform_filter((chm > 2.0).astype(float), size=9)
    chm = ndimage.gaussian_filter(chm, 0.8)
    peaks = (
        (chm == ndimage.maximum_filter(chm, size=9)) & (chm >= 5.0) & (density >= 0.35)
    )
    pr, pc = np.nonzero(peaks)
    th = chm[pr, pc]
    crown = np.clip(1.2 + 0.18 * th, 2.0, 7.5)
    tx, ty = cx[pc], cx[::-1][pr]
    trees = np.column_stack([tx, ty, ground_at(tx, ty), th, crown])
    np.save(os.path.join(out, "trees.npy"), trees.astype(np.float32))

    # ---- buildings: Overture footprints, roofs shaped by the lidar DSM
    bld_filled = bld.copy()
    holes = np.isnan(bld_filled)
    if (~holes).any():
        idx = ndimage.distance_transform_edt(
            holes, return_distances=False, return_indices=True
        )
        bld_filled = bld_filled[tuple(idx)]
    bld_med = ndimage.median_filter(bld_filled, size=5)

    def dsm_at(x, y):
        col = (np.asarray(x) + half) / res - 0.5
        row = (half - np.asarray(y)) / res - 0.5
        return ndimage.map_coordinates(bld_med, [row, col], order=1, mode="nearest")

    buildings = []
    for f, poly in footprints:
        # lidar roof points inside the footprint
        inner = poly.buffer(-0.6)
        minx, miny, maxx, maxy = poly.bounds
        sel = (
            is_bldg
            & (p[:, 0] >= minx)
            & (p[:, 0] <= maxx)
            & (p[:, 1] >= miny)
            & (p[:, 1] <= maxy)
        )
        pts_in = p[sel]
        if len(pts_in):
            pts_in = pts_in[shapely.contains_xy(poly, pts_in[:, 0], pts_in[:, 1])]
        ring = np.asarray(shapely.segmentize(poly.exterior, 1.0).coords)[:-1]
        base_z = float(ground_at(ring[:, 0], ring[:, 1]).min())
        if len(pts_in) >= 8 and len(pts_in) >= 0.15 * poly.area:
            roof_ok = True
            # p90 + 1 m keeps gable ridges but drops overhanging-tree hits above them
            p90, p97 = np.percentile(pts_in[:, 2], [90, 97])
            top = float(min(p97, p90 + 1.0))
        else:
            roof_ok = False
            hgt = f.get("height") or (
                3.2 * f["num_floors"] if f.get("num_floors") else 6.0
            )
            top = base_z + float(hgt)
        buildings.append(
            {
                "id": f.get("id"),
                "name": name_of(f.get("names")),
                "class": f.get("class"),
                "footprint": [list(map(float, c)) for c in poly.exterior.coords[:-1]],
                "holes": [
                    [list(map(float, c)) for c in r.coords[:-1]] for r in poly.interiors
                ],
                "base_z": base_z,
                "top_z": top,
                "lidar_roof": roof_ok,
                "inner_ok": not inner.is_empty,
            }
        )

    # roof meshes: triangulate footprint + interior grid, z from the lidar DSM
    for b in buildings:
        poly = shapely.Polygon(b["footprint"], b["holes"])
        ring_pts = np.asarray(shapely.segmentize(poly.exterior, 1.0).coords)[:-1]
        pts = [ring_pts]
        for r in poly.interiors:
            pts.append(np.asarray(shapely.segmentize(r, 1.0).coords)[:-1])
        minx, miny, maxx, maxy = poly.bounds
        gxs, gys = np.meshgrid(
            np.arange(minx + 0.5, maxx, 1.0), np.arange(miny + 0.5, maxy, 1.0)
        )
        cand = np.column_stack([gxs.ravel(), gys.ravel()])
        if len(cand):
            keep = (
                shapely.contains_xy(poly.buffer(-0.5), cand[:, 0], cand[:, 1])
                if b["inner_ok"]
                else np.zeros(len(cand), bool)
            )
            pts.append(cand[keep])
        allp = np.concatenate(pts)
        tri = shapely.delaunay_triangles(shapely.MultiPoint(allp), only_edges=False)
        faces = []
        lookup = {(round(x, 4), round(y, 4)): i for i, (x, y) in enumerate(allp)}
        for t in tri.geoms:
            c = np.asarray(t.exterior.coords)[:3]
            if not poly.contains(shapely.Point(c.mean(0))):
                continue
            faces.append([lookup[(round(x, 4), round(y, 4))] for x, y in c])
        if b["lidar_roof"]:
            # sample the DSM slightly inside the outline so walls do not pick up the ground
            inward = shapely.Polygon(b["footprint"]).buffer(-0.35)
            sp = allp.copy()
            if not inward.is_empty:
                for i, (x, y) in enumerate(allp):
                    q = (
                        inward.exterior.interpolate(
                            inward.exterior.project(shapely.Point(x, y))
                        )
                        if not inward.contains(shapely.Point(x, y))
                        else None
                    )
                    if q is not None:
                        sp[i] = (q.x, q.y)
            z = np.clip(dsm_at(sp[:, 0], sp[:, 1]), b["base_z"] + 2.2, b["top_z"] + 0.5)
        else:
            z = np.full(len(allp), b["top_z"])
        b["roof_xy"] = allp.round(3).tolist()
        b["roof_z"] = z.round(3).tolist()
        b["roof_faces"] = faces
        b["n_ring"] = len(ring_pts)
        b["hole_rings"] = [len(x) for x in pts[1 : 1 + len(poly.interiors)]]
    with open(os.path.join(out, "buildings.json"), "w") as fh:
        json.dump(buildings, fh)

    # ---- ground texture: lidar intensity, tinted by land use
    tn = int(round(2 * half / GROUND_RES))
    tr = np.floor((half - p[:, 1]) / GROUND_RES).astype(int)
    tc = np.floor((p[:, 0] + half) / GROUND_RES).astype(int)
    ok = (
        (tr >= 0)
        & (tr < tn)
        & (tc >= 0)
        & (tc < tn)
        & np.isin(cls, (2, 9))
        & (lidar["ret"][inside] == lidar["nret"][inside])
    )
    acc = np.zeros((tn, tn))
    cnt = np.zeros((tn, tn))
    np.add.at(acc, (tr[ok], tc[ok]), inten[ok])
    np.add.at(cnt, (tr[ok], tc[ok]), 1)
    valid = cnt > 0
    img = np.where(valid, acc / np.maximum(cnt, 1), np.nan)
    holes = np.isnan(img)
    if holes.any():
        idx = ndimage.distance_transform_edt(
            holes, return_distances=False, return_indices=True
        )
        img = img[tuple(idx)]
    img = ndimage.median_filter(img, size=3)
    lo, hi = np.percentile(img, [2, 98])
    t = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1)

    road_w = {
        "motorway": 12,
        "trunk": 11,
        "primary": 10,
        "secondary": 9,
        "tertiary": 8,
        "residential": 7,
        "unclassified": 6.5,
        "living_street": 6,
        "service": 5,
        "parking_aisle": 6,
        "driveway": 3.5,
        "alley": 4,
        "footway": 1.8,
        "sidewalk": 1.8,
        "pedestrian": 3,
        "path": 1.5,
        "cycleway": 2,
    }
    paved, foot = [], []
    roads_out = []
    for f in ov["segment"]:
        if f.get("subtype") != "road":
            continue
        g = to_local_xy(frame, f["geometry"], z_guess)
        if g.is_empty or not g.intersects(clip_box.buffer(30)):
            continue
        cl = f.get("class") or "unclassified"
        w = road_w.get(cl, 5)
        (
            foot
            if cl in ("footway", "sidewalk", "path", "pedestrian", "cycleway")
            else paved
        ).append(g.buffer(w / 2, cap_style="flat"))
        nm = name_of(f.get("names"))
        if nm and cl not in (
            "footway",
            "sidewalk",
            "path",
            "service",
            "driveway",
            "parking_aisle",
        ):
            roads_out.append(
                {
                    "name": nm,
                    "class": cl,
                    "line": [list(map(float, c)) for c in g.coords]
                    if g.geom_type == "LineString"
                    else None,
                }
            )
    for f in ov.get("land_use", []) + ov.get("infrastructure", []):
        if (f.get("class") or "") in (
            "parking",
            "parking_space",
            "surface",
            "parking_lot",
        ):
            g = to_local_xy(frame, f["geometry"], z_guess)
            if g.geom_type in ("Polygon", "MultiPolygon"):
                paved.append(g)
    water = []
    for f in ov.get("water", []):
        g = to_local_xy(frame, f["geometry"], z_guess)
        if g.is_empty:
            continue
        if g.geom_type in ("LineString", "MultiLineString"):
            g = g.buffer(4 if (f.get("class") in ("river",)) else 2.5)
        water.append(g)
    hw = (tn, tn)
    m_paved = rasterize(paved, GROUND_RES, hw, half)
    m_foot = rasterize(foot, GROUND_RES, hw, half)
    m_water = rasterize(water, GROUND_RES, hw, half)

    grass = np.array([0.30, 0.38, 0.20])
    grass_hi = np.array([0.55, 0.60, 0.38])
    asphalt = np.array([0.17, 0.17, 0.18])
    asphalt_hi = np.array([0.75, 0.74, 0.70])
    concrete = np.array([0.62, 0.61, 0.58])
    water_c = np.array([0.16, 0.24, 0.26])
    tt = t[..., None]
    rgb = grass + (grass_hi - grass) * tt
    rgb = np.where(m_paved[..., None], asphalt + (asphalt_hi - asphalt) * tt**2.2, rgb)
    rgb = np.where(m_foot[..., None], concrete * (0.8 + 0.3 * tt), rgb)
    rgb = np.where(m_water[..., None], water_c * (0.9 + 0.2 * tt), rgb)
    Image.fromarray((np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)).save(
        os.path.join(out, "ground.png")
    )
    Image.fromarray((t * 255).astype(np.uint8)).save(
        os.path.join(out, "lidar_intensity.png")
    )
    Image.fromarray((m_paved & ~m_water).astype(np.uint8) * 255).save(
        os.path.join(out, "paved_mask.png")
    )

    # ---- points of interest, utilities, labels
    pois = []
    for f in ov["place"]:
        g = to_local_xy(frame, f["geometry"], z_guess)
        if abs(g.x) > half or abs(g.y) > half:
            continue
        pois.append(
            {
                "name": name_of(f.get("names")),
                "category": f.get("basic_category"),
                "xy": [g.x, g.y],
                "z": float(ground_at(g.x, g.y)[0]),
            }
        )
    infra = []
    for f in ov.get("infrastructure", []):
        cl = f.get("class") or ""
        if not (
            f.get("subtype") in ("power", "communication")
            or cl in ("charging_station", "street_lamp")
        ):
            continue
        g = to_local_xy(frame, f["geometry"], z_guess)
        if g.is_empty or not g.intersects(clip_box):
            continue
        infra.append({"class": cl, "subtype": f.get("subtype"), "geom": mapping(g)})

    site_pins = []
    for s in sites.SITES:
        lh = float(dem.navd88(np.array([s["lat"]]), np.array([s["lon"]]))[0]) + GEOID_N
        xyz = frame.from_geodetic(s["lat"], s["lon"], lh)
        site_pins.append({"key": s["key"], "title": s["title"], "xyz": xyz.tolist()})

    meta = {
        "site": site,
        "radius_m": half,
        "geoid_n": GEOID_N,
        "ground_res": GROUND_RES,
        "terrain_step": TERRAIN_STEP,
        "extent": sites.extent(site),
        "paste": sites.blosm_paste_string(site),
        "pins": site_pins,
        "pois": pois,
        "roads": roads_out,
        "infrastructure": infra,
        "counts": {
            "buildings": len(buildings),
            "lidar_roofs": sum(b["lidar_roof"] for b in buildings),
            "trees": int(len(trees)),
            "lidar_points": int(len(p)),
        },
        "sources": [
            "USGS 3DEP lidar NH_Coastal 2019 (point cloud + 1 m DEM), public domain",
            f"Overture Maps Foundation {OVERTURE_RELEASE} (includes OpenStreetMap data, ODbL; (c) OpenStreetMap contributors)",
        ],
    }
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    log(f"  {site['key']}: {meta['counts']}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--cache", default=os.path.join(here, "cache"))
    ap.add_argument("--work", default=os.path.join(here, "work"))
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)

    bbox = sites.union_extent(60.0)
    poi_bbox = sites.union_extent(400.0)
    log("bbox", bbox)
    log("Overture ...")
    ov_tables = {
        "building": fetch_overture("buildings", "building", bbox, args.cache),
        "segment": fetch_overture("transportation", "segment", bbox, args.cache),
        "place": fetch_overture("places", "place", poi_bbox, args.cache),
        "infrastructure": fetch_overture("base", "infrastructure", bbox, args.cache),
        "land_use": fetch_overture("base", "land_use", bbox, args.cache),
        "water": fetch_overture("base", "water", bbox, args.cache),
    }
    props = [
        "id",
        "names",
        "class",
        "subtype",
        "height",
        "num_floors",
        "basic_category",
    ]
    ov = {k: overture_features(t, props) for k, t in ov_tables.items()}
    log("Lidar ...")
    lidar = fetch_lidar(bbox, args.cache)
    log("DEM ...")
    z, transform = fetch_dem(bbox, args.cache)
    dem = DemSampler(z, transform)
    for site in sites.SITES:
        build_site(site, lidar, dem, ov, args.work)


if __name__ == "__main__":
    main()
