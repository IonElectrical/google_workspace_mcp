"""Snap an imported Google 3D Tiles mesh vertically onto this file's lidar terrain.

Run it from Blender's Scripting tab (Text editor > Run Script) right after the Blosm
Google 3D Tiles import. Blosm already places the tiles at the right X/Y; the open-data
terrain carries an approximate NAVD88 -> ellipsoid shift, so this removes the leftover
vertical offset (usually under 1 m). It casts rays straight down on a grid around the
site, onto the Google mesh and onto the lidar terrain, and moves the Google object(s)
by the most common ground difference (roofs and trees are ignored by using the mode).
"""

import math

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

TERRAIN = "Terrain (USGS lidar 2019)"
SPACING = 4.0
REACH = 120.0


def horizontal_fix(scene):
    """The model was built to match Blosm's float32 scene origin as computed at build time.
    Recompute it with the Blosm installed here; if it differs, return the correction."""
    stored = scene.get("blosm_center_ecef_f32")
    try:
        from threed_tiles.manager import BaseManager
    except ImportError:
        return Vector((0.0, 0.0, 0.0))
    if stored is None:
        return Vector((0.0, 0.0, 0.0))
    now = BaseManager.fromGeographic(scene["lat"], scene["lon"], 0.0)
    lat = math.atan(now[2] / math.sqrt(now[0] ** 2 + now[1] ** 2))
    q = Matrix.Rotation(lat - math.pi / 2, 3, "X") @ Matrix.Rotation(
        math.radians(-90.0 - scene["lon"]), 3, "Z"
    )
    return q @ Vector([n - s for n, s in zip(now, stored)])


def first_hit(tree, obj, x, y):
    inv = obj.matrix_world.inverted()
    origin = inv @ Vector((x, y, 3000.0))
    direction = (inv.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    loc, _normal, _index, _dist = tree.ray_cast(origin, direction)
    return None if loc is None else (obj.matrix_world @ loc).z


def main():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    google = [
        o
        for c in bpy.data.collections
        if c.name.startswith("Google 3D Tiles")
        for o in c.all_objects
        if o.type == "MESH"
    ]
    terrain = bpy.data.objects.get(TERRAIN)
    if not google or terrain is None:
        print(
            "align_google_tiles: import Google 3D Tiles with Blosm first (and keep the Terrain object)."
        )
        return None
    fix = horizontal_fix(bpy.context.scene)
    if fix.length > 1e-4:
        for o in google:
            o.location += fix
        depsgraph.update()
        print(
            f"align_google_tiles: origin correction {tuple(round(v, 3) for v in fix)} m"
        )
    t_tree = BVHTree.FromObject(terrain, depsgraph)
    g_trees = [(o, BVHTree.FromObject(o, depsgraph)) for o in google]
    aim = bpy.data.objects.get("AIM - camera target (move me)")
    cx, cy = (aim.location.x, aim.location.y) if aim else (0.0, 0.0)

    diffs = []
    steps = int(REACH / SPACING)
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            x, y = cx + i * SPACING, cy + j * SPACING
            zt = first_hit(t_tree, terrain, x, y)
            if zt is None:
                continue
            zg = [
                z for z in (first_hit(t, o, x, y) for o, t in g_trees) if z is not None
            ]
            if zg:
                diffs.append(max(zg) - zt)
    if len(diffs) < 50:
        print("align_google_tiles: too few overlapping samples", len(diffs))
        return None

    # mode of the differences in 0.2 m bins, refined by the median around it
    bins = {}
    for d in diffs:
        if -20.0 < d < 20.0:
            bins.setdefault(round(d / 0.2), []).append(d)
    peak = max(bins.values(), key=len)
    centre = sorted(peak)[len(peak) // 2]
    near = sorted(d for d in diffs if abs(d - centre) < 0.5)
    shift = near[len(near) // 2]
    for o in google:
        o.location.z -= shift
    bpy.context.scene["google_tiles_z_shift_m"] = round(shift, 3)
    msg = f"Google 3D Tiles moved {(-shift):+.2f} m vertically ({len(near)} ground samples of {len(diffs)})."
    print("align_google_tiles:", msg)

    def draw(self, _context):
        self.layout.label(text=msg)

    if not bpy.app.background:
        bpy.context.window_manager.popup_menu(
            draw, title="Google tiles aligned", icon="INFO"
        )
    return shift


main()
