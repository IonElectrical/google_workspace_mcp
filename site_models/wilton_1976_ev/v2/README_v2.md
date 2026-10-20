# Wilton downtown model v2: Ion Electrical job #1976 (RANH Level 2 pilot)

`blend/Wilton1976_Downtown_v2.blend` is one Blender file at true scale covering downtown Wilton NH:

- **Detail area:** ~400 m around each of the 4 candidate sites, about 3,000 × 3,500 ft.
- **Overview:** terrain and buildings out to 2 miles.
- **Rule:** no number in the file is guessed. Each one is either
  - **MEASURED** from a named public dataset, or
  - a **CALCULATED ESTIMATE** with its method stated, or
  - listed in `MISSING_MEASUREMENTS.md`.

| File | What it is |
|---|---|
| `blend/Wilton1976_Downtown_v2.blend` | The model, ~66 MB. Opens in Blender 4.5 LTS or newer. Contains no API key. |
| `README_v2.md` | This file: frame, findings, Mac steps. |
| `docs/SITE_LAYOUTS.md` | Per-site layout measurements: slopes, clearances, trench lengths, overlays. |
| `docs/MILL_ROOF.md` | Mill roof plane table and comparison with the 93k / 94k / 100k claims. |
| `MISSING_MEASUREMENTS.md` | What could not be measured, and who or what can supply it. |
| `SOURCE_LOG.md` | Every source with status, date and accuracy. |
| `FIELD_CHECKLIST.md` | What to capture on site today. |
| `*.py` | The build pipeline, plus five import tools that also ship inside the .blend (Scripting tab). |
| `web/Wilton_Downtown_Viewer.html` | Browser walkthrough of the same model (three.js): orbit, walk at 5.5 ft eye height, site jumps, layer toggles, click-to-identify, measure in ft. Opens offline in Chrome/Safari (needs internet once for three.js). A hosted copy was published as a private claude.ai page; share it from that page's Share menu. Rebuild with `export_web.py`. |

## Coordinate frame (read this before measuring)

| Item | Value |
|---|---|
| Horizontal CRS | **NAD83 / UTM zone 19N, EPSG:26919, metres** |
| Vertical datum | **NAVD88 metres** (GEOID12B, per the NH_Coastal_2019 metadata). The Blender Z value *is* the NAVD88 height. |
| Scene origin offset | **X = Easting − 276,000 m; Y = Northing − 4,747,000 m; Z = 0** |
| Origin in NH State Plane (EPSG:3437, US ft) | E 964,280.63 ft, N 124,929.40 ft. Computed in `frame.py`; checked against pyproj to < 1 mm. |
| Blender units | 1 unit = 1 m. Display is set to **feet**, so the Measure tool and N-panel read in ft. |
| Grid convergence at the mill | 1.863°. Grid north is not true north; roof azimuths in `docs/MILL_ROOF.md` are true. |
| Georef keys in the scene | BlenderGIS (`SRID`, `crs x`, `crs y`), Blosm (`lat`, `lon`), plus `crs_note` and `vertical_datum`. |

To get a real coordinate from any point in Blender, add the offset:

- E = X + 276,000
- N = Y + 4,747,000
- NAVD88 ft = Z × 3.28083

The same offset is stored in the file's scene properties.

## Headline findings for today's walk

1. **S1 Police lot: reported sodium-cyanide vault next door.**
   - EPA (Feb 2023, Abbott Trust Lot J-104-2) describes a vault under a concrete cap "adjacent to the Wilton Police Department".
   - EPA warns a reassessment may be needed if construction disturbs it.
   - **Its exact location is not mapped anywhere we could reach.** Locate it before any trench at S1.
   - It is shown as a red warning label in the model.
2. **S2 Main St lot is not ADA-flat where the layout fits.**
   - The best row has a 3.06 % slope on the van-accessible aisle; the limit is 2.08 %.
   - One EV stall there sits at 10.72 %.
   - The lot needs regrading or a different row. Shoot grades on site.
3. **S2 location conflict.**
   - The brief puts the lot at the SE corner of Main St / Burns Hill Rd. The paved area the data shows is **SW** of the junction.
   - USGS places Town Hall **1,284 ft** from the brief's point; Overture's "Town of Wilton" point is 162 ft away.
   - Confirm the lot boundary on site.
4. **S3 Library: the street is Forest Rd in OSM, not Main St** as in the brief. Confirm.
   - The street-side row is flat: 0.97 % maximum.
   - The library sits ~13 ft above the curb. The trench drops 13.4 ft over ~71–75 ft, so plan for a bore or a stepped trench.
5. **S4 Mill: measured footprint 46,782 sq ft.**
   - The 93,000 / 93,890 / 94,000 / 100,000 sq ft claims are 1.99–2.14 × the footprint.
   - So the claims are **floor area across ~2 levels, not roof or land area.**
   - Usable roof after a 4 ft setback is **29,505 sq ft**. Solar potential is about **413 kW-DC** (CALCULATED ESTIMATE).
6. **The FEMA flood zones, parcels, wetlands and orthophoto could not be downloaded from here** (network policy).
   - The model shows distance rings and lidar water-surface heights, not BFEs.
   - Steps to load the real layers in 2 minutes each on the Mac are below.
   - The FIRM in effect is dated **2009-09-25**.
7. **RANH funding cap (arithmetic only).**
   - $100k per town ÷ $10k per port = **10 ports at the per-port maximum**, e.g. 5 dual pedestals across all sites.
   - This model shows 2 duals per site (16 ports total).
   - The 5-year operating term in the brief is **not confirmed** on the NHDES page. The first application window closes **2026-11-15**.

## Site layouts (summary; full tables in `docs/SITE_LAYOUTS.md`)

Every site uses the same design inputs:

- 2 dual pedestals per site (the brief allows 1–5)
- 18 ft × 9 ft stalls. The 9 ft width is an assumption; confirm it.
- ADA van stall with an 8 ft aisle
- 3 ft plow buffer and 24 ft drive aisle
- Generic 0.76 × 0.61 m pad

Trench lengths start from a **placeholder** power point, because no transformer or service location is mapped. Re-route them once the real location is tagged.

| Site | Layout | ADA stall/aisle slope | Max slope | To mapped water | Above stream surface | Trench (CALC. EST.) | Overlays in model |
|---|---|---|---|---|---|---|---|
| S1 Police lot, 7 Burns Hill Rd | back half of lot, near building | 1.22 % ✔ | 2.44 % | 117.9 ft (Stony Brook) | 8.6 ft | 40.8 + 29.1 ft | 40-space "deed undelineated" area (24,811 sq ft, whole paved lot); police exit keep-clear (10,373 sq ft, assumed route); cyanide warning |
| S2 Main St lot | paved area SW of Main/Burns Hill | **3.06 % ✘** | **10.72 %** | 51.5 ft (Souhegan) | 23.0 ft | 19.7 + 34.8 ft (from Main St edge) | 150 / 250 ft rings toward Stony Brook (brief's AE/floodway band); snow corner not mapped |
| S3 Library street-side | parallel stalls on the measured pavement edge | 0.46 % ✔ | 0.97 % | 57.3 ft (Stony Brook) | 9.0 ft | 70.6 + 74.6 ft (13.4 ft drop) | riverwalk 5 ft away |
| S4 Mill | beside north building (Computer Haven) | 0.32 % ✔ | 2.08 % | 71.7 ft (Souhegan) | 17.2 ft | 42.5 + 20.5 ft | pedestrian bridge corridor 317.9 ft (141.9 ft over water); dike trace; 21 Mill St point; roof planes |

How to read the "above stream surface" column:
- It is ground at the stalls minus the lidar's hydro-flattened water surface at the nearest channel point.
- It shows relative height only. It is **not a BFE** and **not a flood-zone determination**.

**S4 dike (CALCULATED ESTIMATE).** Traced around the NHD pond beside the mill:
- Pond area 88,954 sq ft; water surface 354.3 ft NAVD88
- Crest 357.6–364.3 ft; median 3.7 ft above the pond
- Confirm on site that this is the Waterworks dike.

## Mill roof (summary; full table in `docs/MILL_ROOF.md`)

| | North building (Computer Haven, Sentry Solutions, WS Packaging) | South building (Printorium Apparel) | Total |
|---|---|---|---|
| Footprint | 14,139 sq ft | 32,643 sq ft | **46,782 sq ft** |
| Roof planes (sloped area) | 8 planes | 3 planes | 42,875 sq ft |
| Usable, 3 ft / 4 ft setback (EST.) | | | 32,437 / **29,505 sq ft** |
| Solar, 4 ft setback (EST.) | | | **412.6 kW-DC** |

Method:
- Planes come from RANSAC fits to 2019 lidar single returns.
- Setbacks are exact distance-transform erosion.
- Obstructions are lidar blobs over 0.5 m tall, plus a 1 m clearance.
- kW-DC = usable m² × 215 W/m² × coverage. Coverage is 0.70 for flat roofs and 0.85 for pitched; north-facing pitches are excluded.

Not measured: roof structure, age, membrane and load capacity. No pricing is included.

## What is in the .blend (Outliner collections)

| Collection | Source / status |
|---|---|
| 00 Terrain | USGS 3DEP 1 m DEM (NH_Coastal_2019_B19), 1 m cells in the detail area; 8 m cells to 2 mi |
| 01 Orthophoto drape | **NOT LOADED.** Run `drape_orthophoto.py` with GRANIT tiles. The ground now shows a lidar-intensity composite, labelled "NOT a photo". |
| 02 Buildings (detail) | 264 Overture/OSM footprints, registered to the lidar (shift 0.5 m E, −1.25 m N, measured), with roof shapes from 2019 lidar. 5 have no lidar returns and are drawn as outline only. |
| 02 Buildings (overview) | 1,353 footprints to 2 mi. Heights for 1,095 of them from sparse lidar; **purple** = height not measured. |
| 03 Trees | 8,742 tree tops from the lidar canopy (position ±1 m, height ±0.5 m). Crown size is an estimate. |
| 04 Water | NHD HR flowlines and waterbodies (Souhegan River, Stony Brook, reservoirs); dike trace (EST.); sluiceway **not identified** |
| 05 Flood zones / 06 Wetlands / 07 Parcels | **NOT LOADED** (empty, named with the tool to use) |
| 08 Roads + sidewalks | Overture/OSM centrelines and footways (riverwalk). Widths not measured. |
| 09 Utilities | Empty, for site tags (`import_field_points.py`). No utility data exists in open sources here. |
| 10–13 Site 1–4 | Stalls, ADA stall + aisle, pedestals on pads, plow buffer, trench tubes with length labels, power placeholder, overlays, fact label, cameras |
| 14 Mill roof planes | Lidar roof planes, with area / pitch / azimuth stored on each object (N-panel → Item → Properties) |
| 20 Cameras + lights | Per site: `CAM eye level` (5.5 ft) and `CAM aerial` |
| 30 Google 3D Tiles | Empty. Optional, **visual only**. See step 4 below. |

## Step by step on Edward's Mac

### 1. Blender
1. Download **Blender 4.5 LTS** from <https://www.blender.org/download/lts/4-5/>: **macOS Apple Silicon** (Intel on older Macs).
2. Drag it to Applications and open it. Allow online access if asked.
3. Why 4.5 and not 5.x: Blosm imports Python's `distutils`, which Blender 5.1+ no longer ships.
4. Open `Wilton1976_Downtown_v2.blend` (double-click, or File → Open).

### 2. Look around and measure
- **Walk the site:** hover over the 3D view and press **Shift + `** (or View → Navigation → Walk Navigation).
  - Move with **W A S D** and look with the mouse.
  - **Tab** toggles gravity, so you walk on the terrain at eye height.
  - **Shift** runs; click to stop.
- **Cameras:** Outliner → *20 Cameras + lights* → right-click e.g. `S1_PoliceLot CAM eye level` → **Set Active Camera**. Then press **Numpad 0** (or View → Cameras → Active Camera).
- **Measure:** press **T** for the toolbar, pick the **Measure** ruler, then drag. It reads in **feet**.
  - Hold **Ctrl** to snap to surfaces.
- **Numbers on objects:** click a stall, trench or roof plane, press **N**, and open Item → *Properties*. Sources and values are stored there.
- **Embedded notes:** the **Scripting** tab → text dropdown has these same docs (README, SITE_LAYOUT_MEASUREMENTS, MILL_ROOF, SOURCE_LOG, MISSING_MEASUREMENTS) and the tools.

### 3. Google key and Blosm (only needed for the optional Google mesh)
The full click-by-click is in `../README.md` sections 2–3. In short:
1. Google Cloud console:
   - Create a project and link billing.
   - **APIs & Services → Library → Map Tiles API → Enable**.
   - **Credentials → Create credentials → API key**.
   - Restrict the key to *Map Tiles API*.
2. Download Blosm from <https://prochitecture.gumroad.com/l/blender-osm> (price 0 is accepted).
3. In Blender, go to **Edit → Preferences → Add-ons → ⌄ → Install from Disk…**, choose the zip, then tick **Blosm**.
4. Open Blosm's settings, paste the key into **Google 3D Tiles Key**, and set a data folder.

**The key lives only in Blender's preferences on the Mac.** Never put it in a .blend, a script, a chat or an email. Nothing in this folder contains a key.

### 4. Optional: Google Photorealistic 3D Tiles (VISUAL ONLY, never measure from them)
1. Press **N** in the 3D view and open the **Blosm** tab. The panel is pre-filled:
   - 3D Tiles / Google / *buildings with details*
   - **Relative to initial import** ticked
   - Extent = the detail area
   - If the extent is blank, paste `-71.744318,42.839155,-71.733595,42.849047` with the **paste** button.
2. Click **import**. It takes several minutes for this area; choose *separate buildings* (lod4) for a quicker pass.
3. Go to the **Scripting** tab, pick **google_tiles_to_utm.py** from the text dropdown, and click **▶ Run Script**.
   - The script converts every vertex from Blosm's frame to UTM 19N / NAVD88.
   - It then snaps the mesh vertically to the lidar ground and reports the shift.
4. **Save As** a copy named `…_google.blend` (git-ignored). Google's terms limit storing tiles, so keep that copy internal and use renders with "Google" attribution in proposals.

### 5. Load the missing GIS layers (each takes about 2 minutes)
Every import tool runs the same way:
1. Open the **Scripting** tab.
2. Pick the tool from the text dropdown.
3. Edit the line(s) under `SETTINGS`.
4. Click **▶ Run Script**.

Each layer lands draped on the terrain, in its own collection.

| Layer | Download (on the Mac) | Tool + setting |
|---|---|---|
| **FEMA flood (AE, floodway, BFE)** | Go to <https://msc.fema.gov/portal/home>, search "Wilton, NH", then **Search All Products → Effective Products → NFHL → Hillsborough County (33011C)**. Download and unzip. Direct product ID: `NFHL_33011C`. | `import_gis_layer.py`. Run it three times: `PATH = …/S_FLD_HAZ_AR.shp` (zones; floodway = `ZONE_SUBTY` FLOODWAY), then `…/S_BFE.shp` (BFE lines), then `…/S_XS.shp` (cross-sections). |
| **Parcels** (21 Mill St, 13-ft strip, J-104-x lots) | **NRPC MapGeo** <https://nrpcnh.mapgeo.io> for viewing. To download: open the NRPC parcels layer `https://services6.arcgis.com/2ZriDy2NFXltCIFR/ArcGIS/rest/services/NRPCOpenData/FeatureServer/2/query?where=1%3D1&geometry=-71.7443,42.8392,-71.7336,42.8490&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326&f=geojson` in a browser and save it as `wilton_parcels.geojson`. Fallback: the NH Parcel Mosaic on <https://www.nhgeodata.unh.edu/>. | `import_gis_layer.py`, `PATH = …/wilton_parcels.geojson`, `LAYER_NAME = "Parcels NRPC"` |
| **Orthophoto** (GRANIT 2021/22, 6-inch) | <https://granit.unh.edu/> → Image Download Tool → *USGS NH 2021/2022 6-inch*. Draw a box over downtown and download the GeoTIFF tiles with their `.tfw` files. | `drape_orthophoto.py`, `FOLDER = …`, `CRS = "NH_SP_FT"` |
| **Wetlands** | NWI: <https://www.fws.gov/program/national-wetlands-inventory/data-download> → HUC8 **01070006** shapefile. NHDES: <https://nhdeswppt.unh.edu/> | `import_gis_layer.py`, `PATH = …/HU8_01070006_Wetlands.shp` |
| **Field tags** (poles "5" / "Wilton Telco 3", transformers, pad-mounts, meters) | Fill in `field_points_template.csv` with CompanyCam GPS (lat/lon) for each item. | `import_field_points.py`, `CSV_PATH = …`. Then drag each marker onto the feature you can see in the lidar. |
| **Polycam capture** | Polycam → Export → **GLB**. In Blender, File → Import → glTF and select it. | Add pairs of empties named `CP1_scan` / `CP1_model` (at least 3, ideally 4+, spread out) on the same curb corners and pole bases, then run `register_capture.py` with the capture selected. It prints the scale and the RMS residual in ft; record that number. |

The tools read the CRS from the `.prj` file:
- NH State Plane ft (EPSG:3437/3445), UTM 19N, and lon/lat (NAD83/WGS84) are handled.
- Anything else stops with a message.

All tools were tested here on synthetic data:
- GeoJSON and State Plane shapefile: 0.0 / 0.3 mm
- Orthophoto UV: matches
- Field points: 0.4 mm
- Capture registration: recovered the scale to 0.1 %, RMS 0.14 ft with 2 cm simulated point noise
- Google conversion: 0.2 mm on markers

### 6. After loading layers
- **Re-route trenches:** select a `TRENCH` object, press **Tab**, then move points with **G** and add points with **E**. The label updates its length in feet live.
- **Move a layout:** select its stall objects and the pedestal, then press **G** to move.
- **Flood check:** compare stall ground (fact label, NAVD88 ft) with `STATIC_BFE` from S_FLD_HAZ_AR / S_BFE.
  - Confirm the 2009 FIS datum is NAVD88 before comparing.

## Accuracy, honestly

| What | Accuracy | Basis |
|---|---|---|
| Ground heights | ~0.2 ft vertical (non-vegetated) | Lidar ground vs DEM check: median 0.001 m, RMS 0.056 m over 200,000 points. The USGS project report gives NVA 7.6 cm (95 %), per a search summary; the report itself was not opened. |
| Ground position (curbs, grade breaks) | ~1.5–3 ft | 1 m DEM cells; 0.5 m intensity raster |
| Building outlines | ~1.5–3 ft after registration | OSM traces shifted by the measured best fit (0.5, −1.25 m); roof edges come from lidar points |
| Roof heights / planes | ±0.5 ft | lidar single returns |
| Road / footway lines | 3–10 ft | OSM centrelines; widths not measured |
| Water lines | NHD high-res, 1:24k or better | Use the lidar water surface for heights |
| Google tiles | not survey grade | Visual context only |

The brief asks for ~1 ft accuracy. Only Polycam / total-station capture, registered with `register_capture.py`, gets there. The lidar model is the frame to register into.

## Rebuilding

```bash
# Python 3.11: numpy scipy shapely pyproj pyarrow laspy lazrs rasterio requests pillow pyogrio
# 1) data (~5 min): DEM, lidar EPT, Overture, NHD HU8 01070006 GPKG, USGS Structures NH GPKG
python prepare_downtown.py --cache CACHE --work WORK --nhd NHD_H_01070006_HU8_GPKG.gpkg --struct STRUCT_New_Hampshire_State_GPKG.gpkg
python layouts.py --work WORK          # writes layouts.json + layouts.md (docs/SITE_LAYOUTS.md)
python mill_roof.py --work WORK --cache CACHE   # writes mill_roof.json + MILL_ROOF.md
python export_web.py --work WORK  # writes web/Wilton_Downtown_Viewer.html (~8 MB)
# 2) Blender 4.5 (or pip bpy==4.5.x with "numpy<2"); --blosm = folder containing blosm/
blender -b --factory-startup -P build_downtown_v2.py -- --work WORK --out blend --blosm ADDONS
```
Sites, origin and radii are set in `frame.py`. Layout rules (stall size, buffers) are in `layouts.py` → `DESIGN`; per-site search rules are in `search()` there.

## Credits
- USGS 3DEP lidar / DEM, NHD and National Structures: public domain.
- Overture Maps Foundation / © OpenStreetMap contributors: ODbL.
- Google Photorealistic 3D Tiles (if imported): © Google; attribution is required in any render.
