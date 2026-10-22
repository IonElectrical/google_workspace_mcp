"""Downloaders shared by every location job (copied from the Wilton v1 prepare_data.py, with the
dataset choices moved into the job config): S3 listing, Overture GeoParquet range reads and
USGS EPT lidar. No API keys. Callers pass the Overture release and EPT project URLs.
"""

import concurrent.futures as cf
import io
import math
import os
import xml.etree.ElementTree as ET

import laspy
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import requests
import shapely

OVERTURE = "https://overturemaps-us-west-2.s3.amazonaws.com"
session = requests.Session()


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


def fetch_overture(theme, otype, bbox, cache, release):
    """Rows of one Overture type intersecting bbox=(minlon,minlat,maxlon,maxlat)."""
    path = os.path.join(cache, f"overture_{otype}.parquet")
    if os.path.exists(path):
        return pq.read_table(path)
    files = [
        (k, s)
        for k, s in s3_list(OVERTURE, f"{release}/theme={theme}/type={otype}/")
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


def ept_points(base, bbox):
    """All EPT points of one project inside bbox (lon/lat). Returns an (n, 7) array in Web
    Mercator: x, y, z, intensity, class, return number, number of returns."""
    x0, y0 = lonlat_to_merc(bbox[0], bbox[1])
    x1, y1 = lonlat_to_merc(bbox[2], bbox[3])
    info = get(base + "ept.json").json()
    b = info["bounds"]
    span = b[3] - b[0]

    def hits(key):
        d, x, y, _z = map(int, key.split("-"))
        size = span / (2**d)
        return (
            b[0] + x * size <= x1
            and b[0] + (x + 1) * size >= x0
            and b[1] + y * size <= y1
            and b[1] + (y + 1) * size >= y0
        )

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
    pts = np.concatenate(chunks) if chunks else np.zeros((0, 7))
    log(
        f"  lidar {base.rsplit('/', 2)[-2]}: {len(data_keys)} nodes, {len(pts)} points in bbox"
    )
    return pts


def fetch_lidar(bbox, cache, projects):
    """Points from the first EPT project in `projects` that returns points for bbox."""
    path = os.path.join(cache, "lidar_points.npz")
    if os.path.exists(path):
        return dict(np.load(path))
    tried = []
    for base in projects:
        pts = ept_points(base, bbox)
        tried.append([base, len(pts)])
        if len(pts):
            break
    else:
        raise RuntimeError(f"no lidar points in bbox from {projects}")
    lon, lat = merc_to_lonlat(pts[:, 0], pts[:, 1])
    out = {
        "lon": lon,
        "lat": lat,
        "z_navd88": pts[:, 2],
        "intensity": pts[:, 3],
        "cls": pts[:, 4].astype(np.uint8),
        "ret": pts[:, 5].astype(np.uint8),
        "nret": pts[:, 6].astype(np.uint8),
        "project": base,
    }
    np.savez_compressed(path, **out)
    return out
