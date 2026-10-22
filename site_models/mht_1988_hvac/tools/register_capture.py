"""Scale and register a Polycam (or any phone) capture to the lidar model with control points,
and report the residual error.

1. Import the capture (File > Import > glTF/OBJ/PLY) and select it.
2. For each control point (curb corner, pole base, building corner at ground...) add TWO empties:
     CP1_scan  - snapped onto the feature on the capture
     CP1_model - snapped onto the same feature on the lidar terrain/buildings
   (Shift+A > Empty > Plain Axes; snap with the magnet set to Vertex / Face). At least 3, ideally
   4+ spread around the scan.
3. With the capture selected, run this script (Scripting tab > Run Script).

The capture (and its children) gets the best-fit similarity transform (rotation, uniform scale,
translation; Umeyama / Horn least squares). Residuals per point and RMS are printed, shown in a
popup and stored on the object ("registration_rms_ft"). A scale far from 1.0 means the capture
was not metric or a point pair is wrong.
"""

import re

import bpy
import numpy as np
from mathutils import Matrix


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    s0, d0 = src - mu_s, dst - mu_d
    cov = d0.T @ s0 / len(src)
    u, sig, vt = np.linalg.svd(cov)
    d = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        d[2, 2] = -1
    r = u @ d @ vt
    var_s = (s0**2).sum() / len(src)
    if var_s < 1e-9:
        raise RuntimeError(
            "The CPn_scan points all coincide - place them on distinct features"
        )
    scale = np.trace(np.diag(sig) @ d) / var_s
    t = mu_d - scale * r @ mu_s
    return scale, r, t


def main():
    target = bpy.context.active_object
    if target is None:
        raise RuntimeError("Select the imported capture first")
    bpy.context.view_layer.update()  # make sure every empty's world position is current
    pairs = {}
    for ob in bpy.data.objects:
        m = re.match(r"^(CP\w*?)_(scan|model)$", ob.name, re.IGNORECASE)
        if m:
            pairs.setdefault(m.group(1).upper(), {})[m.group(2).lower()] = np.array(
                ob.matrix_world.translation
            )
    ids = sorted(k for k, v in pairs.items() if "scan" in v and "model" in v)
    if len(ids) < 3:
        raise RuntimeError(
            f"Need >= 3 complete pairs CPn_scan / CPn_model, found {ids}"
        )
    src = np.array([pairs[k]["scan"] for k in ids])
    dst = np.array([pairs[k]["model"] for k in ids])
    s, r, t = umeyama(src, dst)
    m = np.eye(4)
    m[:3, :3] = s * r
    m[:3, 3] = t
    M = Matrix(m.tolist())
    target.matrix_world = M @ target.matrix_world
    for k in ids:  # move the scan-side empties with the capture so they can be checked
        e = bpy.data.objects[f"{k}_scan"] if f"{k}_scan" in bpy.data.objects else None
        if e:
            e.matrix_world = M @ e.matrix_world
    res = np.linalg.norm((s * (r @ src.T)).T + t - dst, axis=1)
    rms = float(np.sqrt(np.mean(res**2)))
    lines = [f"{k}: {v / 0.3048:.2f} ft" for k, v in zip(ids, res)]
    target["registration_scale"] = float(s)
    target["registration_rms_ft"] = round(rms / 0.3048, 3)
    target["registration_points"] = ", ".join(lines)
    msg = f"scale {s:.4f}, RMS {rms / 0.3048:.2f} ft over {len(ids)} points"
    print("register_capture:", msg, "|", "; ".join(lines))

    def draw(self, _ctx):
        self.layout.label(text=msg)
        for ln in lines:
            self.layout.label(text=ln)

    if not bpy.app.background:
        bpy.context.window_manager.popup_menu(
            draw, title="Capture registered", icon="INFO"
        )
    return s, rms, res


main()
