# MHT terminal model: Ion Electrical job #1988 (AmeriTech prime), RFP 2600049

Manchester-Boston Regional Airport, Airport Terminal & Walkway HVAC Equipment Replacement. FAA AIP and IIJA funded.
**Private. Security-sensitive. No pricing.**

`blend/MHT1988_Terminal_v1.blend` is a true-scale model of the terminal, the pedestrian bridge and the garage:

- **Detail area:** 300 m (984 ft) around the terminal and the garage end of the bridge, about 3,150 × 3,170 ft.
- **Overview:** terrain and buildings out to 1 mile.
- **Purpose:** check electrical estimating quantities: feeder and branch-circuit routes from the electrical rooms to the rooftop units, riser heights, roof-edge distances, and crane staging. There are no EV layouts and no charger defaults.
- **Rule:** no number is guessed. Each one is either
  - **MEASURED** from a named dataset (or, later, a tape or wheel reading), or
  - a **CALCULATED ESTIMATE** with its method stated, or
  - listed in `MISSING_MEASUREMENTS.md`.

| File | What it is |
|---|---|
| `ROUTE_LENGTHS.md` | **The answer to the four estimate numbers.** Per unit: horizontal run, riser, roof run, each marked MEASURED or CALCULATED ESTIMATE. |
| `blend/MHT1988_Terminal_v1.blend` | The model, ~47 MB. Blender 4.5 LTS or newer. No API key inside. |
| `web/MHT1988_Terminal_Viewer.html` | Browser walkthrough of the same model: orbit, walk at 5.5 ft eye height, drive/fly, measure in ft, click to identify, a narrated team tour. Needs internet once for three.js. A hosted copy is a **private** claude.ai page; share it only from that page's Share menu, and only with the team. |
| `docs/SITE_LAYOUTS.md` | Unit candidates (position, size, roof height, edge distances), the bridge, crane staging. |
| `docs/ROOF_LEVELS.md` | Terminal roof levels from lidar, checked against the GP-1 34 ft note. |
| `MISSING_MEASUREMENTS.md` | What could not be measured, and who or what can supply it. |
| `SOURCE_LOG.md` | Every source with status, date and accuracy, plus what was removed for security. |
| `NEXT_PHOTO_LIST.md` | Tonight's capture list: wheel readings, Polycam scans with control points, nameplates and penetrations. |
| `utilities/UTILITY_ITEMS.csv` | Feeders, panels, rooms and unit candidates: VERIFIED / INFERRED, located or not. |
| `job_config.py` | **Everything job-specific** (see "Per-job config" below). |
| `pipeline/` | The job-agnostic build scripts. `hvac_routes.py` and `hvac_viewer.py` are this job's analysis. |
| `tools/` | The five import and registration tools; they also ship inside the .blend (Scripting tab). |

## Coordinate frame (read this before measuring)

| Item | Value |
|---|---|
| Horizontal CRS | **NAD83 / UTM zone 19N, EPSG:26919, metres** (MHT at 71.44° W is inside zone 19) |
| Vertical datum | **NAVD88 metres** (GEOID12B, per the NH_Coastal_2019 metadata). Blender Z *is* the NAVD88 height. |
| Scene origin offset | **X = Easting − 301,000 m; Y = Northing − 4,756,000 m; Z = 0** |
| Origin in NH State Plane (EPSG:3437, US ft) | E 1,045,310.01 ft, N 157,034.65 ft. `pipeline/frame.py` matches pyproj to 0.18 mm over ±1.5 km. |
| Blender units | 1 unit = 1 m; display set to **feet**, so the Measure tool reads ft. |
| Georef keys in the scene | `SRID`, `crs x`, `crs y` (BlenderGIS), `lat`, `lon`, `crs_note`, `vertical_datum`. The tools read the origin from `crs x` / `crs y`. |

To get a real coordinate from any point: E = X + 301,000; N = Y + 4,756,000; NAVD88 ft = Z × 3.28083.

## Centre check (1 Airport Road)

The centre was resolved from the data, not typed in: it is the centroid of the Overture/OSM **"Terminal Building"** footprint (204,584 sq ft, 3 floors in OSM). That footprint contains 26 of the 35 Overture places addressed "1 Airport Rd".

| Point | Lat, lon | Distance |
|---|---|---|
| **Model centre** (terminal centroid) | **42.927595, −71.438207** | |
| Overture places at 1 Airport Rd (median of the 26 inside the terminal) | 42.927902, −71.437575 | **203 ft** from the centre |
| Overture place "Manchester-Boston Regional Airport" | 42.929684, −71.435214 | **1,106 ft** from the centre, 678 ft outside the terminal: it marks the airport, not the terminal |
| USGS National Structures | **no terminal point.** Only the ARFF station (402 Kelly Ave) at 42.933373, −71.431057 | 2,846 ft from the centre. Used as a sanity check only. |
| USGS vs Overture | USGS ARFF vs Overture "Manchester Airport Fire Sta" (same address) | **1,603 ft apart: conflict.** USGS ARFF vs the Overture airport place: 1,746 ft. |

**Coverage:** USGS National Structures does not cover the terminal. Overture places do. So the centre rests on the Overture/OSM terminal footprint, cross-checked by the tenant places and the lidar roof.

## Headline findings for tonight's walk

1. **The four estimate numbers can't be confirmed from public data, because the rooms are interior.** What the model fixes is the vertical part and the geometry around it. See `ROUTE_LENGTHS.md`.

   | Your number | Riser (CALC. EST.) | Left for horizontal + roof run |
   |---|---|---|
   | 250 ft, #1077 → AHU-5 | 18.9 ft | 231 ft |
   | 120 ft, #103 → RTU-5 | 33.2 ft | 87 ft |
   | 120 ft, #105 → RTU-1 / RTU-2 | 26.5–28.0 ft | about 92 ft |
   | 60 ft, #204 → RTU-3 / RTU-4 | ≤ 14.2 ft (upper bound; #204 is on the bridge level) | ≥ 46 ft |

   - Risers are taken from the lidar roof at the unit down to a ground-floor slab assumed at grade (68.81 m NAVD88).
   - **RTU-5 is the tightest.** It sits on the bridge over Airport Road, 33 ft above grade, so a third of the 120 ft goes to the riser.

2. **AHU-5 candidate on the low roof:**
   - About **60.5 × 18.9 × 13.0 ft**, the largest unit-shaped object on the low (valley) roof.
   - The low roof is **18.9 ft above grade**.
   - The nearest roof drop edge is 54 ft away; a higher-roof wall is 1 ft away.
   - Three smaller alternates on the same roof are listed. **Confirm the tag on site.**

3. **Only 3 unit-sized objects show on the bridge roofs for the 5 RTUs in the bid package.**
   - RTU-5 candidate: 10.7 × 9.8 × 5.6 ft, at the terminal end.
   - B1: 13.9 × 11.5 × 6.0 ft, at the garage-end head house, now tagged **RTU-2**.
   - B2: 9.0 × 7.4 × 3.5 ft, now tagged **RTU-1**.
   - Tags come from the pre-bid meeting (the airport put RTU-1/2 at the garage end, RTU-3/4 mid-bridge, RTU-5 on the escalator/elevator building) plus size (20 t vs 6 t). Set in `job_config.py` → `BRIDGE_UNIT_TAGS`.
   - RTU-3 and RTU-4 are not in the lidar: the black EPDM returned lidar on only 61 % of cells.
   - **No nameplate has been read yet.** See `docs/HANDOFF.md` for where things stand.

4. **Bridge geometry (measured):**
   - 359 ft from the garage face to the terminal face; deck roof 38 ft wide.
   - Roof is 34.2 ft above Airport Road and rises 5.3 ft toward the terminal.
   - 6 structural arches cross the roof about 54.5 ft apart. The pedestrian bridge has **no OSM footprint**; its outline here comes from the lidar.

5. **Crane, AHU-5 (CALCULATED ESTIMATE):**
   - A placeholder 36 × 36 ft pad on the ramp south of the unit, clear of jet bridges in the lidar.
   - Pick radius **110 ft** to the unit centre and **129 ft** to its far corner, for 57,900 lb.
   - The low roof is 19 ft above the ramp.
   - Location to confirm with AmeriTech / airport operations.

6. **Crane, RTU-5 (CALCULATED ESTIMATE):**
   - From the Airport Road centreline, **77 ft** pick radius; the bridge roof is 34 ft above the road.
   - The closure band is drawn 300 × 40 ft (roadway width NOT measured).

7. **Upper terminal roof vs GP-1 (34 ft):**
   - Lidar main roof is **31.0 ft** above median grade (69,655 sq ft).
   - Smaller areas sit at 32.6 and 34.2 ft; the centre high roof is 45.7 ft.
   - GP-1 is within about 3 ft. Use the lidar level at each unit.

## Site summary (full tables in `docs/SITE_LAYOUTS.md`)

| Site | Where | What is drawn | Basis |
|---|---|---|---|
| AHU-5 | Low (valley) roof, 1998 expansion | Unit box + 3 alternates, distance to roof edge and to the wall, riser height (x-ray), pick-radius line | lidar candidate; riser CALC. EST. |
| RTU-1 to RTU-4 | Bridge roof, terminal to garage | Candidates B1, B2, bridge axis with length, edge distances, riser heights | lidar candidates, tags open |
| RTU-5 | Bridge roof over the curb roadway | Unit box, crane spot on Airport Road, pick radius, closure band | lidar candidate; crane CALC. EST. |
| Electrical rooms | Interior | Labelled PLACEHOLDER posts in a row on the landside lawn. **They are not positions.** | not located |
| Crane staging | Ramp | 36 × 36 ft placeholder pad, 129 ft radius ring | CALC. EST. |

Not shown by design: restricted-area boundaries, gate numbers, contractor access routes, checkpoints and cameras.

## What is in the .blend (Outliner collections)

| Collection | Source / status |
|---|---|
| 00 Terrain | USGS 3DEP 1 m DEM (NH_Coastal_2019_B19): 1 m cells in the detail area, 8 m cells to 1 mile |
| 01 Orthophoto drape | **NOT LOADED**: `drape_orthophoto.py`. The ground shows a lidar-intensity composite, labelled "NOT a photo". |
| 02 Buildings (detail / overview) | 25 Overture/OSM footprints with 2019 lidar roofs, plus the lidar-derived pedestrian bridge (deck drawn 4 m deep; underside not measured). 424 overview footprints, 386 with lidar height; **purple** = height not measured. |
| 03 Trees | 404 tree tops from the lidar canopy |
| 04 Water | NHD flowlines (context) |
| 05 Flood / 06 Wetlands / 07 Parcels | Empty, named with the tool that fills them |
| 08 Roads + sidewalks | Overture/OSM centrelines. Widths not measured. |
| 09 Utilities | Empty, for field tags (`import_field_points.py`) |
| 10 AHU-5 · 11 RTU-1 to RTU-4 · 12 RTU-5 · 13 Electrical rooms · 14 Crane staging | Same features as the web viewer. Numbers are stored on each object (N panel → Item → Properties). |
| 15 Roof levels | One marker per measured terminal roof level |
| 20 Cameras + lights | Per site: `CAM aerial` and `CAM eye level` |
| 30 Google 3D Tiles | Empty. Only if you set the key in Blender's preferences yourself. Visual only. |

## Step by step on the Mac

1. **Blender 4.5 LTS:** download from <https://www.blender.org/download/lts/4-5/> and open `blend/MHT1988_Terminal_v1.blend`.
2. **Look and measure:**
   - **Shift + `** walks (W A S D; **Tab** toggles gravity).
   - **T → Measure** reads feet; hold **Ctrl** to snap.
   - Click a unit box and press **N → Item → Properties** for its numbers and basis.
3. **Embedded docs and tools:** the **Scripting** tab text menu has README, ROUTE_LENGTHS, MISSING_MEASUREMENTS, SOURCE_LOG, NEXT_PHOTO_LIST, SITE_LAYOUTS, ROOF_LEVELS and the five tools.
4. **Polycam scans** (photo list item 2):
   - Export the scan as **GLB**, then File → Import → glTF.
   - Add empties `CP1_scan` / `CP1_model` … `CP4_scan` / `CP4_model` on the same marks.
   - Select the scan and run `register_capture.py`. It prints the scale and the RMS in ft. Record the RMS next to the scan in `ROUTE_LENGTHS.md`.
5. **Field points** (penetrations, hatches, disconnects, control points):
   - Fill `tools/field_points_template.csv`.
   - Set `CSV_PATH` in `import_field_points.py` and run it.
6. **Wheel readings:** enter them in `ROUTE_LENGTHS.md` and mark each one **MEASURED (wheel, date, who)**.
7. **Google 3D Tiles (optional, visual only):**
   - Only with your own key in Blosm's preferences.
   - Import, run `google_tiles_to_utm.py`, then **Save As** a `…_google.blend` copy. That copy is git-ignored and never shared.

All tools read the CRS from the `.prj` file (NH State Plane ft, UTM 19N, lon/lat) and the origin from the scene.

## Accuracy, honestly

| What | Accuracy | Basis |
|---|---|---|
| Ground heights | ~0.1 ft vertical (open ground) | Lidar ground vs DEM: median 0.002 m, RMS 0.021 m over 200,000 points |
| Roof heights at a unit | ±0.2–0.5 ft | Lidar returns at 15 pts/m²; the bridge's black EPDM gives fewer |
| Unit outlines | ±1 ft each side | 0.25 m DSM cells, minimum rotated rectangle |
| Building outlines | 1.5–3 ft | OSM traces (no registration shift needed) |
| Road centrelines | 3–10 ft | OSM; widths not measured |
| Riser heights | Assumption-limited | Slab-at-grade assumption; tape the floor-to-floor heights |
| Room positions and horizontal runs | **not measured** | Interior |

Only tape, wheel or registered Polycam capture gets route lengths to the ±1 ft an estimate needs. This lidar model is the frame to register them into.

**How roofs are drawn.** Each roof level and each roof object is a flat block traced from a 0.5 m lidar roof surface (per-cell max, 3 × 3 median, levels snapped within ±0.25 m, outlines simplified 0.6 m with shared edges kept), extruded to the ground. The blocks are for display only. Every number in the panels and docs comes from the raw lidar points in `hvac_routes.py`, and none changed when the display switched from the 1 m grid to blocks. Thin parapets (under ~1 m) are not drawn.

**Google 3D Tiles would not make it more accurate.** Google's photorealistic mesh is a photogrammetry surface, typically off by a metre or more and smoothed at roof edges. It looks better but measures worse than the 15 pts/m² lidar this model is built on, and its terms don't allow keeping it. The path to better numbers is field capture (tape/wheel, Polycam with control points) and the room locations (drawings). The path to better looks is an orthophoto drape (`drape_orthophoto.py`, GRANIT 6-inch) and, if wanted, Google tiles in a private `…_google.blend` copy (step 7).

**Field photos.** The pre-bid walk photos are tied in by EXIF position and heading: see `docs/FIELD_PHOTOS.md` and the purple posts and sight lines in the viewer.

## Per-job config (first reuse of the Wilton pipeline)

The Wilton #1976 folder is unchanged. Its job-specific parts now live in `job_config.py`, and the scripts in `pipeline/` read it (`--config PATH`, or the `JOB_CONFIG` environment variable). For the next job, copy `pipeline/` and `tools/`, write a new `job_config.py`, and add an analysis module if the purpose differs.

| Wilton (hard-coded) | Now in `job_config.py` |
|---|---|
| `frame.py`: `SITES`, `CENTER`, radii, UTM zone, `E0`/`N0` | `FRAME` (CRS, origin, radii, state plane) and `SITES`; the centre is **resolved** by `CENTER_RESOLVE` |
| `prepare_downtown.py`: DEM tiles, EPT project, NHD file, structures file, Overture release, site-check predicates | `DATASETS` (DEM tiles are picked from the area bounds; the first EPT project that returns points is used), `DETAIL` |
| `layouts.py`: charger rules, overlays | `ANALYSIS` → `pipeline/hvac_routes.py` (this job); EV jobs would point at a layouts module |
| `export_web.py` / `viewer_template.html` / `tour.json`: titles, legend, layers, site panels, narration | `VIEWER`, `TOUR`, and the generic feature format written by the analysis (`viewer_content.json`) |
| Embedded tools: `E0, N0 = 276000, 4747000` | Read from the scene's `crs x` / `crs y` |
| (none) | `REDACT`: security terms dropped at the prepare step; `FEEDERS`, `ROOMS`, `ESTIMATE_ASSUMED_FT` |

## Rebuilding

```bash
# Python 3.11+: numpy scipy shapely pyproj pyarrow laspy lazrs rasterio requests pillow pyogrio
# USGS Structures NH GPKG and NHD HU8 01070006 GPKG: URLs in job_config.py DATASETS (unzip first)
cd pipeline
python frame.py                                   # checks the transforms against pyproj
python prepare_site.py --cache CACHE --work WORK --nhd NHD_H_01070006_HU8_GPKG.gpkg --struct STRUCT_New_Hampshire_State_GPKG.gpkg
python hvac_routes.py --work WORK                 # unit candidates, bridge, risers, crane -> analysis.json
python hvac_viewer.py --work WORK                 # viewer_content.json, ROUTE_LENGTHS.md, docs/
python export_web.py --work WORK                  # web/MHT1988_Terminal_Viewer.html (~7.3 MB; --bare for hosting)
# Blender 4.5: pip bpy==4.5.x with "numpy<2" and shapely, in a Python 3.11 venv
python build_blend.py --work WORK --out ../blend
```

## Credits

- USGS 3DEP lidar / DEM, NHD and National Structures: public domain.
- Overture Maps Foundation / © OpenStreetMap contributors: ODbL.
