"""Build Wilton1976_Downtown_v2.blend (UTM 19N / NAVD88, 1 unit = 1 m) from prepare_downtown.py
and layouts.py output.

    blender -b --factory-startup -P build_downtown_v2.py -- --work WORK --out OUT [--blosm DIR]
    python build_downtown_v2.py --work WORK --out OUT [--blosm DIR]          (bpy wheel)
"""

import argparse
import json
import math
import os
import sys

import bpy  # must come first: with the bpy wheel it provides bmesh/mathutils
import bmesh
import numpy as np
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import build_site_blend as v1  # noqa: E402  (tested helpers: materials, text, curves, trench node group)
import frame  # noqa: E402

FT = 0.3048
TOOLS = [
    "import_gis_layer.py",
    "drape_orthophoto.py",
    "import_field_points.py",
    "register_capture.py",
    "google_tiles_to_utm.py",
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--blosm", default=None)
    return ap.parse_args(argv)


class Ground:
    """Detail 1 m DEM where available, else the 8 m overview DEM (bilinear)."""

    def __init__(self, work):
        d = np.load(os.path.join(work, "dem_detail.npz"))
        o = np.load(os.path.join(work, "dem_overview.npz"))
        self.d = (
            d["z"].astype(np.float64),
            float(d["x0"]),
            float(d["y0"]),
            float(d["step"]),
        )
        self.o = (
            o["z"].astype(np.float64),
            float(o["x0"]),
            float(o["y0"]),
            float(o["step"]),
        )

    @staticmethod
    def _bil(g, x, y):
        z, x0, y0, st = g
        c = (x - x0) / st
        r = (y0 - y) / st
        ok = (c >= 0) & (r >= 0) & (c <= z.shape[1] - 1) & (r <= z.shape[0] - 1)
        c = np.clip(c, 0, z.shape[1] - 1.0001)
        r = np.clip(r, 0, z.shape[0] - 1.0001)
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
        vd, okd = self._bil(self.d, x, y)
        vo, _ = self._bil(self.o, x, y)
        return np.where(okd, vd, vo)


def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def fast_mesh(
    name, verts, quads=None, tris=None, c=None, mats=(), mat_index=None, smooth=False
):
    """Mesh from numpy arrays without Python loops (quads and/or triangles)."""
    me = bpy.data.meshes.new(name)
    verts = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
    polys = []
    if quads is not None and len(quads):
        polys.append((np.asarray(quads, dtype=np.int32).reshape(-1, 4), 4))
    if tris is not None and len(tris):
        polys.append((np.asarray(tris, dtype=np.int32).reshape(-1, 3), 3))
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    loops = (
        np.concatenate([p.ravel() for p, _ in polys])
        if polys
        else np.zeros(0, np.int32)
    )
    sizes = (
        np.concatenate([np.full(len(p), k, np.int32) for p, k in polys])
        if polys
        else np.zeros(0, np.int32)
    )
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops)
    me.polygons.add(len(sizes))
    starts = (
        np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int32)
        if len(sizes)
        else sizes
    )
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    for m in mats:
        me.materials.append(m)
    if mat_index is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_index, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.full(len(me.polygons), smooth, dtype=bool))
    ob = bpy.data.objects.new(name, me)
    (c or bpy.context.scene.collection).objects.link(ob)
    return ob


def grid_terrain(name, z, x0, y0, step, c, mats, mask=None, uv_box=None):
    ny, nx = z.shape
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    verts = np.column_stack(
        [
            (x0 + jj * step).ravel(),
            (y0 - ii * step).ravel(),
            np.nan_to_num(z, nan=np.nanmin(z)).ravel(),
        ]
    )
    idx = np.arange(nx * ny).reshape(ny, nx)
    q = np.stack([idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:], idx[:-1, :-1]], -1)
    keep = (
        ~np.isnan(z[1:, :-1])
        & ~np.isnan(z[1:, 1:])
        & ~np.isnan(z[:-1, 1:])
        & ~np.isnan(z[:-1, :-1])
    )
    if mask is not None:
        keep &= mask
    ob = fast_mesh(name, verts, quads=q[keep], c=c, mats=mats, smooth=True)
    if uv_box is not None:
        me = ob.data
        uv = me.uv_layers.new(name="UVMap")
        vi = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", vi)
        xy = verts[vi, :2]
        u = (xy[:, 0] - uv_box[0]) / (uv_box[2] - uv_box[0])
        v = (xy[:, 1] - uv_box[1]) / (uv_box[3] - uv_box[1])
        uv.data.foreach_set("uv", np.column_stack([u, v]).astype(np.float32).ravel())
    return ob


def image_material(name, path, img_name):
    blob = open(path, "rb").read()
    img = bpy.data.images.new(img_name, 8, 8)
    img.source = "FILE"
    img.filepath_raw = "//textures/" + img_name
    img.pack(data=blob, data_len=len(blob))
    img.reload()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Cubic"
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.92
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m, nt, tex


def drape_poly_mesh(name, rings, ground, c, mat, lift=0.12, spacing=3.0):
    """Polygon (exterior + holes, local XY) triangulated with interior points, draped on the DEM."""
    import shapely  # available in the bpy-wheel venv; in Blender.app fall back to bmesh fill

    poly = shapely.Polygon(rings[0], rings[1:])
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return None
    pts = [np.asarray(shapely.segmentize(poly.exterior, spacing).coords)[:-1]]
    pts += [
        np.asarray(shapely.segmentize(r, spacing).coords)[:-1] for r in poly.interiors
    ]
    minx, miny, maxx, maxy = poly.bounds
    gx, gy = np.meshgrid(np.arange(minx, maxx, spacing), np.arange(miny, maxy, spacing))
    cand = np.column_stack([gx.ravel(), gy.ravel()])
    inner = poly.buffer(-spacing * 0.4)
    if len(cand) and not inner.is_empty:
        pts.append(cand[shapely.contains_xy(inner, cand[:, 0], cand[:, 1])])
    allp = np.concatenate(pts)
    tri = shapely.delaunay_triangles(shapely.MultiPoint(allp))
    idx = {(round(x, 3), round(y, 3)): i for i, (x, y) in enumerate(allp)}
    faces = []
    for t in tri.geoms:
        cc = np.asarray(t.exterior.coords)[:3]
        if poly.contains(shapely.Point(cc.mean(0))):
            faces.append([idx[(round(x, 3), round(y, 3))] for x, y in cc])
    z = ground.z(allp[:, 0], allp[:, 1]) + lift
    return fast_mesh(
        name, np.column_stack([allp, z]), tris=np.asarray(faces), c=c, mats=[mat]
    )


def draped_curve(name, xy, ground, c, mat, bevel, lift=0.15, cyclic=False):
    xy = np.asarray(xy, float)
    if len(xy) < 2:
        return None
    dense = [xy[0]]
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(np.linalg.norm(b - a) / 2.0))
        dense += [a + (b - a) * (k / n) for k in range(1, n + 1)]
    dense = np.asarray(dense)
    pts = np.column_stack([dense, ground.z(dense[:, 0], dense[:, 1]) + lift])
    return v1.poly_curve(name, pts, c, bevel, mat, cyclic=cyclic)


def label(name, body, c, loc, size, mat, flat=False, rot_z=0.0):
    t = v1.text_object(
        name,
        body,
        c,
        loc,
        size,
        mat,
        rot=(0, 0, rot_z) if flat else (math.radians(90), 0, rot_z),
    )
    t.visible_shadow = False
    return t


# --------------------------------------------------------------------------- layers


def build_buildings_detail(B, c, mats):
    roof, wall = mats
    for i, b in enumerate(B):
        name = (b["name"] or f"Bldg {i + 1:03d}") + (
            ""
            if b["lidar_roof"]
            else " - NO 2019 LIDAR (outline only, height not measured)"
        )
        if not b["lidar_roof"]:
            ring = np.asarray(b["footprint"])
            v1.poly_curve(
                name,
                np.column_stack([ring, np.full(len(ring), b["base_z"] + 0.2)]),
                c,
                0.15,
                wall,
                cyclic=True,
            )
            continue
        xy = np.asarray(b["roof_xy"])
        z = np.asarray(b["roof_z"])
        verts = [tuple(p) for p in np.column_stack([xy, z])]
        faces = [tuple(f) for f in b["roof_faces"]]
        mi = [0] * len(faces)
        start = 0
        for k in [b["n_ring"]] + list(b["hole_rings"]):
            ids = list(range(start, start + k))
            bot0 = len(verts)
            verts += [(xy[j, 0], xy[j, 1], b["base_z"] - 0.3) for j in ids]
            for a in range(k):
                cc = (a + 1) % k
                faces.append((ids[a], ids[cc], bot0 + cc, bot0 + a))
                mi.append(1)
            start += k
        ob = v1.mesh_object(name, verts, faces, c, mats=[roof, wall], mat_index=mi)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        ob["height_ft"] = round((b["top_z"] - b["base_z"]) / FT, 1)
        ob["footprint_sqft"] = round(b["area_m2"] / FT**2)
        ob["source"] = "Overture/OSM footprint (lidar-registered) + 2019 lidar roof"


def build_buildings_overview(OB, c, mat, mat_x):
    verts, faces = [], []
    for b in OB:
        if b["top_z"] is None:
            continue
        ring = np.asarray(b["footprint"])[:-1]
        if len(ring) < 3:
            continue
        o = len(verts)
        n = len(ring)
        verts += [(x, y, b["base_z"] - 0.5) for x, y in ring] + [
            (x, y, b["top_z"]) for x, y in ring
        ]
        faces += [
            (o + a, o + (a + 1) % n, o + n + (a + 1) % n, o + n + a) for a in range(n)
        ]
        faces.append(tuple(o + n + a for a in range(n)))
    ob = v1.mesh_object(
        "Overview buildings (lidar height, subsampled)", verts, faces, c, mats=[mat]
    )
    nh = [b for b in OB if b["top_z"] is None]
    if nh:
        cu = bpy.data.curves.new(
            "Overview buildings - height NOT measured (outlines)", "CURVE"
        )
        cu.dimensions = "3D"
        cu.bevel_depth = 0.2
        for b in nh:
            ring = np.asarray(b["footprint"])
            sp = cu.splines.new("POLY")
            sp.points.add(len(ring) - 1)
            for p, (x, y) in zip(sp.points, ring):
                p.co = (x, y, b["base_z"] + 0.3, 1)
        o2 = bpy.data.objects.new(cu.name, cu)
        o2.data.materials.append(mat_x)
        c.objects.link(o2)
    return ob


def build_trees(T, c, mats):
    rng = np.random.default_rng(1976)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    iv = np.array([v.co[:] for v in bm.verts])
    ifc = np.array([[v.index for v in f.verts] for f in bm.faces])
    bm.free()
    n = len(T)
    x, y, gz, h, cr = (T[:, i] for i in range(5))
    conifer = rng.random(n) < 0.3
    seg = 5
    ang = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    tr = np.clip(0.012 * h, 0.12, 0.45)
    # trunks: 2 rings of 5
    trunk_v = np.concatenate(
        [
            np.stack(
                [
                    x[:, None] + tr[:, None] * np.cos(ang),
                    y[:, None] + tr[:, None] * np.sin(ang),
                    np.repeat((gz - 0.3)[:, None], seg, 1),
                ],
                -1,
            ),
            np.stack(
                [
                    x[:, None] + tr[:, None] * np.cos(ang),
                    y[:, None] + tr[:, None] * np.sin(ang),
                    np.repeat((gz + 0.5 * h)[:, None], seg, 1),
                ],
                -1,
            ),
        ],
        1,
    ).reshape(-1, 3)
    base = np.arange(n)[:, None] * 2 * seg
    a = np.arange(seg)
    trunk_q = np.stack(
        [base + a, base + (a + 1) % seg, base + seg + (a + 1) % seg, base + seg + a], -1
    ).reshape(-1, 4)
    off = len(trunk_v)
    # deciduous crowns: icospheres
    d = ~conifer
    nd = int(d.sum())
    sz = 0.36 * h[d]
    cz = gz[d] + h[d] - sz
    dv = (
        iv[None, :, :] * np.stack([cr[d], cr[d], sz], -1)[:, None, :]
        + np.stack([x[d], y[d], cz], -1)[:, None, :]
    ).reshape(-1, 3)
    df = (ifc[None, :, :] + off + (np.arange(nd) * len(iv))[:, None, None]).reshape(
        -1, 3
    )
    off2 = off + len(dv)
    # conifer crowns: cones of 6 + apex
    k = conifer
    nk = int(k.sum())
    a6 = np.linspace(0, 2 * math.pi, 6, endpoint=False)
    r = 0.8 * cr[k]
    ring = np.stack(
        [
            x[k][:, None] + r[:, None] * np.cos(a6),
            y[k][:, None] + r[:, None] * np.sin(a6),
            np.repeat((gz[k] + 0.22 * h[k])[:, None], 6, 1),
        ],
        -1,
    )
    apex = np.stack([x[k], y[k], gz[k] + h[k]], -1)[:, None, :]
    kv = np.concatenate([ring, apex], 1).reshape(-1, 3)
    b7 = off2 + np.arange(nk)[:, None] * 7
    a = np.arange(6)
    kf = np.stack([b7 + a, b7 + (a + 1) % 6, np.repeat(b7 + 6, 6, 1)], -1).reshape(
        -1, 3
    )
    verts = np.concatenate([trunk_v, dv, kv])
    tris = np.concatenate([df, kf])
    mi = np.concatenate(
        [
            np.zeros(len(trunk_q), np.int32),
            np.ones(len(df), np.int32),
            np.full(len(kf), 2, np.int32),
        ]
    )
    return fast_mesh(
        "Trees (2019 lidar canopy)",
        verts,
        quads=trunk_q,
        tris=tris,
        c=c,
        mats=mats,
        mat_index=mi,
    )


# --------------------------------------------------------------------------- site layouts


def build_site(key, s, title, ground, c, M, cam_c):
    items = s["items"]
    for it in items:
        poly = np.asarray(it["poly"])
        z = ground.z(poly[:, 0], poly[:, 1])
        mat = (
            M["ada"]
            if "ADA" in it["name"] and "aisle" not in it["name"]
            else (M["aisle"] if "aisle" in it["name"] else M["stall"])
        )
        verts = [(x, y, zz + 0.03) for (x, y), zz in zip(poly, z)]
        ob = v1.mesh_object(
            f"{key} {it['name']}", verts, [tuple(range(len(verts)))], c, mats=[mat]
        )
        ob["slope_pct_DEM"] = it["slope_pct"] if it["slope_pct"] is not None else -1
        ob["note"] = (
            "DESIGN PROPOSAL; slope from USGS 1 m DEM plane fit (ADA max 2.08 %)"
        )
    th = math.radians(s["pedestals"][0]["heading_deg"])
    for i, p in enumerate(s["pedestals"]):
        x, y = p["xy"]
        z = float(ground.z(x, y)[0])
        kit = bpy.data.objects.new(f"{key} PEDESTAL {i + 1} (dual-port, move me)", None)
        kit.empty_display_type = "ARROWS"
        kit.location = (x, y, z)
        kit.rotation_euler = (0, 0, th)
        c.objects.link(kit)
        for nm, (vv, ff), mat in (
            (
                "pedestal (generic envelope)",
                v1.box_verts(0, 0, 0.15, 0.40, 0.30, 1.80),
                M["charger"],
            ),
            ("pad", v1.box_verts(0, 0, -0.05, 0.76, 0.61, 0.20), M["conc"]),
            (
                "plow buffer 3 ft",
                v1.box_verts(0, 0, 0.0, 0.40 + 2 * 0.9144, 0.30 + 2 * 0.9144, 0.02),
                M["buffer"],
            ),
        ):
            ob = v1.mesh_object(f"{key} P{i + 1} {nm}", vv, ff, c, mats=[mat])
            ob.parent = kit
            if "buffer" in nm:
                ob.display_type = "WIRE"
    src = s["power_placeholder"]
    sx, sy = src["xy"]
    sz = float(ground.z(sx, sy)[0])
    vv, ff = v1.box_verts(sx, sy, sz, 0.9, 0.9, 1.2)
    ph = v1.mesh_object(
        f"{key} POWER SOURCE PLACEHOLDER (move to tagged location)",
        vv,
        ff,
        c,
        mats=[M["service"]],
    )
    ph["note"] = src["note"]
    label(
        f"{key} power label",
        "POWER SOURCE?\n(placeholder)",
        c,
        (sx, sy, sz + 3.0),
        1.0,
        M["service"],
    )
    for t in s["trenches"]:
        pts = np.asarray(t["points"])
        cu = v1.poly_curve(
            f"{key} TRENCH to {t['to']} (CALCULATED ESTIMATE - edit points)",
            pts + [0, 0, 0.05],
            c,
            0.0,
            M["trench"],
        )
        mod = cu.modifiers.new("Trench + length label", "NODES")
        mod.node_group = M["trench_ng"]
        cu["length_3d_ft_at_build"] = t["length_3d_ft"]
    # facts board
    m = s["measured"]
    facts = [
        title,
        f"Ground {m['kit_ground_z_navd88_ft']} ft NAVD88 | ADA stall+aisle slope {s['search']['ada_slope_pct']}% (max 2.08%)",
        f"{m['distance_to_mapped_water_edge_ft']} ft to mapped water; {m['height_above_stream_water_surface_ft']} ft above {m['nearest_named_stream']} surface",
        f"Riverwalk/footway {m['distance_to_osm_footway_riverwalk_ft']} ft | trenches {', '.join(str(t['length_3d_ft']) for t in s['trenches'])} ft (EST.)",
    ]
    cx, cy = np.mean([np.mean(it["poly"], axis=0) for it in items], axis=0)
    cz = float(ground.z(cx, cy)[0])
    lab = label(
        f"{key} FACTS", "\n".join(facts), c, (cx, cy, cz + 9.0), 1.1, M["label"]
    )
    # cameras: eye height 5.5 ft from 30 m out along the row's back side, and an aerial
    aim = bpy.data.objects.new(f"{key} AIM", None)
    aim.location = (cx, cy, cz + 1.2)
    cam_c.objects.link(aim)
    back = np.array([-math.sin(th), math.cos(th)])
    for nm, off, h, lens in (
        ("eye level", back * -30.0, 1.68, 24.0),
        ("aerial", back * -70.0 + np.array([20, -20]), 55.0, 30.0),
    ):
        ex, ey = cx + off[0], cy + off[1]
        cd = bpy.data.cameras.new(f"{key} CAM {nm}")
        cd.lens = lens
        cd.clip_start, cd.clip_end = 0.3, 8000
        cam = bpy.data.objects.new(f"{key} CAM {nm}", cd)
        cam.location = (ex, ey, float(ground.z(ex, ey)[0]) + h)
        con = cam.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
        cam_c.objects.link(cam)
    con = lab.constraints.new("TRACK_TO")
    con.target = bpy.data.objects[f"{key} CAM aerial"]
    con.track_axis, con.up_axis = "TRACK_Z", "UP_Y"
    return aim


def overlay_poly(name, ring, ground, c, mat, text=None, text_mat=None, size=1.4):
    ob = drape_poly_mesh(name, [ring], ground, c, mat, lift=0.06, spacing=2.0)
    if text:
        r = np.asarray(ring)
        x, y = r.mean(0)
        label(
            name + " label",
            text,
            c,
            (x, y, float(ground.z(x, y)[0]) + 0.3),
            size,
            text_mat or mat,
            flat=True,
        )
    return ob


# --------------------------------------------------------------------------- main


def main():
    a = parse_args()
    W = a.work
    meta = json.load(open(os.path.join(W, "meta.json")))
    L = json.load(open(os.path.join(W, "layouts.json")))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    blosm_ok = bool(a.blosm) and v1.enable_blosm(a.blosm)
    scene = bpy.context.scene
    scene.name = "Wilton1976_Downtown_v2"
    us = scene.unit_settings
    us.system, us.length_unit, us.scale_length = "IMPERIAL", "FEET", 1.0
    lat0, lon0 = (float(v) for v in frame.geodetic(0.0, 0.0))
    # georeference: BlenderGIS keys + Blosm keys + our own record
    scene["SRID"] = "EPSG:26919"
    scene["crs x"], scene["crs y"] = frame.E0, frame.N0
    scene["latitude"], scene["longitude"] = lat0, lon0
    scene["lat"], scene["lon"] = lat0, lon0
    scene["crs_note"] = (
        "NAD83 / UTM 19N (EPSG:26919) metres; X = E - 276000, Y = N - 4747000; Z = NAVD88 m (no offset)"
    )
    scene["vertical_datum"] = "NAVD88 (GEOID12B per NH_Coastal_2019 metadata)"
    ground = Ground(W)

    M = {
        "roof": v1.material("Roof (lidar)", (0.32, 0.30, 0.29, 1), 0.7),
        "wall": v1.material("Wall", (0.82, 0.78, 0.70, 1), 0.85),
        "ov_bldg": v1.material("Overview building", (0.75, 0.72, 0.66, 1), 0.9),
        "ov_bldg_x": v1.material("Height not measured", (0.80, 0.40, 0.85, 1), 0.9),
        "trunk": v1.material("Tree trunk", (0.22, 0.15, 0.09, 1), 0.9),
        "leaf": v1.material("Tree crown", (0.16, 0.28, 0.10, 1), 0.9),
        "conifer": v1.material("Tree crown conifer", (0.08, 0.18, 0.08, 1), 0.9),
        "water": v1.material("Water (NHD)", (0.10, 0.25, 0.35, 1), 0.1),
        "stream": v1.material(
            "Stream centreline (NHD)", (0.15, 0.55, 1.0, 1), 0.3, emission=1.5
        ),
        "road": v1.material(
            "Road centreline (OSM)", (0.95, 0.30, 0.85, 1), 0.5, emission=0.6
        ),
        "foot": v1.material(
            "Footway / riverwalk (OSM)", (0.20, 0.85, 0.30, 1), 0.5, emission=0.8
        ),
        "label": v1.material("Label", (0.97, 0.97, 0.95, 1), 0.5, emission=1.5),
        "warn": v1.material("Warning", (1.0, 0.15, 0.05, 1), 0.5, emission=2.0),
        "stall": v1.material("EV stall", (0.95, 0.95, 0.92, 1), 0.6, emission=0.3),
        "ada": v1.material("ADA van stall", (0.10, 0.35, 0.95, 1), 0.5, emission=0.6),
        "aisle": v1.material(
            "ADA access aisle 8 ft", (0.55, 0.75, 1.0, 1), 0.5, emission=0.4
        ),
        "charger": v1.material("Pedestal (generic)", (0.12, 0.13, 0.14, 1), 0.35),
        "conc": v1.material("Concrete pad", (0.70, 0.69, 0.66, 1), 0.8),
        "buffer": v1.material("Plow buffer 3 ft", (1.0, 0.8, 0.0, 1), 0.5),
        "service": v1.material(
            "Power source placeholder", (1.0, 0.80, 0.0, 1), 0.4, emission=2.0
        ),
        "trench": v1.material(
            "Trench (estimate)", (0.95, 0.12, 0.05, 1), 0.5, emission=1.0
        ),
        "deed": v1.material(
            "Deed undelineated (40 spaces)",
            (1.0, 0.9, 0.1, 1),
            0.5,
            emission=0.5,
            alpha=0.28,
        ),
        "exit": v1.material(
            "Police exit keep-clear", (1.0, 0.1, 0.1, 1), 0.5, emission=0.5, alpha=0.28
        ),
        "roofp": v1.material(
            "Mill roof plane (lidar)",
            (0.25, 0.75, 0.95, 1),
            0.5,
            emission=0.4,
            alpha=0.6,
        ),
        "dike": v1.material(
            "Dike crest (estimate)", (0.85, 0.55, 0.15, 1), 0.5, emission=1.0
        ),
        "bridge": v1.material(
            "Bridge corridor (estimate)", (0.9, 0.9, 0.2, 1), 0.5, emission=1.2
        ),
        "ring": v1.material("Distance ring", (1.0, 1.0, 1.0, 1), 0.5, emission=1.0),
    }
    for mname in ("deed", "exit"):
        if hasattr(M[mname], "blend_method"):
            M[mname].blend_method = "BLEND"
    M["trench_ng"] = v1.trench_node_group(M["trench"], M["label"])

    C = {
        k: coll(n)
        for k, n in (
            ("ter", "00 Terrain - USGS 3DEP 1 m DEM (NAVD88)"),
            ("ortho", "01 Orthophoto drape - NOT LOADED (see drape_orthophoto.py)"),
            ("bld", "02 Buildings - lidar roofs (detail)"),
            ("bldo", "02 Buildings - overview (2 mi)"),
            ("tree", "03 Trees - 2019 lidar"),
            ("water", "04 Water - NHD + dike (estimate)"),
            ("flood", "05 Flood zones FEMA NFHL - NOT LOADED (import_gis_layer.py)"),
            ("wet", "06 Wetlands NWI/NHDES - NOT LOADED (import_gis_layer.py)"),
            ("parcel", "07 Parcels - NOT LOADED (import_gis_layer.py)"),
            ("road", "08 Roads + sidewalks - OSM/Overture"),
            ("util", "09 Utilities - tag on site (import_field_points.py)"),
            ("s1", "10 Site 1 - Police lot"),
            ("s2", "11 Site 2 - Main St lot"),
            ("s3", "12 Site 3 - Library street-side"),
            ("s4", "13 Site 4 - Mill"),
            ("roof", "14 Mill roof planes - 2019 lidar (see MILL_ROOF.md)"),
            ("cam", "20 Cameras + lights"),
            (
                "goog",
                "30 Google 3D Tiles - optional, VISUAL ONLY (google_tiles_to_utm.py)",
            ),
        )
    }

    # ---- terrain
    det = meta["detail_box"]
    d = np.load(os.path.join(W, "dem_detail.npz"))
    zt = d["z"].astype(float)
    m_ground, nt, tex = image_material(
        "Ground - lidar intensity composite (NOT a photo)",
        os.path.join(W, "ground_detail.png"),
        "ground_lidar_composite.png",
    )
    for extra, nm in (
        ("relief_hillshade.png", "lidar_relief_hillshade.png"),
        ("lidar_intensity.png", "lidar_intensity.png"),
    ):
        if os.path.exists(os.path.join(W, extra)):
            blob = open(os.path.join(W, extra), "rb").read()
            img = bpy.data.images.new(nm, 8, 8)
            img.source = "FILE"
            img.filepath_raw = "//textures/" + nm
            img.pack(data=blob, data_len=len(blob))
            img.reload()
            n2 = nt.nodes.new("ShaderNodeTexImage")
            n2.image = img
            n2.label = f"Alternate: {nm} (connect to Base Color to switch)"
            n2.location = (
                tex.location.x,
                tex.location.y
                - 300 * (1 + len([n for n in nt.nodes if n.type == "TEX_IMAGE"]) - 2),
            )
    ter = grid_terrain(
        "Terrain detail 1 m (USGS 3DEP NH_Coastal_2019, NAVD88)",
        zt,
        float(d["x0"]),
        float(d["y0"]),
        float(d["step"]),
        C["ter"],
        [m_ground],
        uv_box=(det[0], det[1], det[2], det[3]),
    )
    ter["source"] = meta["layers"]["terrain"]["source"]
    ter["accuracy"] = meta["layers"]["terrain"]["accuracy"]
    o = np.load(os.path.join(W, "dem_overview.npz"))
    zo = o["z"].astype(float)
    ox0, oy0, ost = float(o["x0"]), float(o["y0"]), float(o["step"])
    ny, nx = zo.shape
    cxs = ox0 + (np.arange(nx - 1) + 0.5) * ost
    cys = oy0 - (np.arange(ny - 1) + 0.5) * ost
    gx, gy = np.meshgrid(cxs, cys)
    cx0, cy0 = meta["center_local"]
    outside = ~(
        (gx > det[0] + 4) & (gx < det[2] - 4) & (gy > det[1] + 4) & (gy < det[3] - 4)
    )
    inside_circle = np.hypot(gx - cx0, gy - cy0) <= frame.OVERVIEW_RADIUS
    m_ov = v1.material("Terrain overview 8 m", (0.42, 0.48, 0.34, 1), 0.95)
    grid_terrain(
        "Terrain overview 8 m (2 mi radius, USGS 3DEP)",
        zo - 0.25,
        ox0,
        oy0,
        ost,
        C["ter"],
        [m_ov],
        mask=outside & inside_circle,
    )

    # ---- buildings, trees
    build_buildings_detail(
        json.load(open(os.path.join(W, "buildings_detail.json"))),
        C["bld"],
        (M["roof"], M["wall"]),
    )
    build_buildings_overview(
        json.load(open(os.path.join(W, "buildings_overview.json"))),
        C["bldo"],
        M["ov_bldg"],
        M["ov_bldg_x"],
    )
    T = np.load(os.path.join(W, "trees.npy")).astype(float)
    build_trees(T, C["tree"], (M["trunk"], M["leaf"], M["conifer"]))

    # ---- water (NHD) + dike candidate
    water = json.load(open(os.path.join(W, "water.json")))
    import shapely
    from shapely.geometry import shape

    circle = shapely.Point(cx0, cy0).buffer(frame.OVERVIEW_RADIUS)
    for k in ("areas", "waterbodies"):
        for i, w in enumerate(water[k]):
            g = shape(w["geom"]).intersection(circle)
            for j, pg in enumerate(
                [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
            ):
                if pg.geom_type == "Polygon" and pg.area > 50:
                    ob = drape_poly_mesh(
                        f"NHD {k[:-1]} {w['name'] or 'unnamed'} {i}.{j}",
                        [list(pg.exterior.coords)]
                        + [list(r.coords) for r in pg.interiors],
                        ground,
                        C["water"],
                        M["water"],
                        lift=0.08,
                        spacing=6.0 if pg.area > 2e5 else 3.0,
                    )
                    if ob:
                        ob["source"] = (
                            "USGS NHD HR HU8 01070006 (ftype %s)" % w["ftype"]
                        )
    for w in water["flowlines"]:
        g = shape(w["geom"]).intersection(circle)
        for j, ln in enumerate(
            [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
        ):
            if ln.geom_type == "LineString" and ln.length > 5:
                draped_curve(
                    f"NHD {w['name'] or 'flowline'} {j}",
                    list(ln.coords),
                    ground,
                    C["water"],
                    M["stream"],
                    0.25,
                    lift=0.3,
                )
    for nm in ("Souhegan River", "Stony Brook"):
        lines = [shape(w["geom"]) for w in water["flowlines"] if w["name"] == nm]
        if lines:
            ln = max(lines, key=lambda g: g.length)
            p = ln.interpolate(0.5, normalized=True)
            if abs(p.x - cx0) < 1500 and abs(p.y - cy0) < 1500:
                label(
                    f"NHD label {nm}",
                    nm.upper(),
                    C["water"],
                    (p.x, p.y, float(ground.z(p.x, p.y)[0]) + 1.0),
                    4.0,
                    M["stream"],
                    flat=True,
                )
    dk = L["sites"]["S4_Mill"].get("dike_candidate")
    if dk:
        pts = np.asarray(dk["points"])
        mask = np.asarray(dk["embankment_mask"])
        runs, cur = [], []
        for p, mk in zip(pts, mask):
            if mk:
                cur.append(p)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        for i, r in enumerate(r for r in runs if len(r) >= 4):
            v1.poly_curve(
                f"DIKE crest {i} - CALCULATED ESTIMATE (lidar DEM)",
                np.asarray(r) + [0, 0, 0.2],
                C["water"],
                0.35,
                M["dike"],
            )
        p = pts[mask][len(pts[mask]) // 2] if mask.any() else pts[0]
        label(
            "DIKE label",
            f"DIKE? crest {dk['crest_height_above_pond_ft_median']} ft above pond (EST.)\nconfirm = Waterworks dike",
            C["water"],
            (p[0], p[1], p[2] + 4),
            2.0,
            M["dike"],
        )
    label(
        "SLUICEWAY note",
        "Hydro sluiceway / channel: NOT in NHD and not\nidentified in lidar - trace on site (see missing list)",
        C["water"],
        (150.0, -60.0, float(ground.z(150, -60)[0]) + 6),
        1.6,
        M["warn"],
    )

    # ---- roads + sidewalks
    R = json.load(open(os.path.join(W, "roads.json")))
    done_names = set()
    for i, rd in enumerate(R):
        if not rd["line"]:
            continue
        foot = rd["class"] in ("footway", "path", "pedestrian", "steps", "sidewalk")
        ln = np.asarray(rd["line"])
        in_det = (
            (ln[:, 0] > det[0]).all()
            and (ln[:, 0] < det[2]).all()
            and (ln[:, 1] > det[1]).all()
            and (ln[:, 1] < det[3]).all()
        )
        draped_curve(
            f"{'Footway' if foot else 'Road'} {rd['name'] or rd['class']} {i}",
            ln,
            ground,
            C["road"],
            M["foot"] if foot else M["road"],
            0.12 if foot else 0.25 if in_det else 0.8,
            lift=0.2,
        )
        if (
            rd["name"]
            and in_det
            and not foot
            and rd["name"] not in done_names
            and len(ln) >= 2
        ):
            k = len(ln) // 2
            a_, b_ = ln[max(k - 1, 0)], ln[min(k + 1, len(ln) - 1)]
            ang = math.atan2(b_[1] - a_[1], b_[0] - a_[0])
            if abs(ang) > math.pi / 2:
                ang += math.pi
            label(
                f"Street {rd['name']}",
                rd["name"].upper(),
                C["road"],
                (ln[k][0], ln[k][1], float(ground.z(*ln[k])[0]) + 0.6),
                3.0,
                M["label"],
                flat=True,
                rot_z=ang,
            )
            done_names.add(rd["name"])

    # ---- placeholders for layers that could not be loaded in this build
    for key_, text in (
        (
            "ortho",
            "ORTHOPHOTO NOT LOADED: GRANIT 2021/22 6-in leaf-off imagery was not reachable from the build machine.\nRun drape_orthophoto.py (Scripting tab) with the downloaded tile + world file.",
        ),
        (
            "flood",
            "FEMA NFHL NOT LOADED (FIRM effective 2009-09-25, Hillsborough Co. panels 33011C....).\nDownload NFHL_33011C from msc.fema.gov, then run import_gis_layer.py on S_FLD_HAZ_AR.shp and S_BFE.shp.",
        ),
        (
            "wet",
            "WETLANDS NOT LOADED: NWI (fws.gov) / NHDES layers were not reachable.\nRun import_gis_layer.py on the NWI shapefile for NH.",
        ),
        (
            "parcel",
            "PARCELS NOT LOADED: GRANIT parcel mosaic / Town tax map J not reachable.\nRun import_gis_layer.py on the parcel shapefile (21 Mill St, 13-ft strip, J-104-2, J-61...).",
        ),
        (
            "util",
            "UTILITIES: no poles, transformers or meters are mapped in any open dataset here.\nFill field_points_template.csv from CompanyCam and run import_field_points.py.",
        ),
        (
            "goog",
            "Google Photorealistic 3D Tiles: VISUAL CONTEXT ONLY - never measure from them.\nImport with Blosm (panel pre-set), then run google_tiles_to_utm.py.",
        ),
    ):
        x, y = cx0 + 60, cy0 - 120
        label(
            f"NOTE {key_}",
            text,
            C[key_],
            (x, y, float(ground.z(x, y)[0]) + 20 + 4 * list(C).index(key_)),
            2.2,
            M["warn"],
        )

    # ---- sites
    titles = {s["key"]: s["title"] for s in frame.SITES}
    ckey = {
        "S1_PoliceLot": "s1",
        "S2_MainStLot": "s2",
        "S3_Library": "s3",
        "S4_Mill": "s4",
    }
    aims = {}
    for key, s in L["sites"].items():
        aims[key] = build_site(key, s, titles[key], ground, C[ckey[key]], M, C["cam"])
        sx, sy = (
            float(v)
            for v in frame.local(
                *next((t["lat"], t["lon"]) for t in frame.SITES if t["key"] == key)
            )
        )
        sz = float(ground.z(sx, sy)[0])
        vv, ff = v1.box_verts(sx, sy, sz - 0.3, 0.3, 0.3, 15.3)
        v1.mesh_object(
            f"{key} PIN (brief coordinate)", vv, ff, C[ckey[key]], mats=[M["warn"]]
        )
        label(
            f"{key} PIN label",
            f"{titles[key]}\n(brief coordinate)",
            C[ckey[key]],
            (sx, sy, sz + 17.0),
            1.6,
            M["warn"],
        )
    s1, s2, s4 = (
        L["sites"]["S1_PoliceLot"],
        L["sites"]["S2_MainStLot"],
        L["sites"]["S4_Mill"],
    )
    if "deed_area" in s1:
        overlay_poly(
            "S1 40 DEEDED SPACES - DEED UNDELINEATED (whole lot shaded)",
            s1["deed_area"]["poly"],
            ground,
            C["s1"],
            M["deed"],
            f"40 SPACES DEEDED TO WILTON FALLS BLDG (6 Burns Hill Rd)\nDEED UNDELINEATED - whole paved lot shown ({s1['deed_area']['area_sqft']:,} sq ft)",
            M["label"],
            1.3,
        )
    if "police_exit" in s1:
        overlay_poly(
            "S1 POLICE EXIT keep-clear (ASSUMED - confirm with WPD)",
            s1["police_exit"]["zone"],
            ground,
            C["s1"],
            M["exit"],
            "POLICE EXIT - KEEP CLEAR\n(assumed from brief; confirm with WPD)",
            M["warn"],
            1.3,
        )
    hz = s1["hazard"]
    hx, hy = hz["xy"]
    label(
        "S1 HAZARD",
        "REPORTED: sodium cyanide vault under concrete cap, Abbott Trust lot J-104-2 (EPA 2023).\nTown 10/22: the concrete pad in front of the PD by the bridge.\nEXACT EDGES PENDING (PASI report) - confirm before trenching",
        C["s1"],
        (hx + 12.0, hy + 12.0, float(ground.z(hx, hy)[0]) + 24.0),
        1.4,
        M["warn"],
    )
    if "bands" in s2:
        bx, by = s2["bands"]["center"]
        for r_ft in s2["bands"]["rings_ft"]:
            a_ = np.linspace(0, 2 * math.pi, 120)
            r = r_ft * FT
            draped_curve(
                f"S2 ring {r_ft} ft (brief: AE/floodway band toward Stony Brook)",
                np.column_stack([bx + r * np.cos(a_), by + r * np.sin(a_)]),
                ground,
                C["s2"],
                M["ring"],
                0.08,
                cyclic=False,
            )
        label(
            "S2 bands label",
            f"150 / 250 ft rings from brief point. Point is {s2['bands']['given_point_to_stony_brook_ft']} ft from Stony Brook CL.\nFEMA NFHL NOT LOADED - rings are distances only. Snow-storage corner: not mapped",
            C["s2"],
            (bx, by - 30, float(ground.z(bx, by - 30)[0]) + 6),
            1.3,
            M["warn"],
        )
    if "bridge_corridor" in s4:
        bc = s4["bridge_corridor"]
        v1.poly_curve(
            "S4 PEDESTRIAN BRIDGE corridor Riverside Way-Howard St (CALCULATED ESTIMATE)",
            np.asarray(bc["points"]) + [0, 0, 1.0],
            C["s4"],
            0.3,
            M["bridge"],
        )
        p = np.asarray(bc["points"])[len(bc["points"]) // 2]
        label(
            "S4 bridge label",
            f"Bridge corridor (EST.): {bc['length_ft']} ft landing-to-landing line,\n{bc['water_width_ft']} ft over mapped water. Plan A / Plan B TBD on site",
            C["s4"],
            (p[0], p[1], p[2] + 8),
            1.5,
            M["bridge"],
        )
    mx, my = s4["map_point_21_mill_st"]
    label(
        "S4 21 Mill St",
        "21 Mill St (OSM house point)\nparcel lines + 13-ft strip NOT MAPPED",
        C["s4"],
        (mx, my, float(ground.z(mx, my)[0]) + 6),
        1.3,
        M["warn"],
    )

    # ---- mill roof planes (mill_roof.py)
    mr_path = os.path.join(W, "mill_roof.json")
    if os.path.exists(mr_path):
        MR = json.load(open(mr_path))
        info = {
            (b["building"], p["id"]): p for b in MR["buildings"] for p in b["planes"]
        }
        for k, pt in enumerate(
            json.load(open(os.path.join(W, "mill_roof_patches.json")))
        ):
            ring = np.asarray(pt["ring"])
            a_, b_, c_ = pt["abc"]
            z = a_ * ring[:, 0] + b_ * ring[:, 1] + c_ + 0.15
            ob = v1.mesh_object(
                f"Mill roof {pt['building'][:14]} plane {pt['plane']}.{k}",
                list(map(tuple, np.column_stack([ring, z]))),
                [tuple(range(len(ring)))],
                C["roof"],
                mats=[M["roofp"]],
            )
            pinfo = info.get((pt["building"], pt["plane"]), {})
            for kk in (
                "plan_area_sqft",
                "sloped_area_sqft",
                "slope_deg",
                "pitch_in_12",
                "azimuth_true_deg",
                "usable_4ft_sqft",
                "solar_kwdc_est",
            ):
                if kk in pinfo:
                    ob[kk] = pinfo[kk]
        for b in MR["buildings"]:
            big = max(b["planes"], key=lambda q: q["plan_area_sqft"])
            sel = [
                pt
                for pt in json.load(open(os.path.join(W, "mill_roof_patches.json")))
                if pt["building"] == b["building"] and pt["plane"] == big["id"]
            ]
            if sel:
                r = np.asarray(sel[0]["ring"])
                x, y = r.mean(0)
                a_, b_, c_ = sel[0]["abc"]
                label(
                    f"Mill roof label {b['building'][:20]}",
                    f"{b['building'].split(' (')[0]}: footprint {b['footprint_sqft']:,} sq ft\n"
                    f"roof planes {sum(q['sloped_area_sqft'] for q in b['planes']):,} sq ft | usable (4 ft) {sum(q['usable_4ft_sqft'] for q in b['planes']):,} sq ft (EST.)",
                    C["roof"],
                    (x, y, a_ * x + b_ * y + c_ + 6.0),
                    1.6,
                    M["label"],
                )

    # ---- lights, world, render, viewport
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = Euler((math.radians(50), 0, math.radians(35)))
    C["cam"].objects.link(sun)
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.55,
        0.68,
        0.86,
        1,
    )
    scene.world = world
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.filepath = "//renders/"
    scene.camera = bpy.data.objects["S1_PoliceLot CAM aerial"]
    if blosm_ok:
        b = scene.blosm
        b.dataType, b.threedTilesSource, b.lodOf3dTiles = "3d-tiles", "google", "lod5"
        b.join3dTilesObjects, b.relativeToInitialImport = True, True
        lat_a, lon_a = frame.geodetic(
            np.array([det[0], det[2]]), np.array([det[1], det[3]])
        )
        b.minLon, b.minLat, b.maxLon, b.maxLat = (
            float(lon_a.min()),
            float(lat_a.min()),
            float(lon_a.max()),
            float(lat_a.max()),
        )
    for screen in bpy.data.screens:
        for area in screen.areas:
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    sp.clip_start, sp.clip_end = 0.1, 20000.0
                    sp.shading.type, sp.shading.color_type = "SOLID", "TEXTURE"
                    sp.show_region_ui = True
                    sp.region_3d.view_location = Vector((cx0 + 50, cy0 + 60, 110))
                    sp.region_3d.view_distance = 700.0
                    sp.region_3d.view_rotation = Euler(
                        (math.radians(55), 0, math.radians(25))
                    ).to_quaternion()

    # ---- notes + tools inside the file
    for name in ("README_v2.md", "SOURCE_LOG.md", "MISSING_MEASUREMENTS.md"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            bpy.data.texts.new(name).write(open(p).read())
    for name in TOOLS + ["frame.py"]:
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            bpy.data.texts.new(name).write(open(p).read())
    for src_name, txt_name in (
        ("layouts.md", "SITE_LAYOUT_MEASUREMENTS.md"),
        ("MILL_ROOF.md", "MILL_ROOF.md"),
    ):
        lm = os.path.join(W, src_name)
        if os.path.exists(lm):
            bpy.data.texts.new(txt_name).write(open(lm).read())
    scene["checks"] = json.dumps(meta["checks"])
    for ob in scene.objects:
        ob.select_set(False)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "Wilton1976_Downtown_v2.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print(f"saved {path} ({os.path.getsize(path) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
    if bpy.app.background:
        sys.stdout.flush()
        os._exit(0)
