"""End-to-end check that a Blosm 3D Tiles import lands on the open-data layers.

Serves a tiny synthetic 3D Tiles set on localhost (one marker per site pin, placed at the
pin's WGS84 position via an ECEF node translation, like Google's tiles), imports it into a
site .blend through Blosm's own "custom 3D Tiles" path, and compares where the markers
land with the pins built by build_site_blend.py. Then it checks align_google_tiles.py on a
copy of the terrain raised by a known amount.

    python verify_alignment.py SITE.blend WORK_DIR BLOSM_PARENT_DIR
(run with the bpy wheel, Blender 4.5; no network access or API key needed)
"""

import functools
import http.server
import json
import math
import os
import struct
import sys
import tempfile
import threading

import bpy  # must come first with the bpy wheel
import addon_utils
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sites  # noqa: E402


def write_glb(path, points_ecef):
    # octahedron of radius 1 m around each node origin; glTF is y-up: (X, Y, Z)_ecef -> (X, Z, -Y)
    v = np.array(
        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
        np.float32,
    )
    idx = np.array(
        [0, 2, 4, 2, 1, 4, 1, 3, 4, 3, 0, 4, 2, 0, 5, 1, 2, 5, 3, 1, 5, 0, 3, 5],
        np.uint16,
    )
    binary = v.tobytes() + idx.tobytes()
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(points_ecef)))}],
        "nodes": [
            {"mesh": 0, "translation": [float(p[0]), float(p[2]), float(-p[1])]}
            for p in points_ecef
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 6,
                "type": "VEC3",
                "min": [-1, -1, -1],
                "max": [1, 1, 1],
            },
            {
                "bufferView": 1,
                "componentType": 5123,
                "count": len(idx),
                "type": "SCALAR",
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": v.nbytes, "target": 34962},
            {
                "buffer": 0,
                "byteOffset": v.nbytes,
                "byteLength": idx.nbytes,
                "target": 34963,
            },
        ],
        "buffers": [{"byteLength": len(binary)}],
    }
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def main():
    blend, work, blosm_parent = sys.argv[1:4]
    sys.path.insert(0, blosm_parent)
    bpy.context.preferences.use_preferences_save = False
    addon_utils.enable("blosm", default_set=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    scene = bpy.context.scene
    site = next(s for s in sites.SITES if sites.blend_name(s) == scene.name)
    meta = json.load(open(os.path.join(work, site["key"], "meta.json")))
    frame = sites.BlosmFrame(scene["lat"], scene["lon"])

    pins = np.array([p["xyz"] for p in meta["pins"]])
    lat, lon, h = frame.to_geodetic(pins)
    ecef = sites.ecef(lat, lon, h)

    tmp = tempfile.mkdtemp()
    write_glb(os.path.join(tmp, "markers.glb"), ecef)
    pad = math.radians(0.01)
    region = [
        math.radians(lon.min()) - pad,
        math.radians(lat.min()) - pad,
        math.radians(lon.max()) + pad,
        math.radians(lat.max()) + pad,
        0.0,
        300.0,
    ]
    json.dump(
        {
            "asset": {"version": "1.0"},
            "geometricError": 100,
            "root": {
                "boundingVolume": {"region": region},
                "geometricError": 0,
                "refine": "REPLACE",
                "content": {"uri": "markers.glb"},
            },
        },
        open(os.path.join(tmp, "tileset.json"), "w"),
    )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    b = scene.blosm
    b.threedTilesSource = "custom"
    b.threedTilesUrl = f"http://127.0.0.1:{server.server_address[1]}/tileset.json"
    b.geometricError = 30.0
    bpy.context.preferences.addons["blosm"].preferences.dataDir = tmp
    print("blosm import:", bpy.ops.blosm.import_data())

    from threed_tiles.manager import BaseManager

    c_blosm = BaseManager.fromGeographic(scene["lat"], scene["lon"], 0.0)
    print(
        "float32 origin replica == Blosm's:",
        list(c_blosm) == list(scene["blosm_center_ecef_f32"]),
    )

    obj = next(
        o
        for c in bpy.data.collections
        if c.name.startswith("3D Tiles")
        for o in c.objects
    )
    co = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
    centres = co.reshape(-1, 6, 3).mean(1)
    worst = 0.0
    for s, c in zip(sites.SITES, centres):
        head = bpy.data.objects[f"PIN head {s['key']}"].matrix_world.translation
        p = np.array(head) - (
            0.0,
            0.0,
            16.0,
        )  # the pin head sits PIN_H = 16 m above the ground point
        err = np.linalg.norm(c - p)
        worst = max(worst, err)
        print(
            f"  {s['key']:20s} pin {np.round(p, 2)}  imported marker {np.round(c, 2)}  error {err * 100:.2f} cm"
        )
    print(
        f"MAX MARKER ERROR: {worst * 100:.2f} cm (scene lat/lon unchanged: {scene['lat']}, {scene['lon']})"
    )

    # align_google_tiles.py on a fake 'Google' mesh = terrain raised 0.8 m
    terrain = bpy.data.objects["Terrain (USGS lidar 2019)"]
    fake = terrain.copy()
    fake.data = terrain.data.copy()
    fake.location.z += 0.8
    gcol = bpy.data.collections.new("Google 3D Tiles")
    scene.collection.children.link(gcol)
    gcol.objects.link(fake)
    ns = {"__name__": "__main__"}
    exec(bpy.data.texts["align_google_tiles.py"].as_string(), ns)
    print(
        f"ALIGN SCRIPT: fake offset +0.80 m -> remaining {fake.location.z - terrain.location.z:+.3f} m"
    )
    server.shutdown()


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
