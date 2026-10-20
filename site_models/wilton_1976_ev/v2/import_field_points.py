"""Import field-tagged points (poles, transformers, pad-mounts, meters, panels, control points,
bridge landings...) from a CSV into Wilton1976_Downtown_v2.blend, standing on the lidar terrain.

CSV columns (header row required; see field_points_template.csv):
  id, type, tag, lat, lon, easting, northing, source, accuracy_ft, notes
Give either lat/lon (decimal degrees, phone / CompanyCam GPS) or easting/northing (UTM 19N metres).
Phone GPS is typically +-10-15 ft: after import, drag each marker onto the feature you can see
in the lidar model (pole base, pad corner) and note that in the object's "position" property.

Blender: Scripting tab -> set CSV_PATH -> Run Script.
"""

import csv
import math

import bpy

CSV_PATH = "/Users/YOU/Documents/Wilton1976/field_points.csv"
COLLECTION = "09 Utilities - tag on site (import_field_points.py)"
E0, N0 = 276000.0, 4747000.0
_F, _A = 1 / 298.257222101, 6378137.0
COLORS = {
    "pole": (0.55, 0.35, 0.15, 1),
    "transformer": (1.0, 0.75, 0.0, 1),
    "padmount": (1.0, 0.55, 0.0, 1),
    "meter": (0.2, 0.8, 1.0, 1),
    "panel": (0.2, 0.5, 1.0, 1),
    "control": (1.0, 0.0, 1.0, 1),
    "other": (0.9, 0.9, 0.9, 1),
}


def utm19(lat, lon):
    n = _F / (2 - _F)
    a = _A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    al = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    ]
    e = math.sqrt(_F * (2 - _F))
    phi, lam = math.radians(lat), math.radians(lon + 69.0)
    t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
    xp, ep = (
        math.atan2(t, math.cos(lam)),
        math.atanh(math.sin(lam) / math.sqrt(1 + t * t)),
    )
    xi, eta = xp, ep
    for j, c in enumerate(al, 1):
        xi += c * math.sin(2 * j * xp) * math.cosh(2 * j * ep)
        eta += c * math.cos(2 * j * xp) * math.sinh(2 * j * ep)
    return 500000.0 + 0.9996 * a * eta, 0.9996 * a * xi


def main():
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    scene = bpy.context.scene
    col = bpy.data.collections.get(COLLECTION) or bpy.data.collections.new(COLLECTION)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    terrain = next(o for o in scene.objects if o.name.startswith("Terrain detail"))
    tree = BVHTree.FromObject(terrain, bpy.context.evaluated_depsgraph_get())

    def ground(x, y):
        loc, *_ = tree.ray_cast(Vector((x, y, 3000.0)), Vector((0, 0, -1)))
        return loc.z if loc is not None else 100.0

    n = 0
    for row in csv.DictReader(open(CSV_PATH, newline="", encoding="utf-8-sig")):
        if row.get("lat") and row.get("lon"):
            e, nn = utm19(float(row["lat"]), float(row["lon"]))
        elif row.get("easting") and row.get("northing"):
            e, nn = float(row["easting"]), float(row["northing"])
        else:
            continue
        x, y = e - E0, nn - N0
        z = ground(x, y)
        kind = (row.get("type") or "other").strip().lower()
        h = {
            "pole": 10.0,
            "transformer": 1.5,
            "padmount": 1.4,
            "meter": 1.6,
            "panel": 1.8,
        }.get(kind, 1.0)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.25 if kind == "pole" else 0.5, depth=h, location=(x, y, z + h / 2)
        )
        ob = bpy.context.active_object
        ob.name = f"{kind.upper()} {row.get('id', '')} {row.get('tag', '')}".strip()
        for c in ob.users_collection:
            c.objects.unlink(ob)
        col.objects.link(ob)
        m = bpy.data.materials.get(f"Field {kind}") or bpy.data.materials.new(
            f"Field {kind}"
        )
        m.diffuse_color = COLORS.get(kind, COLORS["other"])
        ob.data.materials.append(m)
        for k in ("id", "type", "tag", "source", "accuracy_ft", "notes"):
            ob[k] = row.get(k, "")
        ob["position"] = (
            "from CSV coordinates (move onto the feature in the lidar model and say so here)"
        )
        cu = bpy.data.curves.new(ob.name + " label", "FONT")
        cu.body = f"{kind.upper()} {row.get('tag', '')}"
        cu.size = 0.8
        cu.align_x = "CENTER"
        lab = bpy.data.objects.new(ob.name + " label", cu)
        lab.location = (x, y, z + h + 1.2)
        lab.rotation_euler = (math.radians(90), 0, 0)
        col.objects.link(lab)
        n += 1
    print(f"import_field_points: {n} points from {CSV_PATH}")


main()
