"""MHT #1988: turn analysis.json into the viewer's site content (generic feature format read by
export_web.py), plus ROUTE_LENGTHS.md. Job-specific; the exporter itself is generic.

    python hvac_viewer.py --work WORK --docs ../

Feature format (all coordinates model metres, z NAVD88):
  box    {c:[x,y,z_base], w, d, h, rot (deg, long side along x), mat, info}
  poly   {p:[x,y,z,...] or xy + drape:true, mat, info}
  tube   {p:[x,y,z,...], r, mat, info}
  line   {p:[x,y,z,...], color}
  marker {at:[x,y,z], mat, size, h, info}
  any feature may carry label + la:[x,y,z] (+ lk label kind, lmax distance)
"""

import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frame  # noqa: E402

FT = 0.3048


def f1(v, d=1):
    return f"{v:,.{d}f}" if v is not None else "n/a"


def flat(a):
    """Nested points -> flat list; None (z from the ground, filled by the exporter) is kept."""
    out = []
    for v in np.asarray(a, dtype=object).ravel():
        out.append(None if v is None else round(float(v), 3))
    return out


def info(title, rows, note, tag):
    return {
        "title": title,
        "rows": [[r[0], r[1]] for r in rows],
        "note": note,
        "tag": tag,
    }


def unit_box(u, mat="unit", tag="e"):
    r = np.asarray(u["rect"])
    c = r.mean(0)
    e1, e2 = r[1] - r[0], r[2] - r[1]
    long_e = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2
    rot = math.degrees(math.atan2(long_e[1], long_e[0]))
    L, W, H = (v * FT for v in u["size_ft"])
    rows = [
        [
            "Size L × W × H (lidar)",
            f"{u['size_ft'][0]} × {u['size_ft'][1]} × {u['size_ft'][2]} ft",
        ],
        [
            "Roof surface",
            f"{f1(u['roof_navd88_ft'])} ft NAVD88 · {f1(u['roof_above_grade_ft'])} ft above grade",
        ],
        ["Top of unit above grade", f"{f1(u['top_above_grade_ft'])} ft"],
        [
            "Nearest roof drop edge",
            f"{f1(u['edge_drop_ft'])} ft"
            if u["edge_drop_ft"] is not None
            else "none within 197 ft",
        ],
        [
            "Nearest wall / higher roof",
            f"{f1(u['wall_ft'])} ft"
            if u["wall_ft"] is not None
            else "none within 197 ft",
        ],
        ["Lat, lon (NAD83)", f"{u['lat']}, {u['lon']}"],
    ]
    if u.get("tons"):
        rows.insert(0, ["Bid package", f"{u['tons']} tons"])
    return {
        "t": "box",
        "c": [round(float(c[0]), 3), round(float(c[1]), 3), u["roof_z_m"]],
        "w": round(L, 3),
        "d": round(W, 3),
        "h": round(H, 3),
        "rot": round(-rot, 2),  # three.js y-rotation is clockwise seen from above
        "mat": mat,
        "info": info(
            u["tag"], rows, u["confidence"] + ". " + (u.get("note") or ""), tag
        ),
        "label": f"{u['tag'].replace('Bridge unit ', '')} · lidar candidate",
        "la": [round(float(c[0]), 2), round(float(c[1]), 2), u["roof_z_m"] + H + 2.5],
        "lk": "est",
        "lmax": 450,
    }


def edge_lines(u):
    out = []
    c = np.asarray(u["rect"]).mean(0)
    z = u["roof_z_m"] + 0.3
    for key, xy, col, txt in (
        ("edge_drop_ft", u["edge_drop_xy"], 0xFFFFFF, "to roof edge"),
        ("wall_ft", u["wall_xy"], 0x9AD2FF, "to wall"),
    ):
        if xy is None or u[key] is None or u[key] > 150:
            continue
        out.append(
            {
                "t": "line",
                "p": flat([[c[0], c[1], z], [xy[0], xy[1], z]]),
                "color": col,
                "label": f"{f1(u[key])} ft {txt}",
                "la": [(c[0] + xy[0]) / 2, (c[1] + xy[1]) / 2, z + 0.8],
                "lk": "trench",
                "lmax": 220,
            }
        )
    return out


def riser(u, floor_z, label):
    c = np.asarray(u["rect"]).mean(0)
    return {
        "t": "tube",
        "p": flat([[c[0], c[1], floor_z], [c[0], c[1], u["roof_z_m"]]]),
        "r": 0.12,
        "mat": "riser",
        "info": info(
            f"{u['tag']} riser (x-ray, position not known)",
            [["Roof to floor", label]],
            "Drawn under the unit centre only to show the height. The real riser and roof "
            "penetration are not located; ground-floor slab taken at grade.",
            "e",
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--docs", default=os.path.join(HERE, ".."))
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    C = frame.load_config(a.config)
    A = json.load(open(os.path.join(a.work, "analysis.json")))
    meta = json.load(open(os.path.join(a.work, "meta.json")))
    grade = A["grade_m"]
    U = {u["tag"]: u for u in A["units"]}
    ahu, r5 = U["AHU-5"], U["RTU-5"]
    bunits = [u for u in A["units"] if u["tag"].startswith("Bridge unit")]
    R = {r["unit"]: r for r in A["routes"]}
    br = A["bridge"]
    cr, c5 = A["crane_ahu5"], A["crane_rtu5"]

    def ctr(u):
        return np.asarray(u["rect"]).mean(0)

    def cams(center_xy, z, bearing=200, dist=70, up=45, eye_d=28):
        b = math.radians(bearing)
        cx, cy = center_xy
        return {
            "center": [round(cx, 2), round(cy, 2), round(z, 2)],
            "aerial": [
                round(cx + dist * math.sin(b), 2),
                round(cy + dist * math.cos(b), 2),
                round(z + up, 2),
            ],
            "eye": [
                round(cx + eye_d * math.sin(b), 2),
                round(cy + eye_d * math.cos(b), 2),
                None,
            ],
        }

    sites = []
    # ---- AHU-5
    feats = [unit_box(ahu)] + edge_lines(ahu)
    feats.append(riser(ahu, grade, f"{f1(R['AHU-5']['riser_ft'])} ft (calc. estimate)"))
    for k, al in enumerate(A["ahu5_alternates"], start=1):
        b = unit_box(al, "unitAlt", "e")
        b["info"]["title"] = f"AHU-5 alternate candidate {k}"
        b["label"] = f"alt {k}"
        b["lk"] = "note"
        b["lmax"] = 250
        feats.append(b)
    if cr:
        feats.append(
            {
                "t": "line",
                "p": flat(
                    [
                        [*cr["pad_xy"], cr["ramp_z_m"] + 1.0],
                        [*ctr(ahu), ahu["roof_z_m"] + ahu["size_ft"][2] * FT],
                    ]
                ),
                "color": 0xFF9D1A,
                "label": f"pick radius {f1(cr['pick_radius_center_ft'])} ft to unit centre",
                "la": [
                    (cr["pad_xy"][0] + ctr(ahu)[0]) / 2,
                    (cr["pad_xy"][1] + ctr(ahu)[1]) / 2,
                    ahu["roof_z_m"] + 6,
                ],
                "lk": "trench",
                "lmax": 400,
            }
        )
    sites.append(
        {
            "key": "ahu5",
            "title": "AHU-5 · low (valley) roof",
            "button": "AHU-5",
            "addr": "Terminal low (valley) roof, 1998 expansion (per bid package)",
            "rationale": "184-ton custom packaged DX unit, about 57,900 lb, replaced in Phase 3. Light gray TPO roof (1998). "
            "Feeder (2)[3-250 kcmil + 1#2 GND in 3in], 500A, from SWBD E in room #1077.",
            "alerts": [
                "Unit position is a LIDAR CANDIDATE: the largest packaged-unit-shaped object on the low roof. "
                "Three alternates on the same roof level are drawn in grey. Confirm the tag on site."
            ],
            "facts": [
                [
                    "Low roof surface",
                    f"{f1(ahu['roof_navd88_ft'])} ft NAVD88",
                    "m",
                    "lidar",
                ],
                [
                    "Low roof above grade",
                    f"{f1(ahu['roof_above_grade_ft'])} ft",
                    "m",
                    "lidar + DEM",
                ],
                [
                    "Candidate size L × W × H",
                    f"{ahu['size_ft'][0]} × {ahu['size_ft'][1]} × {ahu['size_ft'][2]} ft",
                    "m",
                    "lidar",
                ],
                [
                    "Nearest roof drop edge",
                    f"{f1(ahu['edge_drop_ft'])} ft",
                    "m",
                    "lidar",
                ],
                [
                    "Nearest wall / higher roof",
                    f"{f1(ahu['wall_ft'])} ft",
                    "m",
                    "lidar",
                ],
                [
                    "Riser, roof to ground-floor slab",
                    f"{f1(R['AHU-5']['riser_ft'])} ft",
                    "e",
                ],
                [
                    "Horizontal run, room #1077 to riser",
                    "not measurable (interior)",
                    "x",
                ],
                [
                    "Your estimate total",
                    f"{R['AHU-5']['assumed_total_ft']} ft",
                    "e",
                    "assumption",
                ],
                [
                    "Left for horizontal + roof run",
                    f"{f1(R['AHU-5']['left_for_horizontal_and_roof_ft'])} ft",
                    "e",
                ],
                [
                    "Crane pick radius (centre / far corner)",
                    f"{f1(cr['pick_radius_center_ft'])} / {f1(cr['pick_radius_far_corner_ft'])} ft",
                    "e",
                ],
            ],
            "features": feats,
            **cams(ctr(ahu), ahu["roof_z_m"], 200, 75, 50),
        }
    )

    # ---- RTU-1 to RTU-4 (bridge)
    feats = [
        {
            "t": "line",
            "p": flat(
                [
                    [*p, z + 0.4]
                    for p, z in zip(
                        br["axis"], (br["roof_z_range_m"][0], br["roof_z_range_m"][1])
                    )
                ]
            ),
            "color": 0xFFE14D,
            "label": f"Bridge {f1(br['length_ft'], 0)} ft face to face · deck {f1(br['deck_width_ft'], 0)} ft wide · roof rises {f1(br['roof_rise_ft'])} ft to the terminal",
            "la": [*np.mean(br["axis"], axis=0).tolist(), br["roof_z_range_m"][1] + 5],
            "lk": "note",
            "lmax": 500,
        }
    ]
    for u in bunits:
        feats.append(unit_box(u))
        feats += edge_lines(u)
        feats.append(
            riser(
                u,
                grade,
                f"{f1(u['roof_above_grade_ft'])} ft to grade (room floor not known)",
            )
        )
    mid = (
        np.mean([ctr(u) for u in bunits], axis=0)
        if bunits
        else np.mean(br["axis"], axis=0)
    )
    rows = [
        [
            "Bridge length, garage face to terminal face",
            f"{f1(br['length_ft'])} ft",
            "m",
            "lidar + OSM",
        ],
        ["Deck width (roof)", f"{f1(br['deck_width_ft'])} ft", "m", "lidar"],
        [
            "Bridge roof",
            f"{f1(br['roof_z_range_m'][0] / FT)}–{f1(br['roof_z_range_m'][1] / FT)} ft NAVD88",
            "m",
            "lidar",
        ],
        [
            "Bridge roof above Airport Road",
            f"{f1(br['roof_above_road_ft'])} ft",
            "m",
            "lidar + DEM",
        ],
        [
            "Structural arches on the roof",
            f"{br['arches']}, every {f1(br['arch_spacing_ft'])} ft",
            "m",
            "lidar",
        ],
        [
            "Unit-sized objects on the deck roof",
            f"{len(bunits) + 1} (incl. RTU-5)",
            "m",
            "lidar",
        ],
        ["Roof hatch", "not located", "x"],
    ]
    for u in bunits:
        rows.append(
            [
                f"{u['tag']} size",
                f"{u['size_ft'][0]} × {u['size_ft'][1]} × {u['size_ft'][2]} ft",
                "m",
                "lidar",
            ]
        )
        rows.append(
            [
                f"{u['tag']} roof above grade / to edge",
                f"{f1(u['roof_above_grade_ft'])} / {f1(u['edge_drop_ft'])} ft",
                "m",
                "lidar",
            ]
        )
    sites.append(
        {
            "key": "rtu1_4",
            "title": "RTU-1 to RTU-4 · bridge roof",
            "button": "RTU-1 to 4",
            "addr": "Pedestrian bridge roof, terminal to garage",
            "rationale": "6, 20, 20, 20 tons. Black EPDM roof (2000). RTU-1 and RTU-2 from panel M3 in room #105; "
            "RTU-3 and RTU-4 from panel M2 in bridge room #204.",
            "alerts": [
                f"The lidar shows only {len(bunits) + 1} unit-sized objects on the bridge roofs for the 5 RTUs in the bid package "
                "(RTU-1 to RTU-5). Tags cannot be read from lidar: candidates are numbered B1, B2 from the garage end. "
                "Black EPDM returned few lidar points (61 % cell cover), so small units can hide in dropouts. Confirm every spot on site."
            ],
            "facts": rows,
            "features": feats,
            **cams(mid.tolist(), br["roof_z_range_m"][0], 200, 80, 60),
        }
    )

    # ---- RTU-5
    feats = [unit_box(r5)] + edge_lines(r5)
    feats.append(riser(r5, grade, f"{f1(R['RTU-5']['riser_ft'])} ft (calc. estimate)"))
    feats.append(
        {
            "t": "poly",
            "xy": c5["closure_ring"],
            "drape": True,
            "mat": "closure",
            "edge": 0xFF281E,
            "info": info(
                "Airport Road closure area (CALC. ESTIMATE)",
                [
                    ["Length along centreline", f"{f1(c5['closure_length_ft'], 0)} ft"],
                    ["Width", "40 ft (road width NOT measured)"],
                    ["Window", "1:30 to 4:00 AM"],
                ],
                c5["method"],
                "e",
            ),
            "label": "Airport Road closure (est.) · 1:30–4:00 AM",
            "la": [*np.asarray(c5["closure_ring"]).mean(0).tolist(), None],
            "lk": "est",
            "lmax": 400,
        }
    )
    feats.append(
        {
            "t": "marker",
            "at": [*c5["spot_xy"], None],
            "mat": "craneMark",
            "size": 1.2,
            "h": 2.0,
            "info": info(
                "RTU-5 crane spot (CALC. ESTIMATE)",
                [
                    ["Pick radius to unit", f"{f1(c5['pick_radius_ft'])} ft"],
                    [
                        "Pick height above road",
                        f"{f1(c5['pick_height_above_road_ft'])} ft",
                    ],
                ],
                c5["method"],
                "e",
            ),
        }
    )
    feats.append(
        {
            "t": "line",
            "p": flat(
                [
                    [*c5["spot_xy"], None],
                    [*ctr(r5), r5["roof_z_m"] + r5["size_ft"][2] * FT],
                ]
            ),
            "color": 0xFF9D1A,
            "label": f"pick radius {f1(c5['pick_radius_ft'])} ft",
            "la": [
                (c5["spot_xy"][0] + ctr(r5)[0]) / 2,
                (c5["spot_xy"][1] + ctr(r5)[1]) / 2,
                r5["roof_z_m"],
            ],
            "lk": "trench",
            "lmax": 300,
        }
    )
    sites.append(
        {
            "key": "rtu5",
            "title": "RTU-5 · bridge over the curb roadway",
            "button": "RTU-5",
            "addr": "Bridge roof over the terminal curb roadway (Airport Road)",
            "rationale": "12.5 tons. Replaced at night with Airport Road closed 1:30 to 4:00 AM. Feeder 3#8 + 1#10 in 1in, 40A, panel M1 in room #103.",
            "alerts": [
                "Unit position is a LIDAR CANDIDATE (the unit-shaped object on the bridge nearest Airport Road). The nameplate was not read; confirm on site."
            ],
            "facts": [
                [
                    "Size L × W × H",
                    f"{r5['size_ft'][0]} × {r5['size_ft'][1]} × {r5['size_ft'][2]} ft",
                    "m",
                    "lidar",
                ],
                [
                    "Roof surface above grade",
                    f"{f1(r5['roof_above_grade_ft'])} ft",
                    "m",
                    "lidar + DEM",
                ],
                [
                    "Nearest roof drop edge",
                    f"{f1(r5['edge_drop_ft'])} ft",
                    "m",
                    "lidar",
                ],
                [
                    "Riser, roof to ground-floor slab",
                    f"{f1(R['RTU-5']['riser_ft'])} ft",
                    "e",
                ],
                [
                    "Your estimate total (#103)",
                    f"{R['RTU-5']['assumed_total_ft']} ft",
                    "e",
                    "assumption",
                ],
                [
                    "Left for horizontal + roof run",
                    f"{f1(R['RTU-5']['left_for_horizontal_and_roof_ft'])} ft",
                    "e",
                ],
                ["Crane pick radius from road", f"{f1(c5['pick_radius_ft'])} ft", "e"],
                [
                    "Closure band (est.)",
                    f"{f1(c5['closure_length_ft'], 0)} × 40 ft",
                    "e",
                ],
            ],
            "features": feats,
            **cams(ctr(r5).tolist(), r5["roof_z_m"], 160, 60, 35),
        }
    )

    # ---- electrical rooms (placeholders)
    feats = []
    for key, rm in A["rooms"].items():
        z = grade
        feats.append(
            {
                "t": "marker",
                "at": [*rm["xy"], z],
                "mat": "placeholder",
                "size": 1.4,
                "h": 2.2,
                "info": info(
                    rm["label"],
                    [["Status", "NOT LOCATED"], ["Floor", rm["floor"]]],
                    "Interior location is not in public data. The marker sits in a labelled row on the landside lawn, NOT at the room. Locate with a Polycam scan or wheel readings.",
                    "p",
                ),
                "label": f"PLACEHOLDER · {rm['label'].split(' (')[0].replace('Electrical Room', 'Elec. Rm')}",
                "la": [*rm["xy"], z + 3.2],
                "lk": "est",
                "lmax": 350,
            }
        )
    rx = np.mean([rm["xy"] for rm in A["rooms"].values()], axis=0)
    sites.append(
        {
            "key": "erooms",
            "title": "Electrical rooms · placeholders",
            "button": "Elec. rooms",
            "addr": "Rooms #1076, #1077 (SWBD E), #103 (M1), #105 (M3), #204 (M2)",
            "rationale": "Interior locations are not in any public dataset. The yellow posts are a legend row, not positions. "
            "Route lengths stay CALCULATED ESTIMATE until scans or wheel readings come in.",
            "alerts": ["Do not measure from these posts."],
            "facts": [[rm["label"], "NOT LOCATED", "x"] for rm in A["rooms"].values()],
            "features": feats,
            **cams(rx.tolist(), grade, 180, 60, 30),
        }
    )

    # ---- crane staging (AHU-5)
    feats = []
    if cr:
        feats.append(
            {
                "t": "poly",
                "xy": cr["pad_ring"],
                "drape": True,
                "mat": "crane",
                "edge": 0xFF9D1A,
                "info": info(
                    "AHU-5 crane pad (CALC. ESTIMATE)",
                    [
                        ["Pad (placeholder outriggers)", "36 × 36 ft"],
                        [
                            "Pick radius to unit centre",
                            f"{f1(cr['pick_radius_center_ft'])} ft",
                        ],
                        [
                            "Pick radius to far corner",
                            f"{f1(cr['pick_radius_far_corner_ft'])} ft",
                        ],
                        [
                            "Roof above ramp at pad",
                            f"{f1(cr['pick_height_above_ramp_ft'])} ft",
                        ],
                        ["Load (bid package)", "57,900 lb"],
                    ],
                    cr["method"],
                    "e",
                ),
                "label": f"Crane pad (est.) · radius {f1(cr['pick_radius_center_ft'])} ft",
                "la": [*cr["pad_xy"], None],
                "lk": "est",
                "lmax": 600,
            }
        )
        a_ = np.linspace(0, 2 * math.pi, 97)
        rad = cr["pick_radius_far_corner_ft"] * FT
        ring = np.column_stack(
            [
                cr["pad_xy"][0] + rad * np.cos(a_),
                cr["pad_xy"][1] + rad * np.sin(a_),
                np.full(len(a_), cr["ramp_z_m"] + 0.3),
            ]
        )
        feats.append(
            {
                "t": "line",
                "p": flat(ring),
                "color": 0xFF9D1A,
                "label": f"{f1(cr['pick_radius_far_corner_ft'])} ft radius",
                "la": ring[24].tolist(),
                "lk": "note",
                "lmax": 500,
            }
        )
    sites.append(
        {
            "key": "crane",
            "title": "Crane staging · ramp",
            "button": "Crane",
            "addr": "Airside ramp next to the terminal (location per AmeriTech / airport ops)",
            "rationale": "Daylight picks, possibly weekends. The pad is a placeholder footprint on the apron, on the line from the AHU-5 candidate to the nearest ramp, clear of jet bridges and equipment in the 2019 lidar. No crane is selected.",
            "alerts": [
                "Security: access routes, gates and restricted-area boundaries are deliberately not drawn."
            ],
            "facts": [
                [
                    "Pick radius, pad centre to AHU-5 centre",
                    f"{f1(cr['pick_radius_center_ft'])} ft",
                    "e",
                ],
                [
                    "Pick radius, to far corner",
                    f"{f1(cr['pick_radius_far_corner_ft'])} ft",
                    "e",
                ],
                [
                    "Low roof above ramp",
                    f"{f1(cr['pick_height_above_ramp_ft'])} ft",
                    "m",
                    "lidar + DEM",
                ],
                [
                    "Top of AHU-5 candidate above ramp",
                    f"{f1(cr['pick_height_above_ramp_ft'] + ahu['size_ft'][2])} ft",
                    "m",
                    "lidar",
                ],
                ["Load", "57,900 lb", "m", "bid package"],
            ]
            if cr
            else [],
            "features": feats,
            **cams(cr["pad_xy"], cr["ramp_z_m"], 230, 110, 70),
        }
    )

    # ---- overview: route check table
    head = ["Unit · room", "Riser ft", "Your total ft", "Left ft"]
    trows = []
    for r in A["routes"]:
        rv = r["riser_ft"]
        rv = (
            f"{f1(rv[0])}–{f1(rv[1])}"
            if isinstance(rv, list)
            else (f1(rv) if rv is not None else f"≤ {f1(r['riser_bound_ft'])}")
        )
        trows.append(
            [
                f"{r['unit']} · #{r['room'].split('_')[1]}",
                rv,
                str(r["assumed_total_ft"]),
                f1(r.get("left_for_horizontal_and_roof_ft")),
            ]
        )
    uc = A["upper_roof_check"]
    overview = {
        "title": C.VIEWER["overview_title"],
        "button": "Terminal",
        "text": "True-scale model from the 2019 USGS lidar (15 points per m²): the terminal, the pedestrian bridge and the garage "
        "within about 1,000 ft, terrain and buildings out to 1 mile. Unit positions are lidar candidates; electrical rooms are "
        "interior and shown only as placeholders.",
        "alerts": [
            f"Upper terminal roof: GP-1 says about 34 ft. Lidar: main roof {f1(uc['lidar_main_roof_above_grade_ft'])} ft above median grade, "
            f"higher parts up to 34 ft, centre high roof {f1(uc['lidar_highest_roof_above_grade_ft'])} ft.",
        ],
        "tables": [
            {
                "title": "Route check (CALCULATED ESTIMATE)",
                "head": head,
                "rows": trows,
                "note": "Riser = lidar roof at the unit minus the ground-floor slab taken at grade. 'Left' = your total minus the riser: what remains for the room-to-riser horizontal run and the roof run. #204's riser is an upper bound. Full method in ROUTE_LENGTHS.md.",
            }
        ],
    }
    legend = [
        ["#2f7fd8", "Rooftop unit, lidar candidate (blue box)"],
        ["#8d949b", "Alternate candidate (grey box)"],
        ["#ff8a1f", "Riser height, drawn under the unit (x-ray)"],
        ["#ffffff", "Distance to roof edge", True],
        ["#9ad2ff", "Distance to wall / higher roof"],
        ["#ffd21a", "Electrical room PLACEHOLDER (not located)"],
        ["rgba(255,157,26,0.55)", "Crane pad and pick radius (estimate)"],
        ["rgba(255,40,30,0.5)", "Airport Road closure area (estimate)"],
        ["#e04fc8", "Road centreline (OSM) · green: footway"],
        ["#c47ad6", "Building, height not measured"],
    ]
    lc = meta["checks"]["lidar_ground_vs_dem"]
    about = [
        [
            "m",
            f"Ground: USGS 3DEP 1 m DEM (NAVD88). Roofs and units: 2019 USGS lidar {meta['layers']['lidar']['source'].split('lidar ')[1].split(' (')[0]}, {meta['layers']['lidar']['density_pts_m2']} points per m²; lidar vs DEM RMS {lc['rms_dz_m_clipped2m'] / FT:.2f} ft.",
        ],
        [
            "m",
            "Building outlines and roads: Overture Maps / OpenStreetMap. Streams: USGS NHD.",
        ],
        [
            "e",
            "Unit positions are lidar candidates, not tagged. Risers, crane pad, closure band and route checks are calculated estimates.",
        ],
        [
            "x",
            "Not in this model: electrical room locations, roof hatches, roof penetrations, conduit routes, orthophoto, utilities. No Google 3D Tiles.",
        ],
        [
            "",
            "PRIVATE viewer. Security-sensitive airport: no restricted-area, gate, checkpoint or camera details are drawn. No pricing.",
        ],
        [
            "",
            f"Coordinates: NAD83 / UTM 19N (EPSG:26919). Model X = E − {frame.E0:,.0f} m, Y = N − {frame.N0:,.0f} m; heights NAVD88.",
        ],
    ]
    layers = [
        ["terrain", "Terrain, 1 m lidar DEM", True],
        ["groundtex", "Ground colour from lidar intensity (not a photo)", True],
        ["buildings", "Buildings with lidar roofs", True],
        ["trees", "Trees from the lidar canopy", True],
        ["roads", "Roads and footways (OSM)", True],
        ["water", "Streams and ponds (NHD)", True],
        ["layouts", "Units, risers, edge distances, placeholders, crane", True],
        ["overview", "1-mile overview terrain and buildings", True],
        ["labels", "Street and site labels", True],
    ]
    vars_ = {
        "ahu_roof_ft": f1(ahu["roof_above_grade_ft"]),
        "ahu_size": f"{ahu['size_ft'][0]:.0f} by {ahu['size_ft'][1]:.0f} by {ahu['size_ft'][2]:.0f}",
        "ahu_edge": f1(ahu["edge_drop_ft"], 0),
        "ahu_riser": f1(R["AHU-5"]["riser_ft"]),
        "ahu_left": f1(R["AHU-5"]["left_for_horizontal_and_roof_ft"], 0),
        "crane_r": f1(cr["pick_radius_center_ft"], 0),
        "crane_far": f1(cr["pick_radius_far_corner_ft"], 0),
        "bridge_len": f1(br["length_ft"], 0),
        "bridge_road": f1(br["roof_above_road_ft"], 0),
        "n_bridge": str(len(bunits) + 1),
        "r5_riser": f1(R["RTU-5"]["riser_ft"]),
        "r5_r": f1(c5["pick_radius_ft"], 0),
        "r12_riser": f"{R['RTU-1']['riser_ft'][0]:.0f} to {R['RTU-1']['riser_ft'][1]:.0f}"
        if isinstance(R["RTU-1"]["riser_ft"], list)
        else "n/a",
        "r34_bound": f1(R["RTU-3"]["riser_bound_ft"], 0),
        "main_roof": f1(uc["lidar_main_roof_above_grade_ft"], 0),
    }
    json.dump(
        {
            "sites": sites,
            "overview": overview,
            "legend": legend,
            "about": about,
            "layers": layers,
            "tour_vars": vars_,
        },
        open(os.path.join(a.work, "viewer_content.json"), "w"),
        indent=1,
    )
    write_route_md(A, C, meta, os.path.join(a.docs, "ROUTE_LENGTHS.md"))
    write_site_md(A, meta, os.path.join(a.docs, "docs", "SITE_LAYOUTS.md"))
    write_roof_md(A, os.path.join(a.docs, "docs", "ROOF_LEVELS.md"))
    print(
        "wrote viewer_content.json, ROUTE_LENGTHS.md, docs/SITE_LAYOUTS.md, docs/ROOF_LEVELS.md"
    )


def write_site_md(A, meta, path):
    """Per-site measurements (the HVAC job's equivalent of Wilton's SITE_LAYOUTS.md)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    g = A["grade_m"]
    L = []
    w = L.append
    w("# Site measurements: MHT #1988 rooftop units\n")
    w(
        "No EV layouts on this job. Every value is **MEASURED** from the 2019 USGS lidar / 1 m DEM, or a **CALCULATED"
    )
    w(
        "ESTIMATE** with its method, or listed in `MISSING_MEASUREMENTS.md`. Unit tags cannot be read from lidar: the"
    )
    w(
        "positions below are **lidar candidates** until the nameplates are photographed in place.\n"
    )
    w(
        f"Grade (ground-floor reference) = median DEM in a 5–13 ft band around the terminal footprint = {g:.2f} m NAVD88 "
        f"({g / FT:.1f} ft); 5th–95th percentile {A['grade_p5_p95_m'][0]:.2f}–{A['grade_p5_p95_m'][1]:.2f} m.\n"
    )
    w("## Unit candidates\n")
    w(
        "| Tag | Basis | Lat, lon (NAD83) | Model X, Y (m) | Size L × W × H (ft) | Roof surface (ft NAVD88) | Roof above grade (ft) | Top of unit above grade (ft) | To roof drop edge (ft) | To wall / higher roof (ft) |"
    )
    w("|---|---|---|---|---|---|---|---|---|---|")
    for u in A["units"] + A["ahu5_alternates"]:
        w(
            f"| {u['tag']} | {u['confidence'].split(' (')[0].split(';')[0]} | {u['lat']}, {u['lon']} | {u['xy'][0]:.1f}, {u['xy'][1]:.1f} | "
            f"{u['size_ft'][0]} × {u['size_ft'][1]} × {u['size_ft'][2]} | {u['roof_navd88_ft']} | {u['roof_above_grade_ft']} | {u['top_above_grade_ft']} | "
            f"{u['edge_drop_ft']} | {u['wall_ft']} |"
        )
    w("")
    w(
        "Method: DSM = highest lidar return per 0.25 m cell. Terminal: roof surface = grey opening of the DSM (6.25 m window);"
    )
    w(
        "equipment = blobs 0.8–6 m above it; AHU-5 = the largest unit-shaped blob on the lowest roof level (alternates ranked by"
    )
    w(
        "volume). Bridge: roof = cubic fit of the along-axis profile; objects 0.45–5 m above it; arches (narrow, spanning the deck)"
    )
    w(
        "and wing roofs (reaching past the deck edge) are excluded; RTU-5 = the candidate nearest Airport Road. Size = minimum"
    )
    w(
        "rotated rectangle of the blob (±1 ft on each side, lidar spacing). Drop edge = nearest cell more than 1.5 m below the"
    )
    w(
        "unit's roof; wall = nearest cell more than 1.5 m above it. Edge distances are plan distances from the unit outline.\n"
    )
    br = A["bridge"]
    w("## Pedestrian bridge (terminal to garage)\n")
    w("| Measure | Value | Basis |")
    w("|---|---|---|")
    w(
        f"| Length, garage face to terminal face (along the axis) | {br['length_ft']} ft | lidar outline + OSM footprints |"
    )
    w(f"| Deck width at roof level | {br['deck_width_ft']} ft | lidar |")
    w(
        f"| Roof height | {br['roof_z_range_m'][0] / FT:.1f}–{br['roof_z_range_m'][1] / FT:.1f} ft NAVD88; rises {br['roof_rise_ft']} ft toward the terminal | lidar |"
    )
    w(
        f"| Roof above Airport Road at the crossing | {br['roof_above_road_ft']} ft | lidar − DEM |"
    )
    w(
        f"| Structural arches on the roof | {br['arches']}, every {br['arch_spacing_ft']} ft | lidar |"
    )
    w(
        f"| Lidar returns on the roof | {br['lidar_pts_per_m2_on_roof']} pts/m²; {br['lidar_cover_pct']} % of 0.25 m cells hit (black EPDM) | lidar |"
    )
    w("| Underside / deck level | NOT MEASURED (not visible to lidar) | missing list |")
    w(
        "| Unit-sized objects on the deck roof | "
        + ", ".join(u["tag"] for u in A["units"] if u["on"] == "bridge")
        + f" ({sum(1 for u in A['units'] if u['on'] == 'bridge')} for 5 RTUs in the bid package) | lidar |"
    )
    w("")
    cr, c5 = A["crane_ahu5"], A["crane_rtu5"]
    w("## Crane staging (CALCULATED ESTIMATE)\n")
    w("| Pick | Crane spot | Pick radius | Height | Notes |")
    w("|---|---|---|---|---|")
    w(
        f"| AHU-5 (57,900 lb, daylight) | 36 × 36 ft pad on the ramp, model X, Y {cr['pad_xy'][0]:.1f}, {cr['pad_xy'][1]:.1f} | {cr['pick_radius_center_ft']} ft to unit centre, {cr['pick_radius_far_corner_ft']} ft to far corner | low roof {cr['pick_height_above_ramp_ft']} ft above ramp | {cr['method']} |"
    )
    w(
        f"| RTU-5 (night, Airport Road closed 1:30–4:00 AM) | Airport Road centreline, model X, Y {c5['spot_xy'][0]:.1f}, {c5['spot_xy'][1]:.1f} | {c5['pick_radius_ft']} ft | bridge roof {c5['pick_height_above_road_ft']} ft above road | {c5['method']} |"
    )
    w("")
    w(
        "Security: access routes, gates and restricted-area boundaries are not drawn or described in this model."
    )
    open(path, "w").write("\n".join(L) + "\n")


def write_roof_md(A, path):
    g = A["grade_m"]
    uc = A["upper_roof_check"]
    L = ["# Terminal roof levels (2019 USGS lidar)\n"]
    L.append(
        f"Histogram of the lidar surface inside the terminal footprint, 0.5 m bins, levels over 400 m². Heights above grade use {g:.2f} m NAVD88 (median DEM around the terminal).\n"
    )
    L.append(
        "| Roof level (m NAVD88) | ft NAVD88 | Above grade (ft) | Plan area (sq ft) |"
    )
    L.append("|---|---|---|---|")
    for lv in A["terminal_roof_levels"]:
        L.append(
            f"| {lv['z_m']:.2f} | {lv['z_m'] / FT:.1f} | {lv['above_grade_ft']} | {lv['area_sqft']:,} |"
        )
    L.append("")
    L.append(
        f"**Check against the bid package.** GP-1 gives the upper terminal roof as approx. 34 ft. The largest roof level is "
        f"{uc['lidar_main_roof_above_grade_ft']} ft above median grade, with smaller areas at 32.6 and 34.2 ft and the centre high roof "
        f"at {uc['lidar_highest_roof_above_grade_ft']} ft. GP-1 is within about 3 ft of the main roof. The gap could come from the grade "
        "reference GP-1 used or from parapets; public data does not settle it. Use the lidar level at each unit for risers.\n"
    )
    L.append(
        f"The low (valley) roof that carries the AHU-5 candidate is at {A['valley_roof_z_m']:.2f} m bin centre "
        f"(unit-level measurement: {A['units'][0]['roof_z_m']:.2f} m, {A['units'][0]['roof_above_grade_ft']} ft above grade).\n"
    )
    L.append(
        "Not measured: roof structure, deck type, membrane age (TPO 1998 and EPDM 2000 are from the bid package), load capacity, "
        "roof hatches, penetrations. No pricing."
    )
    open(path, "w").write("\n".join(L) + "\n")


def write_route_md(A, C, meta, path):
    grade = A["grade_m"]
    L = []
    w = L.append
    w("# ROUTE_LENGTHS: MHT #1988 feeder and branch-circuit routes\n")
    w(
        "Electrical room to rooftop unit, per unit. Each length is either **MEASURED** (named dataset, or a tape or wheel"
    )
    w(
        "reading) or a **CALCULATED ESTIMATE** with its method. The rooms are interior and are not in any public dataset,"
    )
    w(
        "so **every total stays CALCULATED ESTIMATE** until the Polycam scans or wheel readings on the photo list come in.\n"
    )
    w(
        f"Built {C.DATASETS['retrieved']} from the 2019 USGS lidar ({meta['layers']['lidar']['density_pts_m2']} pts/m²) and the USGS 1 m DEM. "
        f"Ground-floor reference: grade = median DEM around the terminal = {grade:.2f} m NAVD88 ({grade / FT:.1f} ft).\n"
    )
    w("## The four numbers to confirm\n")
    w("| Your assumption | Units | What the model can say tonight |")
    w("|---|---|---|")
    R = {r["unit"]: r for r in A["routes"]}

    def rs(r):
        v = r["riser_ft"]
        if isinstance(v, list):
            return f"{v[0]:.1f}–{v[1]:.1f} ft"
        return (
            f"{v:.1f} ft"
            if v is not None
            else f"≤ {r['riser_bound_ft']:.1f} ft (bound)"
        )

    w(
        f"| 250 ft from #1077 | AHU-5 | Riser {rs(R['AHU-5'])} (CALC. EST.). Leaves {R['AHU-5']['left_for_horizontal_and_roof_ft']:.0f} ft for the room-to-riser run and roof run. The farthest terminal corner is {R['AHU-5']['plan_max_euclid_ft']:.0f} ft from the unit in plan, so 250 ft is possible but not checkable until #1077 is located. |"
    )
    w(
        f"| 120 ft from #103 | RTU-5 | Riser {rs(R['RTU-5'])} (bridge roof over Airport Road). Leaves {R['RTU-5']['left_for_horizontal_and_roof_ft']:.0f} ft. |"
    )
    w(
        f"| 120 ft from #105 | RTU-1, RTU-2 | Riser {rs(R['RTU-1'])} depending on which bridge candidate is which. Leaves about {R['RTU-1']['left_for_horizontal_and_roof_ft']:.0f} ft. |"
    )
    w(
        f"| 60 ft from #204 | RTU-3, RTU-4 | #204 is on the bridge level; its floor is not visible to lidar. Riser is at most {R['RTU-3']['riser_bound_ft']:.0f} ft. Leaves at least {R['RTU-3']['left_for_horizontal_and_roof_ft']:.0f} ft along the bridge. The bridge is {A['bridge']['length_ft']:.0f} ft face to face. |"
    )
    w("")
    w("## Per unit\n")
    w(
        "| Unit | Feeder (E-1/E-2) | From | Unit position | Horizontal run, room to riser | Riser height | Roof run, penetration to unit | Total |"
    )
    w("|---|---|---|---|---|---|---|---|")
    for r in A["routes"]:
        w(
            f"| {r['unit']} | {r['conductors']}, {r['ocpd_a']}A | {r['room_label']} | {r['unit_located']} | "
            f"NOT MEASURED: room interior, not in public data | {rs(r)}, CALCULATED ESTIMATE | NOT MEASURED: penetration not located | "
            f"CALCULATED ESTIMATE pending; your assumption {r['assumed_total_ft']} ft |"
        )
    w("")
    w("## Method\n")
    w(
        "- **Riser height (CALCULATED ESTIMATE).** Roof surface at the unit from the 2019 lidar (measured, about ±0.2 ft) minus the"
    )
    w(
        "  ground-floor slab, taken as grade (median 1 m DEM in a 5–13 ft band around the terminal footprint). Slab-at-grade is an"
    )
    w(
        "  assumption; panel height, ceiling offsets and the roof curb are not included. Add them from the field readings."
    )
    w(
        "- **#204 (bridge room).** The bridge floor is not visible to lidar. Upper bound = highest bridge-unit roof minus (Airport Road"
    )
    w(
        f"  surface {A['bridge']['road_z_m']:.2f} m + 14.5 ft minimum vertical clearance over a roadway). The deck structure is not subtracted, so the"
    )
    w("  real riser is shorter.")
    w(
        "- **Roof run.** Not measured: roof penetrations are not in public data. If the conduit comes up through a curb under the"
    )
    w("  unit, it is 0 ft. Measure it on the roof (photo list item 3).")
    w(
        "- **Horizontal run.** Not measured: rooms are interior. The scans and wheel readings (photo list items 1 and 2) replace it."
    )
    w(
        "- **Unit positions.** Lidar candidates: equipment-sized objects standing 0.8–6 m (bridge: 0.45–5 m) above the fitted roof"
    )
    w(
        "  surface. Tags cannot be read from lidar. See `README.md` for the candidate list and alternates."
    )
    w(
        "- **Plan sanity bound.** Distance in plan from the unit to the farthest corner of the room's building. A total longer than"
    )
    w("  riser + that distance + a reasonable roof run would need checking.\n")
    w("## Lengths that would change a column from CALCULATED ESTIMATE to MEASURED\n")
    w(
        "1. Wheel or tape readings along each route: room door to riser, riser floor to roof, penetration to unit disconnect."
    )
    w(
        "2. Polycam scans of rooms #1077, #103, #105, #204 and each roof area, with 4 named control points and one taped distance."
    )
    w(
        "   Register them with `register_capture.py` (in the .blend) and record the RMS in ft."
    )
    w("3. The roof penetration point for each circuit (photo list item 3).\n")
    w("No pricing is included anywhere in this model.")
    open(path, "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
