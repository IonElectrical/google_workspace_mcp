"""Optional batch import of Google Photorealistic 3D Tiles into the site .blend files.

Does the same thing as clicking "import" in the Blosm panel of each file, for all three
sites in one go, then snaps the tiles onto the lidar terrain and saves a copy named
<site>_google.blend next to the original.

The API key is never written to disk by this script: it is read from the macOS Keychain
(service "google-map-tiles") or, failing that, from the GOOGLE_MAPS_API_KEY environment
variable, handed to Blosm's preferences for this run only (preferences are not saved),
and scrubbed from anything printed. The saved file is scanned for the key before it is kept.

Store the key once (Terminal prompts for it, nothing is echoed or kept in shell history):
    security add-generic-password -a "$USER" -s google-map-tiles -w
Run (Blender 4.5 LTS with Blosm installed and enabled):
    /Applications/Blender.app/Contents/MacOS/Blender -b -P import_google_tiles.py -- \
        --blends ~/Wilton1976/*.blend [--lod lod5]
"""

import argparse
import glob
import os
import subprocess
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))


def get_key():
    try:
        key = subprocess.run(
            ["security", "find-generic-password", "-s", "google-map-tiles", "-w"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if key:
            return key
    except (OSError, subprocess.CalledProcessError):
        pass
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        sys.exit(
            "No key: add it to the Keychain (service google-map-tiles) or set GOOGLE_MAPS_API_KEY."
        )
    return key


class Scrub:
    """stdout/stderr wrapper that masks the key (Blosm prints failing URLs, which contain it)."""

    def __init__(self, stream, secret):
        self.stream, self.secret = stream, secret

    def write(self, s):
        return self.stream.write(s.replace(self.secret, "***"))

    def flush(self):
        self.stream.flush()


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blends", nargs="+", required=True)
    ap.add_argument("--lod", default="lod5", choices=["lod3", "lod4", "lod5"])
    args = ap.parse_args(argv)
    paths = [
        p
        for pattern in args.blends
        for p in glob.glob(os.path.expanduser(pattern))
        if not p.endswith("_google.blend")
    ]

    key = get_key()
    sys.stdout, sys.stderr = Scrub(sys.stdout, key), Scrub(sys.stderr, key)
    bpy.context.preferences.use_preferences_save = False
    bpy.context.preferences.filepaths.save_version = (
        0  # no .blend1 backups of the scan copy
    )
    if "blosm" not in bpy.context.preferences.addons:
        import addon_utils

        addon_utils.enable("blosm", default_set=True)

    for path in paths:
        bpy.ops.wm.open_mainfile(filepath=path)
        prefs = bpy.context.preferences.addons["blosm"].preferences
        prefs.googleMapsApiKey = key
        if not prefs.dataDir:
            prefs.dataDir = os.path.join(os.path.dirname(path), "blosm_data")
            os.makedirs(prefs.dataDir, exist_ok=True)
        b = bpy.context.scene.blosm
        b.dataType, b.threedTilesSource, b.lodOf3dTiles = "3d-tiles", "google", args.lod
        b.relativeToInitialImport = True
        print(f"{os.path.basename(path)}: importing Google 3D Tiles ({args.lod}) ...")
        try:
            result = bpy.ops.blosm.import_data()
        except RuntimeError as e:  # in background mode operator errors are raised
            result = {"CANCELLED"}
            print(" ", e)
        finally:
            prefs.googleMapsApiKey = ""
        if "FINISHED" not in result:
            print("  import failed - nothing saved for this file")
            continue
        align = bpy.data.texts.get("align_google_tiles.py")
        exec(
            compile(
                align.as_string()
                if align
                else open(os.path.join(HERE, "align_google_tiles.py")).read(),
                "align_google_tiles.py",
                "exec",
            ),
            {"__name__": "__main__"},
        )
        print("  attribution:", bpy.context.scene.blosm.copyright)

        out = path[:-6] + "_google.blend"
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=False, copy=True)
        with open(out, "rb") as f:
            leaked = key.encode() in f.read()
        if leaked:
            os.remove(out)
            sys.exit(f"  key found inside {out} - file deleted, nothing kept")
        bpy.ops.wm.open_mainfile(filepath=out)
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print(f"  saved {out}")


if bpy.app.background:
    main()
    sys.stdout.flush()
    os._exit(0)
else:
    print("Run this script with Blender in background mode (-b), see the docstring.")
