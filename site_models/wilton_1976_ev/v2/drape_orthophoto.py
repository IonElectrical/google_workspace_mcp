"""Drape orthophoto tiles (e.g. GRANIT 2021/22 6-inch leaf-off, NH State Plane US ft) on the lidar
terrain of Wilton1976_Downtown_v2.blend. Each tile needs its world file (.tfw/.jgw/.j2w/.pgw/.wld)
next to it. Several tiles are fine: each terrain face gets the tile that covers it.

Blender: Scripting tab -> open this text -> set FOLDER and CRS -> Run Script. Then View > Solid
shading "Texture" or Material Preview shows the photo.
"""

import glob
import math
import os

import bpy
import numpy as np

# ------------------------------------------------------------------ SETTINGS
FOLDER = "/Users/YOU/Downloads/granit_ortho_wilton"  # images + world files
CRS = "NH_SP_FT"  # "NH_SP_FT" (EPSG:3437/3445, GRANIT) or "UTM19N_M" (EPSG:26919/6348)
# ---------------------------------------------------------------------------

E0, N0 = 276000.0, 4747000.0
_F = 1 / 298.257222101
_A = 6378137.0
US_FT = 1200.0 / 3937.0
WORLD_EXT = {
    ".tif": ".tfw",
    ".tiff": ".tfw",
    ".jpg": ".jgw",
    ".jpeg": ".jgw",
    ".jp2": ".j2w",
    ".png": ".pgw",
}


def _coeffs():
    n = _F / (2 - _F)
    a = _A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    al = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    ]
    be = [n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96, n**2 / 48 + n**3 / 15, 17 * n**3 / 480]
    de = [2 * n - 2 * n**2 / 3 - 2 * n**3, 7 * n**2 / 3 - 8 * n**3 / 5, 56 * n**3 / 15]
    return a, al, be, de


def tm_fwd(lat, lon, lon0, k0, fe, fn=0.0, lat0=0.0):
    a, al, _, _ = _coeffs()
    e = math.sqrt(_F * (2 - _F))
    phi, lam = np.radians(lat), np.radians(np.asarray(lon) - lon0)
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xp, ep = np.arctan2(t, np.cos(lam)), np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    xi, eta = xp.copy(), ep.copy()
    for j, c in enumerate(al, 1):
        xi = xi + c * np.sin(2 * j * xp) * np.cosh(2 * j * ep)
        eta = eta + c * np.cos(2 * j * xp) * np.sinh(2 * j * ep)
    m0 = tm_fwd(lat0, lon0, lon0, k0, 0.0)[1] if lat0 else 0.0
    return fe + k0 * a * eta, fn + k0 * a * xi - m0


def tm_inv(x, y, lon0, k0, fe, fn=0.0, lat0=0.0):
    a, _, be, de = _coeffs()
    m0 = tm_fwd(lat0, lon0, lon0, k0, 0.0)[1] if lat0 else 0.0
    xi, eta = (np.asarray(y) - fn + m0) / (k0 * a), (np.asarray(x) - fe) / (k0 * a)
    xp, ep = xi.copy(), eta.copy()
    for j, c in enumerate(be, 1):
        xp = xp - c * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        ep = ep - c * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    chi = np.arcsin(np.sin(xp) / np.cosh(ep))
    phi = chi.copy()
    for j, c in enumerate(de, 1):
        phi = phi + c * np.sin(2 * j * chi)
    return np.degrees(phi), lon0 + np.degrees(np.arctan2(np.sinh(ep), np.cos(xp)))


def scene_to_image_crs(x, y):
    e, n = np.asarray(x) + E0, np.asarray(y) + N0
    if CRS == "UTM19N_M":
        return e, n
    lat, lon = tm_inv(e, n, -69.0, 0.9996, 500000.0)
    sx, sy = tm_fwd(lat, lon, -71.66666666666667, 0.999966667, 300000.0, 0.0, 42.5)
    return np.asarray(sx) / US_FT, np.asarray(sy) / US_FT


def main():
    terrain = next(
        o for o in bpy.context.scene.objects if o.name.startswith("Terrain detail")
    )
    me = terrain.data
    tiles = []
    for img_path in sorted(glob.glob(os.path.join(FOLDER, "*"))):
        ext = os.path.splitext(img_path)[1].lower()
        if ext not in WORLD_EXT:
            continue
        wf = [
            os.path.splitext(img_path)[0] + e
            for e in (WORLD_EXT[ext], ".wld", WORLD_EXT[ext].upper())
        ]
        wf = next((w for w in wf if os.path.exists(w)), None)
        if not wf:
            print("no world file for", img_path)
            continue
        A, D, B, E, C, F = [float(v) for v in open(wf).read().split()[:6]]
        img = bpy.data.images.load(img_path, check_existing=True)
        w, h = img.size
        tiles.append({"img": img, "aff": (A, B, C, D, E, F), "w": w, "h": h})
    if not tiles:
        raise RuntimeError("No image + world file pairs found in " + FOLDER)
    # face centres -> tile index
    nf = len(me.polygons)
    cen = np.empty(nf * 3, dtype=np.float64)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    fx, fy = scene_to_image_crs(cen[:, 0], cen[:, 1])
    tile_of = np.full(nf, -1, dtype=np.int32)
    for i, t in enumerate(tiles):
        A, B, C, D, E, F = t["aff"]
        det_ = A * E - B * D
        col = (E * (fx - C) - B * (fy - F)) / det_
        row = (-D * (fx - C) + A * (fy - F)) / det_
        inside = (
            (col >= 0) & (col < t["w"]) & (row >= 0) & (row < t["h"]) & (tile_of < 0)
        )
        tile_of[inside] = i
    # materials: keep the existing ground material for faces no tile covers
    base_n = len(me.materials)
    for i, t in enumerate(tiles):
        m = bpy.data.materials.new(f"Orthophoto {os.path.basename(t['img'].filepath)}")
        m.use_nodes = True
        tex = m.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = t["img"]
        uvn = m.node_tree.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "OrthoUV"
        m.node_tree.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
        m.node_tree.links.new(
            tex.outputs["Color"],
            m.node_tree.nodes["Principled BSDF"].inputs["Base Color"],
        )
        me.materials.append(m)
    mi = np.zeros(nf, dtype=np.int32)
    me.polygons.foreach_get("material_index", mi)
    mi = np.where(tile_of >= 0, base_n + tile_of, mi)
    me.polygons.foreach_set("material_index", mi)
    # per-loop UVs from each face's tile
    uv = me.uv_layers.get("OrthoUV") or me.uv_layers.new(name="OrthoUV")
    nl = len(me.loops)
    vi = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ls = np.empty(nf, dtype=np.int32)
    lt = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    face_of_loop = np.repeat(np.arange(nf), lt)
    lx, ly = scene_to_image_crs(co[vi, 0], co[vi, 1])
    u = np.zeros(nl)
    v = np.zeros(nl)
    for i, t in enumerate(tiles):
        sel = tile_of[face_of_loop] == i
        A, B, C, D, E, F = t["aff"]
        det_ = A * E - B * D
        col = (E * (lx[sel] - C) - B * (ly[sel] - F)) / det_ + 0.5
        row = (-D * (lx[sel] - C) + A * (ly[sel] - F)) / det_ + 0.5
        u[sel], v[sel] = col / t["w"], 1.0 - row / t["h"]
    uv.data.foreach_set("uv", np.column_stack([u, v]).astype(np.float32).ravel())
    covered = int((tile_of >= 0).sum())
    bpy.context.scene["orthophoto"] = (
        f"{len(tiles)} tiles from {FOLDER} ({CRS}); {covered}/{nf} terrain faces covered"
    )
    print("drape_orthophoto:", bpy.context.scene["orthophoto"])


main()
