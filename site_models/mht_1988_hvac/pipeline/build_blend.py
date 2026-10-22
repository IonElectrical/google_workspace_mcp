"""Build the job .blend (UTM / NAVD88, 1 unit = 1 m, display in feet) from the pipeline outputs.
Generalised from Wilton's build_downtown_v2.py: collections, names and site content come from the
job config and WORK/sites_resolved.json (written by export_web.py from the job's analysis), so the
.blend and the web viewer show the same features.

    python build_blend.py --work WORK --out ../blend            (bpy 4.5 wheel, numpy<2, shapely)
    blender -b --factory-startup -P build_blend.py -- --work WORK --out ../blend
"""

import argparse
import json
import math
import os
import sys

import bpy  # isort: skip  (must come first: with the bpy wheel it provides bmesh/mathutils)
import bmesh  # isort: skip
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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
    ap.add_argument("--config", default=None)
    return ap.parse_args(argv)


def material(name, color, roughness=0.8, emission=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = color
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.diffuse_color = (*color[:3], alpha)
    return m


def mesh_object(name, verts, faces, coll, mats=(), mat_index=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(clean_customdata=False)
    for m in mats:
        me.materials.append(m)
    if mat_index is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_index, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.full(len(me.polygons), smooth, dtype=bool))
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def text_object(name, body, coll, loc, size, mat, rot=(0.0, 0.0, 0.0), extrude=0.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = rot
    ob.data.materials.append(mat)
    coll.objects.link(ob)
    return ob


def poly_curve(name, pts, coll, bevel, mat, cyclic=False):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = 1
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (c[0], c[1], c[2], 1.0)
    sp.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    coll.objects.link(ob)
    return ob


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
    return poly_curve(name, pts, c, bevel, mat, cyclic=cyclic)


def label(name, body, c, loc, size, mat, flat=False, rot_z=0.0):
    t = text_object(
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
            poly_curve(
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
        ob = mesh_object(name, verts, faces, c, mats=[roof, wall], mat_index=mi)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        if "height_note" not in b:
            ob["height_ft"] = round((b["top_z"] - b["base_z"]) / FT, 1)
        ob["footprint_sqft"] = round(b["area_m2"] / FT**2)
        ob["source"] = (
            b.get("height_note")
            or "Overture/OSM footprint (lidar-registered) + 2019 lidar roof"
        )


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
    ob = mesh_object(
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


# --------------------------------------------------------------------------- sites

MATS = {
    "unit": ("Rooftop unit - lidar candidate", (0.18, 0.50, 0.85, 1), 0.5, 0.4, 1.0),
    "unitAlt": (
        "Rooftop unit - alternate candidate",
        (0.55, 0.58, 0.61, 1),
        0.6,
        0.0,
        0.8,
    ),
    "riser": ("Riser height (estimate, x-ray)", (1.0, 0.54, 0.12, 1), 0.5, 1.5, 1.0),
    "route": ("Route (estimate)", (0.95, 0.12, 0.05, 1), 0.5, 1.0, 1.0),
    "placeholder": ("PLACEHOLDER - not located", (1.0, 0.82, 0.10, 1), 0.4, 2.0, 1.0),
    "craneMark": ("Crane spot (estimate)", (1.0, 0.62, 0.10, 1), 0.4, 1.5, 1.0),
    "crane": ("Crane pad (estimate)", (1.0, 0.62, 0.10, 1), 0.5, 0.6, 0.35),
    "closure": ("Road closure area (estimate)", (1.0, 0.16, 0.12, 1), 0.5, 0.6, 0.35),
    "zone": ("Zone", (1.0, 0.89, 0.10, 1), 0.5, 0.5, 0.3),
    "line": ("Measured distance line", (1.0, 1.0, 1.0, 1), 0.5, 1.0, 1.0),
}


def build_site(s, c, M, cam_c):
    for k, f in enumerate(s["features"]):
        info = f.get("info") or {}
        name = (info.get("title") or f.get("label") or f"{s['key']} {f['t']} {k}")[:60]
        ob = None
        if f["t"] == "box":
            cx, cy, cz = f["c"]
            me = bpy.data.meshes.new(name)
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(name, me)
            ob.scale = (f["w"], f["d"], f["h"])
            ob.location = (cx, cy, cz + f["h"] / 2)
            ob.rotation_euler = (0, 0, -math.radians(f.get("rot", 0.0)))
            me.materials.append(M.get(f.get("mat"), M["unit"]))
            c.objects.link(ob)
        elif f["t"] in ("tube", "line"):
            p = np.asarray(f["p"], float).reshape(-1, 3)
            ob = poly_curve(
                name,
                p,
                c,
                0.12 if f["t"] == "tube" else 0.05,
                M.get(f.get("mat"), M["line"] if f["t"] == "line" else M["riser"]),
            )
            if f["t"] == "line" and len(p) == 2:
                ob["length_ft"] = round(
                    float(np.linalg.norm(p[1, :2] - p[0, :2])) / FT, 1
                )
        elif f["t"] == "poly":
            p = np.asarray(f["p"], float).reshape(-1, 3)
            ob = mesh_object(
                name, p, [list(range(len(p)))], c, mats=[M.get(f.get("mat"), M["zone"])]
            )
        elif f["t"] == "marker":
            x, y, z = f["at"]
            sz, h = f.get("size", 0.9), f.get("h", 1.2)
            me = bpy.data.meshes.new(name)
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(name, me)
            ob.scale = (sz, sz, h)
            ob.location = (x, y, z + h / 2)
            me.materials.append(M.get(f.get("mat"), M["placeholder"]))
            c.objects.link(ob)
        if ob is not None:
            for r in info.get("rows", []):
                ob[r[0][:60]] = str(r[1])
            if info.get("note"):
                ob["note"] = info["note"]
            if info.get("tag"):
                ob["basis"] = {
                    "m": "MEASURED",
                    "e": "CALCULATED ESTIMATE",
                    "x": "NOT LOCATED",
                    "p": "PLACEHOLDER",
                }.get(info["tag"], info["tag"])
        if f.get("label"):
            la = f["la"]
            t = label(
                f"{s['key']} label {k}",
                f["label"],
                c,
                (la[0], la[1], la[2] + 0.5),
                0.9,
                M["label_e"] if f.get("lk") in ("est", "trench") else M["label"],
            )
            t.rotation_euler = (math.radians(90), 0, 0)
    t = label(
        f"{s['key']} title",
        s["title"],
        c,
        (s["center"][0], s["center"][1], s["center"][2] + 12),
        2.4,
        M["label"],
    )
    # cameras
    for nm, loc in (("CAM aerial", s["aerial"]), ("CAM eye level", s["eye"])):
        cam = bpy.data.cameras.new(f"{s['key']} {nm}")
        cam.lens = 24 if "eye" in nm else 35
        cam.clip_end = 5000
        ob = bpy.data.objects.new(f"{s['key']} {nm}", cam)
        ob.location = loc
        d = Vector(s["center"]) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        cam_c.objects.link(ob)


def main():
    a = parse_args()
    C = frame.load_config(a.config)
    W = a.work
    J = lambda n: json.load(open(os.path.join(W, n)))  # noqa: E731
    meta = J("meta.json")
    sites = J("sites_resolved.json")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = C.JOB["blend_name"].replace(".blend", "")
    us = scene.unit_settings
    us.system, us.length_unit, us.scale_length = "IMPERIAL", "FEET", 1.0
    lat0, lon0 = (float(v) for v in frame.geodetic(0.0, 0.0))
    scene["SRID"] = f"EPSG:{frame.EPSG}"
    scene["crs x"], scene["crs y"] = frame.E0, frame.N0
    scene["latitude"], scene["longitude"] = lat0, lon0
    scene["lat"], scene["lon"] = lat0, lon0
    scene["crs_note"] = (
        f"NAD83 / UTM 19N (EPSG:{frame.EPSG}) metres; X = E - {frame.E0:.0f}, Y = N - {frame.N0:.0f}; Z = NAVD88 m (no offset)"
    )
    scene["vertical_datum"] = C.FRAME["vertical"]
    scene["job"] = (
        f"JobTread #{C.JOB['number']} - {C.JOB['title']} - PRIVATE, no pricing"
    )
    ground = Ground(W)

    M = {
        "roof": material("Roof (lidar)", (0.32, 0.30, 0.29, 1), 0.7),
        "wall": material("Wall", (0.82, 0.78, 0.70, 1), 0.85),
        "ov_bldg": material("Overview building", (0.75, 0.72, 0.66, 1), 0.9),
        "ov_bldg_x": material("Height not measured", (0.80, 0.40, 0.85, 1), 0.9),
        "trunk": material("Tree trunk", (0.22, 0.15, 0.09, 1), 0.9),
        "leaf": material("Tree crown", (0.16, 0.28, 0.10, 1), 0.9),
        "conifer": material("Tree crown conifer", (0.08, 0.18, 0.08, 1), 0.9),
        "water": material("Water (NHD)", (0.10, 0.25, 0.35, 1), 0.1),
        "stream": material(
            "Stream centreline (NHD)", (0.15, 0.55, 1.0, 1), 0.3, emission=1.5
        ),
        "road": material(
            "Road centreline (OSM)", (0.95, 0.30, 0.85, 1), 0.5, emission=0.6
        ),
        "foot": material("Footway (OSM)", (0.20, 0.85, 0.30, 1), 0.5, emission=0.8),
        "label": material("Label", (0.97, 0.97, 0.95, 1), 0.5, emission=1.5),
        "label_e": material("Label - estimate", (1.0, 0.72, 0.2, 1), 0.5, emission=1.5),
    }
    for k, (nm, col, rough, em, al) in MATS.items():
        M[k] = material(nm, col, rough, emission=em, alpha=al)
        if al < 1.0 and hasattr(M[k], "blend_method"):
            M[k].blend_method = "BLEND"

    names = [
        ("ter", "00 Terrain - USGS 3DEP 1 m DEM (NAVD88)"),
        ("ortho", "01 Orthophoto drape - NOT LOADED (see drape_orthophoto.py)"),
        ("bld", "02 Buildings - lidar roofs (detail)"),
        ("bldo", "02 Buildings - overview (1 mi)"),
        ("tree", "03 Trees - 2019 lidar"),
        ("water", "04 Water - NHD"),
        ("flood", "05 Flood zones FEMA NFHL - NOT LOADED (import_gis_layer.py)"),
        ("wet", "06 Wetlands NWI/NHDES - NOT LOADED (import_gis_layer.py)"),
        ("parcel", "07 Parcels - NOT LOADED (import_gis_layer.py)"),
        ("road", "08 Roads + sidewalks - OSM/Overture"),
        ("util", "09 Utilities - tag on site (import_field_points.py)"),
    ]
    for i, s in enumerate(sites):
        names.append((s["key"], f"{10 + i} {s['title'].replace(' · ', ' - ')}"))
    names += [
        (
            "roof",
            f"{10 + len(sites)} Roof levels - 2019 lidar (see docs/ROOF_LEVELS.md)",
        ),
        ("cam", "20 Cameras + lights"),
        (
            "goog",
            "30 Google 3D Tiles - optional, VISUAL ONLY, only with your own key (google_tiles_to_utm.py)",
        ),
    ]
    CL = {k: coll(n) for k, n in names}

    # ---- terrain
    det = meta["detail_box"]
    d = np.load(os.path.join(W, "dem_detail.npz"))
    m_ground, nt, tex = image_material(
        "Ground - lidar intensity composite (NOT a photo)",
        os.path.join(W, "ground_detail.png"),
        "ground_lidar_composite.png",
    )
    ter = grid_terrain(
        "Terrain detail 1 m (USGS 3DEP NH_Coastal_2019, NAVD88)",
        d["z"].astype(float),
        float(d["x0"]),
        float(d["y0"]),
        float(d["step"]),
        CL["ter"],
        [m_ground],
        uv_box=tuple(det),
    )
    ter["source"] = meta["layers"]["terrain"]["source"]
    ter["accuracy"] = meta["layers"]["terrain"]["accuracy"]
    o = np.load(os.path.join(W, "dem_overview.npz"))
    zo = o["z"].astype(float)
    ox0, oy0, ost = float(o["x0"]), float(o["y0"]), float(o["step"])
    ny, nx = zo.shape
    cxs = ox0 + (np.arange(nx - 1) + 0.5) * ost
    cys = oy0 - (np.arange(ny - 1) + 0.5) * ost
    outside = ~(
        (cxs[None, :] > det[0])
        & (cxs[None, :] < det[2])
        & (cys[:, None] > det[1])
        & (cys[:, None] < det[3])
    )
    m_ov = material("Terrain overview (8 m)", (0.45, 0.50, 0.38, 1), 0.95)
    grid_terrain(
        "Terrain overview 8 m (to 1 mi)",
        zo - 0.3,
        ox0,
        oy0,
        ost,
        CL["ter"],
        [m_ov],
        mask=outside,
    )

    # ---- empty layers say which tool fills them
    for k, tool in (
        ("ortho", "drape_orthophoto.py"),
        ("flood", "import_gis_layer.py"),
        ("wet", "import_gis_layer.py"),
        ("parcel", "import_gis_layer.py"),
        ("util", "import_field_points.py"),
        ("goog", "google_tiles_to_utm.py"),
    ):
        e = bpy.data.objects.new(f"EMPTY - fill with {tool}", None)
        CL[k].objects.link(e)

    # ---- buildings, trees, roads, water
    extra = (
        J("buildings_extra.json")
        if os.path.exists(os.path.join(W, "buildings_extra.json"))
        else []
    )
    build_buildings_detail(
        J("buildings_detail.json") + extra, CL["bld"], (M["roof"], M["wall"])
    )
    build_buildings_overview(
        J("buildings_overview.json"), CL["bldo"], M["ov_bldg"], M["ov_bldg_x"]
    )
    T = np.load(os.path.join(W, "trees.npy")).astype(float)
    if len(T):
        build_trees(T, CL["tree"], [M["trunk"], M["leaf"], M["conifer"]])
    for r in J("roads.json"):
        if not r["line"]:
            continue
        foot = r["class"] in ("footway", "sidewalk", "path", "steps", "pedestrian")
        ob = draped_curve(
            f"{'Footway' if foot else 'Road'} {r['name'] or r['class'] or ''}".strip(),
            r["line"],
            ground,
            CL["road"],
            M["foot" if foot else "road"],
            0.12,
        )
        if ob is not None:
            ob["source"] = "Overture/OSM centreline; width NOT measured"
    Wt = J("water.json")
    for f in Wt["flowlines"]:
        for ln in f["geom"]["coordinates"]:
            draped_curve(
                f"Stream {f['name'] or ''}".strip(),
                np.asarray(ln)[:, :2],
                ground,
                CL["water"],
                M["stream"],
                0.25,
                lift=0.3,
            )

    # ---- sites (same features as the web viewer)
    for s in sites:
        build_site(s, CL[s["key"]], M, CL["cam"])

    # ---- roof levels (one marker per measured terminal roof level)
    A = J("analysis.json")
    for lv in A["terminal_roof_levels"]:
        e = bpy.data.objects.new(
            f"Roof level {lv['z_m']:.2f} m NAVD88 = {lv['above_grade_ft']} ft above grade, {lv['area_sqft']:,} sq ft",
            None,
        )
        e.location = (*meta["center"]["local_xy"], lv["z_m"])
        e.empty_display_type = "PLAIN_AXES"
        e.empty_display_size = 3
        CL["roof"].objects.link(e)

    # ---- light + default camera
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.0
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (math.radians(40), 0, math.radians(150))
    CL["cam"].objects.link(so)
    cams = [ob for ob in CL["cam"].objects if ob.type == "CAMERA"]
    if cams:
        scene.camera = cams[0]
    scene.render.engine = (
        "BLENDER_EEVEE_NEXT"
        if "BLENDER_EEVEE_NEXT"
        in [
            e.identifier
            for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
        ]
        else scene.render.engine
    )

    # ---- embedded docs and tools
    job = C.JOB_DIR
    for fn in (
        "README.md",
        "ROUTE_LENGTHS.md",
        "MISSING_MEASUREMENTS.md",
        "SOURCE_LOG.md",
        "NEXT_PHOTO_LIST.md",
        "docs/SITE_LAYOUTS.md",
        "docs/ROOF_LEVELS.md",
    ):
        pth = os.path.join(job, fn)
        if os.path.exists(pth):
            t = bpy.data.texts.new(os.path.basename(fn))
            t.write(open(pth).read())
    for fn in TOOLS:
        t = bpy.data.texts.new(fn)
        t.write(open(os.path.join(job, "tools", fn)).read())
    scene["checks"] = json.dumps(meta["checks"])
    scene["center"] = json.dumps(meta["center"])

    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, C.JOB["blend_name"])
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True, relative_remap=True)
    print("saved", path, f"{os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
    os._exit(0)  # headless bpy can hang on exit
