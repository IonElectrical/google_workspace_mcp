"""Build one Blender file per Wilton #1976 site from prepare_data.py output.

Blender (4.5 LTS recommended):
    blender -b --factory-startup -P build_site_blend.py -- --work WORK --out OUT [--blosm DIR]
or with the `bpy` wheel:
    python build_site_blend.py --work WORK --out OUT [--blosm DIR] [--previews]

--blosm points at a folder that contains the `blosm` add-on folder; when given, the
Blosm panel in each file is pre-filled (Google 3D Tiles, extent of the site). Only numpy
and Blender's own modules are used here.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sites  # noqa: E402

FT = 0.3048
PIN_H = 16.0  # pin height (m) so pins show above most village roofs
ORANGE = (1.0, 0.35, 0.02, 1.0)
BLUE = (0.10, 0.35, 0.95, 1.0)


# --------------------------------------------------------------------------- basics


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--blosm", default=None, help="folder containing the blosm add-on folder"
    )
    ap.add_argument("--sites", nargs="*", default=[s["key"] for s in sites.SITES])
    ap.add_argument(
        "--previews", action="store_true", help="render PNG previews with Cycles (CPU)"
    )
    return ap.parse_args(argv)


def enable_blosm(path):
    import addon_utils

    if path and path not in sys.path:
        sys.path.insert(0, path)
    bpy.context.preferences.use_preferences_save = False
    mod = addon_utils.enable("blosm", default_set=True)
    return mod is not None and hasattr(bpy.context.scene, "blosm")


def collection(name, parent=None, hide_render=False):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    c.hide_render = hide_render
    return c


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


class Terrain:
    """Bilinear lookup of the 1 m terrain grid (row 0 = north)."""

    def __init__(self, xyz, half, step):
        self.xyz, self.half, self.step = xyz, half, step
        self.n = xyz.shape[0]

    def z(self, x, y):
        x = np.clip(np.atleast_1d(x), -self.half, self.half)
        y = np.clip(np.atleast_1d(y), -self.half, self.half)
        c = (x + self.half) / self.step
        r = (self.half - y) / self.step
        c0 = np.clip(np.floor(c).astype(int), 0, self.n - 2)
        r0 = np.clip(np.floor(r).astype(int), 0, self.n - 2)
        fc, fr = c - c0, r - r0
        z = self.xyz[..., 2]
        return (
            z[r0, c0] * (1 - fc) * (1 - fr)
            + z[r0, c0 + 1] * fc * (1 - fr)
            + z[r0 + 1, c0] * (1 - fc) * fr
            + z[r0 + 1, c0 + 1] * fc * fr
        )

    def drape(self, xy, lift=0.15):
        xy = np.asarray(xy, dtype=np.float64)
        return np.column_stack([xy, self.z(xy[:, 0], xy[:, 1]) + lift])


def blosm_center_f32(lat, lon):
    """Blosm's scene origin exactly as it computes it: BaseManager.fromGeographic(lat, lon, 0.)
    in blosm/threed_tiles/manager.py, which works in mathutils' 32-bit floats. Its rounding
    (up to ~0.3 m at ECEF magnitudes) shifts every imported tile by one constant vector."""
    rs = (6378137.0**2, 6378137.0**2, 6356752.3142451793**2)
    la, lo = math.radians(lat), math.radians(lon)
    cl = math.cos(la)
    n = Vector((cl * math.cos(lo), cl * math.sin(lo), math.sin(la)))
    n.normalize()
    k = Vector((rs[0] * n[0], rs[1] * n[1], rs[2] * n[2]))
    k /= math.sqrt(n.dot(k))
    n *= 0.0
    return k + n


def blosm_offset(lat, lon):
    """Constant offset between our float64 frame and where Blosm puts imported tiles."""
    frame = sites.BlosmFrame(lat, lon)
    c32 = np.array(blosm_center_f32(lat, lon)[:], dtype=np.float64)
    return frame.q @ (frame.origin - c32), c32


def point_in_poly(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


# --------------------------------------------------------------------------- layers


def build_terrain(xyz, img_path, coll):
    n = xyz.shape[0]
    verts = xyz.reshape(-1, 3)
    idx = np.arange(n * n).reshape(n, n)
    faces = np.stack(
        [idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:], idx[:-1, :-1]], -1
    ).reshape(-1, 4)
    # pack the PNG bytes under a relative name so no build-machine path ends up in the file
    blob = open(img_path, "rb").read()
    img = bpy.data.images.new("ground_lidar_landuse.png", 8, 8)
    img.source = "FILE"
    img.filepath_raw = "//textures/ground_lidar_landuse.png"
    img.pack(data=blob, data_len=len(blob))
    img.reload()
    m = bpy.data.materials.new("Ground (lidar intensity + land use)")
    m.use_nodes = True
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Cubic"
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.92
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    ob = mesh_object(
        "Terrain (USGS lidar 2019)", verts, faces, coll, mats=[m], smooth=True
    )
    uv = ob.data.uv_layers.new(name="UVMap")
    vi = np.empty(len(ob.data.loops), dtype=np.int32)
    ob.data.loops.foreach_get("vertex_index", vi)
    row, col = np.divmod(vi, n)
    uvs = np.column_stack([col / (n - 1), 1.0 - row / (n - 1)]).astype(np.float32)
    uv.data.foreach_set("uv", uvs.ravel())
    return ob


def build_buildings(buildings, coll, mats):
    roof, wall, roof_x, wall_x = mats
    objs = []
    for i, b in enumerate(buildings):
        xy = np.asarray(b["roof_xy"])
        z = np.asarray(b["roof_z"])
        top = np.column_stack([xy, z])
        verts = list(map(tuple, top))
        faces = [tuple(f) for f in b["roof_faces"]]
        mat_idx = [0] * len(faces)
        rings, start = [b["n_ring"]] + list(b["hole_rings"]), 0
        base = b["base_z"] - 0.3
        for k in rings:
            ids = list(range(start, start + k))
            bot0 = len(verts)
            verts.extend((xy[j, 0], xy[j, 1], base) for j in ids)
            for a in range(k):
                c = (a + 1) % k
                faces.append((ids[a], ids[c], bot0 + c, bot0 + a))
                mat_idx.append(1)
            start += k
        label = b["name"] or f"Bldg_{i + 1:03d}"
        if not b["lidar_roof"]:
            label += " (no 2019 lidar - height estimated)"
        ob = mesh_object(
            label,
            verts,
            faces,
            coll,
            mats=[roof, wall] if b["lidar_roof"] else [roof_x, wall_x],
            mat_index=mat_idx,
        )
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        ob["overture_id"] = b["id"] or ""
        ob["height_ft"] = round((b["top_z"] - b["base_z"]) / FT, 1)
        objs.append(ob)
    return objs


def build_trees(trees, coll, mats):
    rng = np.random.default_rng(1976)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    ico_v = np.array([v.co[:] for v in bm.verts])
    ico_f = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    seg = 7
    ang = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    ring = np.column_stack([np.cos(ang), np.sin(ang)])
    verts, faces, mid = [], [], []
    for x, y, gz, h, cr in trees:
        conifer = rng.random() < 0.3
        rot = rng.random() * math.tau
        o = len(verts)
        tr = float(np.clip(0.012 * h, 0.12, 0.45))
        verts += [(x + tr * c, y + tr * s, gz - 0.3) for c, s in ring]
        verts += [(x + tr * c, y + tr * s, gz + 0.55 * h) for c, s in ring]
        for a in range(seg):
            b = (a + 1) % seg
            faces.append((o + a, o + b, o + seg + b, o + seg + a))
            mid.append(0)
        o = len(verts)
        if conifer:
            r = 0.8 * cr
            verts += [
                (x + r * math.cos(t + rot), y + r * math.sin(t + rot), gz + 0.22 * h)
                for t in ang
            ]
            verts.append((x, y, gz + h))
            for a in range(seg):
                faces.append((o + a, o + (a + 1) % seg, o + seg))
                mid.append(2)
            faces.append(tuple(o + a for a in reversed(range(seg))))
            mid.append(2)
        else:
            sz = 0.36 * h
            cz = gz + h - sz
            s = 0.85 + 0.3 * rng.random()
            verts += [
                (x + v[0] * cr * s, y + v[1] * cr / s, cz + v[2] * sz) for v in ico_v
            ]
            faces += [tuple(o + k for k in f) for f in ico_f]
            mid += [1] * len(ico_f)
    return mesh_object(
        "Trees (lidar 2019)", verts, faces, coll, mats=mats, mat_index=mid
    )


def trench_node_group(mat_tube, mat_text):
    """Geometry nodes for trench curves: 0.4 m tube + live length label in feet."""
    ng = bpy.data.node_groups.new("Trench route + length (ft)", "GeometryNodeTree")
    ng.interface.new_socket(
        "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    ng.interface.new_socket(
        "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    nd, ln = ng.nodes, ng.links
    gi = nd.new("NodeGroupInput")
    go = nd.new("NodeGroupOutput")

    circle = nd.new("GeometryNodeCurvePrimitiveCircle")
    circle.inputs["Radius"].default_value = 0.2
    circle.inputs["Resolution"].default_value = 8
    tube = nd.new("GeometryNodeCurveToMesh")
    ln.new(gi.outputs[0], tube.inputs["Curve"])
    ln.new(circle.outputs["Curve"], tube.inputs["Profile Curve"])
    set_tube = nd.new("GeometryNodeSetMaterial")
    set_tube.inputs["Material"].default_value = mat_tube
    ln.new(tube.outputs["Mesh"], set_tube.inputs["Geometry"])

    length = nd.new("GeometryNodeCurveLength")
    ln.new(gi.outputs[0], length.inputs["Curve"])
    feet = nd.new("ShaderNodeMath")
    feet.operation = "MULTIPLY"
    feet.inputs[1].default_value = 1.0 / FT
    ln.new(length.outputs["Length"], feet.inputs[0])
    v2s = nd.new("FunctionNodeValueToString")
    v2s.inputs["Decimals"].default_value = 0
    ln.new(feet.outputs[0], v2s.inputs["Value"])

    mid = nd.new("GeometryNodeSampleCurve")
    mid.mode = "FACTOR"
    ln.new(gi.outputs[0], mid.inputs["Curves"])
    mid.inputs["Factor"].default_value = 0.5
    lift = nd.new("ShaderNodeVectorMath")
    lift.operation = "ADD"
    lift.inputs[1].default_value = (0.0, 0.0, 2.5)
    ln.new(mid.outputs["Position"], lift.inputs[0])

    def label(string_socket=None, text=None, align="LEFT"):
        s2c = nd.new("GeometryNodeStringToCurves")
        s2c.align_x = align
        s2c.align_y = "MIDDLE"
        s2c.inputs["Size"].default_value = 3.0
        if string_socket is not None:
            ln.new(string_socket, s2c.inputs["String"])
        else:
            s2c.inputs["String"].default_value = text
        real = nd.new("GeometryNodeRealizeInstances")
        ln.new(s2c.outputs["Curve Instances"], real.inputs["Geometry"])
        fill = nd.new("GeometryNodeFillCurve")
        ln.new(real.outputs["Geometry"], fill.inputs["Curve"])
        move = nd.new("GeometryNodeTransform")
        ln.new(fill.outputs["Mesh"], move.inputs["Geometry"])
        ln.new(lift.outputs["Vector"], move.inputs["Translation"])
        return move

    num = label(string_socket=v2s.outputs["String"], align="RIGHT")
    unit = label(text=" ft", align="LEFT")
    join_txt = nd.new("GeometryNodeJoinGeometry")
    ln.new(num.outputs["Geometry"], join_txt.inputs["Geometry"])
    ln.new(unit.outputs["Geometry"], join_txt.inputs["Geometry"])
    set_txt = nd.new("GeometryNodeSetMaterial")
    set_txt.inputs["Material"].default_value = mat_text
    ln.new(join_txt.outputs["Geometry"], set_txt.inputs["Geometry"])

    join = nd.new("GeometryNodeJoinGeometry")
    ln.new(set_tube.outputs["Geometry"], join.inputs["Geometry"])
    ln.new(set_txt.outputs["Geometry"], join.inputs["Geometry"])
    ln.new(join.outputs["Geometry"], go.inputs[0])
    for i, node in enumerate(nd):
        node.location = (200 * (i % 6), -180 * (i // 6))
    return ng


def box_verts(cx, cy, z0, sx, sy, sz):
    xs, ys = (cx - sx / 2, cx + sx / 2), (cy - sy / 2, cy + sy / 2)
    v = [(x, y, z) for z in (z0, z0 + sz) for y in ys for x in xs]
    f = [
        (0, 2, 3, 1),
        (4, 5, 7, 6),
        (0, 1, 5, 4),
        (1, 3, 7, 5),
        (3, 2, 6, 7),
        (2, 0, 4, 6),
    ]
    return v, f


# --------------------------------------------------------------------------- scene


def build_site(site, work, out_dir, blosm_ok, previews):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if blosm_ok:
        enable_blosm(None)
    d = os.path.join(work, site["key"])
    meta = json.load(open(os.path.join(d, "meta.json")))
    buildings = json.load(open(os.path.join(d, "buildings.json")))
    xyz = np.load(os.path.join(d, "terrain_xyz.npy")).astype(np.float64)
    trees = np.load(os.path.join(d, "trees.npy")).astype(np.float64)
    half = meta["radius_m"]
    ter = Terrain(xyz, half, meta["terrain_step"])

    scene = bpy.context.scene
    scene.name = sites.blend_name(site)
    scene.unit_settings.system = "IMPERIAL"
    scene.unit_settings.length_unit = "FEET"
    scene.unit_settings.scale_length = 1.0
    # Blosm reads these to place later imports (Google 3D Tiles) relative to this file
    scene["lat"] = float(site["lat"])
    scene["lon"] = float(site["lon"])
    scene["job"] = "Ion Electrical #1976 - Wilton NH RANH Level 2 EV chargers"

    m_roof = material("Roof (lidar)", (0.30, 0.28, 0.27, 1), 0.7)
    m_wall = material("Wall", (0.80, 0.76, 0.68, 1), 0.85)
    m_roof_x = material("Roof (no lidar, estimated)", (0.45, 0.30, 0.50, 1), 0.7)
    m_wall_x = material("Wall (no lidar, estimated)", (0.80, 0.70, 0.85, 1), 0.85)
    m_trunk = material("Tree trunk", (0.22, 0.15, 0.09, 1), 0.9)
    m_leaf = material("Tree crown deciduous", (0.15, 0.27, 0.09, 1), 0.9)
    m_conifer = material("Tree crown conifer", (0.07, 0.17, 0.08, 1), 0.9)
    m_label = material("Label white", (0.95, 0.95, 0.95, 1), 0.5, emission=1.5)
    m_line = material("Extent line", (1.0, 0.85, 0.1, 1), 0.5, emission=2.0)
    m_ring = material("Distance ring", (1.0, 1.0, 1.0, 1), 0.5, emission=1.0)
    m_here = material("Pin - this site", ORANGE, 0.4, emission=2.5)
    m_other = material("Pin - other sites", BLUE, 0.4, emission=1.5)
    m_trench = material("Trench route", (0.95, 0.12, 0.05, 1), 0.5, emission=1.0)
    m_conc = material("Concrete pad", (0.70, 0.69, 0.66, 1), 0.8)
    m_charger = material("Charger body", (0.12, 0.13, 0.14, 1), 0.35)
    m_screen = material("Charger accent", (0.10, 0.75, 0.35, 1), 0.3, emission=1.0)
    m_stall = material("Stall striping", (0.98, 0.98, 0.95, 1), 0.6, emission=0.3)
    m_service = material("Service point", (1.0, 0.80, 0.0, 1), 0.4, emission=2.0)

    c_base = collection("Open data base (USGS lidar + Overture)")
    c_ter = collection("Terrain", c_base)
    c_bld = collection("Buildings (lidar roofs)", c_base)
    c_tree = collection("Trees (lidar)", c_base)
    c_lab = collection("Labels", c_base)
    c_site = collection("Site pins + rings")
    c_plan = collection("Planning - EDIT ME (chargers, stalls, trench)")
    c_cam = collection("Cameras + lights")

    build_terrain(xyz, os.path.join(d, "ground.png"), c_ter)
    build_buildings(buildings, c_bld, (m_roof, m_wall, m_roof_x, m_wall_x))
    if len(trees):
        build_trees(trees, c_tree, (m_trunk, m_leaf, m_conifer))

    # ---- street and landmark labels
    seen = {}
    for r in meta["roads"]:
        if not r["line"]:
            continue
        line = np.asarray(r["line"])
        inside = (np.abs(line[:, 0]) < half * 0.8) & (np.abs(line[:, 1]) < half * 0.8)
        if inside.sum() < 2:
            continue
        seg = line[inside]
        length = np.linalg.norm(np.diff(seg, axis=0), axis=1).sum()
        if length > seen.get(r["name"], (0,))[0]:
            seen[r["name"]] = (length, seg)
    for name, (_, seg) in seen.items():
        k = len(seg) // 2
        a, b = seg[max(k - 1, 0)], seg[min(k + 1, len(seg) - 1)]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        if ang > math.pi / 2 or ang < -math.pi / 2:
            ang += math.pi
        mx, my = seg[k]
        text_object(
            f"Street - {name}",
            name.upper(),
            c_lab,
            (mx, my, float(ter.z(mx, my)[0]) + 0.6),
            3.2,
            m_label,
            rot=(0, 0, ang),
        )
    landmark_cats = {
        "police_station",
        "library",
        "government_office",
        "theatre_venue",
        "post_office",
        "shipping_or_delivery_service",
        "place_of_worship",
        "church_cathedral",
    }
    for p in meta["pois"]:
        if p["category"] in landmark_cats and p["name"]:
            x, y = p["xy"]
            t = text_object(
                f"Landmark - {p['name']}",
                p["name"],
                c_lab,
                (x, y, p["z"] + 7.0),
                1.8,
                m_label,
            )
            t["category"] = p["category"]

    # ---- site pins (all three), rings and the Blosm import extent
    pins = {p["key"]: Vector(p["xyz"]) for p in meta["pins"]}
    here = pins[site["key"]]
    aim = bpy.data.objects.new("AIM - camera target (move me)", None)
    aim.location = here + Vector((0, 0, 2.0))
    aim.empty_display_size = 3
    c_cam.objects.link(aim)
    pin_labels = []
    for s in sites.SITES:
        p = pins[s["key"]]
        is_here = s["key"] == site["key"]
        mat = m_here if is_here else m_other
        v, f = box_verts(p.x, p.y, p.z - 0.5, 0.3, 0.3, PIN_H + 0.5)
        mesh_object(f"PIN {s['title']}", v, f, c_site, mats=[mat])
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=1.0, location=(p.x, p.y, p.z + PIN_H)
        )
        ball = bpy.context.active_object
        ball.name = f"PIN head {s['key']}"
        ball.data.materials.append(mat)
        for c in ball.users_collection:
            c.objects.unlink(ball)
        c_site.objects.link(ball)
        lab = text_object(
            f"PIN label {s['key']}",
            s["title"],
            c_site,
            (p.x, p.y, p.z + PIN_H + 3.0),
            2.6 if is_here else 2.0,
            mat,
            extrude=0.05,
        )
        pin_labels.append(lab)

    for ft in (50, 100, 200):
        r = ft * FT
        a = np.linspace(0, 2 * math.pi, 145)[:-1]
        pts = ter.drape(
            np.column_stack([here.x + r * np.cos(a), here.y + r * np.sin(a)]), 0.12
        )
        poly_curve(f"Ring {ft} ft", pts, c_site, 0.06, m_ring, cyclic=True)
        lx, ly = here.x, here.y - r
        text_object(
            f"Ring label {ft} ft",
            f"{ft} ft",
            c_site,
            (lx, ly - 1.8, float(ter.z(lx, ly - 1.8)[0]) + 0.4),
            2.0,
            m_ring,
        )
    edge = np.linspace(-half, half, 201)
    sq = np.concatenate(
        [
            np.column_stack([edge, np.full_like(edge, -half)]),
            np.column_stack([np.full_like(edge, half), edge]),
            np.column_stack([edge[::-1], np.full_like(edge, half)]),
            np.column_stack([np.full_like(edge, -half), edge[::-1]]),
        ]
    )
    poly_curve(
        "Import extent (Blosm / Google tiles box)",
        ter.drape(sq, 0.3),
        c_site,
        0.25,
        m_line,
        cyclic=True,
    )

    # ---- planning kit placed on the nearest paved ground clear of buildings
    rings = [b["footprint"] for b in buildings]
    paved_img = bpy.data.images.load(os.path.join(d, "paved_mask.png"))
    pw = paved_img.size[0]
    paved = (
        np.array(paved_img.pixels[:]).reshape(pw, pw, -1)[..., 0] > 0.5
    )  # row 0 = south
    bpy.data.images.remove(paved_img)
    gres = meta["ground_res"]

    def in_building(x, y, margin=0.0):
        probes = (
            [(x, y)]
            if not margin
            else [
                (x, y),
                (x + margin, y),
                (x - margin, y),
                (x, y + margin),
                (x, y - margin),
            ]
        )
        near = [r for r in rings if abs(r[0][0] - x) < 90 and abs(r[0][1] - y) < 90]
        return any(point_in_poly(px, py, r) for px, py in probes for r in near)

    def is_paved(x, y):
        c, r = int((x + half) / gres), int((y + half) / gres)
        return 0 <= c < pw and 0 <= r < pw and bool(paved[r, c])

    def open_spot(cx, cy, rmax):
        for r in np.arange(0.0, rmax, 1.5):
            for t in np.linspace(0, 2 * math.pi, max(8, int(r * 2)), endpoint=False):
                x, y = cx + r * math.cos(t), cy + r * math.sin(t)
                if is_paved(x, y) and not in_building(x, y, 3.0):
                    return x, y, t
        return cx, cy, 0.0

    cx, cy, heading = open_spot(here.x, here.y, 60.0)
    cz = float(ter.z(cx, cy)[0])
    kit = bpy.data.objects.new("CHARGER KIT - move/rotate me", None)
    kit.empty_display_type = "ARROWS"
    kit.empty_display_size = 2
    kit.location = (cx, cy, cz)
    kit.rotation_euler = (0, 0, heading)
    c_plan.objects.link(kit)
    parts = [
        (
            "L2 pedestal (dual port) example",
            box_verts(0, 0, 0.15, 0.32, 0.28, 1.75),
            m_charger,
        ),
        ("Pedestal screen", box_verts(0, -0.145, 1.25, 0.24, 0.02, 0.32), m_screen),
        ("Concrete pad 30x24 in", box_verts(0, 0, -0.05, 0.76, 0.61, 0.2), m_conc),
    ]
    for name, (v, f), mat in parts:
        ob = mesh_object(name, v, f, c_plan, mats=[mat])
        ob.parent = kit
    sw, sl, stripe = 9 * FT, 18 * FT, 0.1
    for k, off in enumerate((-sw / 2, sw / 2)):
        v, f = [], []
        for x0 in (off - sw / 2, off + sw / 2):
            vv, ff = box_verts(x0, -0.6 - sl / 2, 0.0, stripe, sl, 0.02)
            f += [tuple(i + len(v) for i in fc) for fc in ff]
            v += vv
        ob = mesh_object(f"Stall {k + 1} 9x18 ft", v, f, c_plan, mats=[m_stall])
        ob.parent = kit
    kit.location.z = cz + 0.02

    for turn in np.linspace(0.9, 0.9 + 2 * math.pi, 12, endpoint=False):
        sx, sy = cx + 18 * math.cos(heading + turn), cy + 18 * math.sin(heading + turn)
        if not in_building(sx, sy, 1.0):
            break
    sz = float(ter.z(sx, sy)[0])
    v, f = box_verts(sx, sy, sz, 0.8, 0.8, 1.6)
    svc = mesh_object(
        "SERVICE POINT (move to actual panel/transformer)",
        v,
        f,
        c_plan,
        mats=[m_service],
    )
    text_object("SERVICE label", "SERVICE", c_plan, (sx, sy, sz + 3.2), 1.6, m_service)
    route_xy = np.array([[sx, sy], [sx, cy], [cx, cy]])
    dense = np.concatenate(
        [
            np.linspace(route_xy[i], route_xy[i + 1], 12, endpoint=False)
            for i in range(2)
        ]
        + [route_xy[-1:]]
    )
    trench = poly_curve(
        "TRENCH route example (edit points)",
        ter.drape(dense, 0.05),
        c_plan,
        0.0,
        m_trench,
    )
    mod = trench.modifiers.new("Trench + length label", "NODES")
    mod.node_group = trench_node_group(m_trench, m_label)
    svc["note"] = (
        "Placeholder. Move to the service/panel location found on the site visit."
    )

    # ---- cameras + lights
    def camera(name, loc, lens=32.0, ortho=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.clip_start = 0.5
        cd.clip_end = 3000.0
        if ortho:
            cd.type = "ORTHO"
            cd.ortho_scale = ortho
        cam = bpy.data.objects.new(name, cd)
        cam.location = loc
        con = cam.constraints.new("TRACK_TO")
        con.target = aim
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
        c_cam.objects.link(cam)
        return cam

    cam_se = camera("CAM Aerial from SE", here + Vector((85, -95, 65)))
    camera("CAM Aerial from NW", here + Vector((-90, 85, 60)))
    plan = camera(
        "CAM Plan view (ortho, 150 m wide)", here + Vector((0, 0.01, 300)), ortho=150.0
    )
    plan.constraints.clear()
    plan.rotation_euler = (0, 0, 0)
    # street-level view: a point on a named street 20-50 m away with a clear view of the kit
    depsgraph = bpy.context.evaluated_depsgraph_get()
    kit_aim = bpy.data.objects.new("AIM street camera (move me)", None)
    kit_aim.location = (cx, cy, cz + 1.2)
    kit_aim.empty_display_size = 1.5
    c_cam.objects.link(kit_aim)
    best = None
    for r in meta["roads"]:
        if not r["line"]:
            continue
        line = np.asarray(r["line"])
        for a, b in zip(line[:-1], line[1:]):
            for f in np.linspace(0, 1, max(2, int(np.linalg.norm(b - a) / 2.0))):
                ex, ey = a + f * (b - a)
                dist = math.hypot(ex - cx, ey - cy)
                if not 20.0 <= dist <= 50.0 or (best and abs(dist - 32) >= best[0]):
                    continue
                eye = Vector((ex, ey, float(ter.z(ex, ey)[0]) + 1.7))
                dirv = kit_aim.location - eye
                hit, *_ = scene.ray_cast(
                    depsgraph, eye, dirv.normalized(), distance=dirv.length - 2.0
                )
                if not hit:
                    best = (abs(dist - 32), eye)
    cam_street = camera(
        "CAM Street level",
        best[1] if best else here + Vector((25, -25, 1.7)),
        lens=24.0,
    )
    cam_street.constraints[0].target = kit_aim
    for lab in pin_labels:
        con = lab.constraints.new("TRACK_TO")
        con.target = cam_se
        con.track_axis = "TRACK_Z"
        con.up_axis = "UP_Y"
    for ob in c_lab.objects:
        if ob.name.startswith("Landmark"):
            con = ob.constraints.new("TRACK_TO")
            con.target = cam_se
            con.track_axis = "TRACK_Z"
            con.up_axis = "UP_Y"
            ob.hide_render = True  # orientation aid in the viewport only
    for ob in scene.objects:
        if ob.type in {"FONT", "CURVE"} or ob.users_collection[0] in (c_site, c_lab):
            ob.visible_shadow = False
    scene.camera = cam_se

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.data.angle = math.radians(1.5)
    sun.rotation_euler = Euler((math.radians(50), 0, math.radians(35)))
    c_cam.objects.link(sun)
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.55,
        0.68,
        0.86,
        1,
    )
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.filepath = "//renders/"
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass

    # ---- Blosm panel pre-filled for the Google 3D Tiles import
    ext = meta["extent"]
    if blosm_ok:
        b = scene.blosm
        b.dataType = "3d-tiles"
        b.threedTilesSource = "google"
        b.lodOf3dTiles = "lod5"
        b.join3dTilesObjects = True
        b.relativeToInitialImport = True
        b.minLon, b.minLat, b.maxLon, b.maxLat = ext

    # ---- viewport: frame the site, show textures, open the sidebar
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    sp.clip_start = 0.1
                    sp.clip_end = 5000.0
                    sp.shading.type = "SOLID"
                    sp.shading.color_type = "TEXTURE"
                    sp.show_region_ui = True
                    r3d = sp.region_3d
                    r3d.view_location = here
                    r3d.view_distance = 260.0
                    r3d.view_rotation = Euler(
                        (math.radians(55), 0, math.radians(30))
                    ).to_quaternion()
                    r3d.view_perspective = "PERSP"

    # ---- notes inside the file
    readme = bpy.data.texts.new("README_SITE")
    readme.write(site_readme(site, meta))
    align = bpy.data.texts.new("align_google_tiles.py")
    align.write(
        open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "align_google_tiles.py"
            )
        ).read()
    )

    # ---- match Blosm's float32 scene origin so imported Google tiles sit exactly on this model
    delta, c32 = blosm_offset(site["lat"], site["lon"])
    for ob in scene.objects:
        if ob.parent is None:
            ob.location += Vector(delta)
    scene["blosm_center_ecef_f32"] = [float(v) for v in c32]
    scene["blosm_offset_applied_m"] = [round(float(v), 4) for v in delta]
    for screen in bpy.data.screens:
        for area in screen.areas:
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    sp.region_3d.view_location = here + Vector(delta)

    for ob in scene.objects:
        ob.select_set(False)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, sites.blend_name(site) + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print(f"saved {path} ({os.path.getsize(path) / 1e6:.1f} MB)")

    if previews:
        render_previews(scene, out_dir, site, [cam_se, plan, cam_street])
    return path


def render_previews(scene, out_dir, site, cams):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    os.makedirs(os.path.join(out_dir, "previews"), exist_ok=True)
    for cam in cams:
        scene.camera = cam
        tag = cam.name.split(" ")[1].lower()
        scene.render.filepath = os.path.join(
            out_dir, "previews", f"{sites.blend_name(site)}_{tag}.png"
        )
        bpy.ops.render.render(write_still=True)
        print("rendered", scene.render.filepath)


def site_readme(site, meta):
    pins = "\n".join(
        f"  {p['title']}: local x={p['xyz'][0]:.1f} m, y={p['xyz'][1]:.1f} m"
        for p in meta["pins"]
    )
    return f"""ION ELECTRICAL - JOB #1976 - WILTON NH - RANH LEVEL 2 PUBLIC CHARGERS
{site["title"]}
{site["address"]}
Center: {site["lat"]}, {site["lon"]}   Box: {2 * meta["radius_m"]:.0f} x {2 * meta["radius_m"]:.0f} m (+/-{meta["radius_m"] / FT:.0f} ft)

WHAT IS IN THIS FILE (all real-world scale, 1 Blender unit = 1 m, UI shows feet)
  Open data base (USGS lidar + Overture)
    Terrain        USGS 3DEP 2019 1 m bare-earth DEM, textured with lidar intensity + roads/water
    Buildings      Overture footprints, roof heights/shapes from the 2019 lidar points
                   (purple = no 2019 lidar returns, height estimated - new or removed since 2019?)
    Trees          tree tops detected in the 2019 lidar canopy (height + crown size)
    Labels         street names, landmarks
  Site pins + rings   orange = this site, blue = the other two sites; 50/100/200 ft rings;
                      yellow box = the Google 3D Tiles import extent
  Planning - EDIT ME  example L2 pedestal on pad + two 9x18 ft stalls (move the CHARGER KIT empty),
                      SERVICE POINT placeholder, and a TRENCH route curve that shows its length in feet.
  Cameras + lights    aerial SE / NW, plan (ortho), street level - all aim at the AIM empty.

Other sites in this model:
{pins}

ADD GOOGLE PHOTOREALISTIC 3D TILES (Blosm add-on, Google key in Blosm preferences)
  1. Press N in the 3D viewport, open the Blosm tab.
  2. The extent is already filled in. If it is blank, copy this line, then click "paste"
     in the Blosm panel:
        {meta["paste"]}
  3. Dropdown next to import: 3D Tiles. Source: Google. Level of details: buildings with
     details. Keep "Relative to initial import" ON so the tiles land on top of this model.
  4. Click import. Then open the Scripting tab, select align_google_tiles.py, and click
     Run Script - it snaps the Google mesh vertically onto the lidar terrain.

TRENCH LENGTHS
  Select "TRENCH route example", Tab into Edit Mode, move points (G), add points (E).
  Turn on snapping (magnet icon) to "Face Project" so the route follows the ground.
  The label updates live in feet. Shift+D to duplicate for more routes.

SOURCES / ATTRIBUTION
  {chr(10).join("  " + s for s in meta["sources"])}
  Google 3D Tiles (when imported): show "Google" + the data providers listed in the Blosm
  panel on any render you publish.
  Heights: WGS84 ellipsoid (lidar NAVD88 shifted by {meta["geoid_n"]} m, approximate).
"""


def main():
    args = parse_args()
    blosm_ok = False
    if args.blosm:
        blosm_ok = enable_blosm(args.blosm)
        print("Blosm add-on enabled:", blosm_ok)
    for key in args.sites:
        build_site(sites.site_by_key(key), args.work, args.out, blosm_ok, args.previews)


if __name__ == "__main__":
    main()
    if bpy.app.background:
        # the bpy module can hang in its exit handlers; everything is saved by now
        sys.stdout.flush()
        os._exit(0)
