# Location build-out: true-scale 3D site model in Blender + web walkthrough

Source of truth: the Notion skill page of the same name
(https://app.notion.com/p/401456145533813f8f37c41c636311d3). This copy is for Claude Code
sessions that cannot reach Notion. If the two differ, follow Notion and update this file.

Use this when Ion Electrical needs a new project location built out as a true-scale,
georeferenced 3D model in Blender, with measured site layouts, a missing-measurements list, a
source log, and a browser walkthrough the client or Town can open. It repeats the method used for
Wilton NH job #1976 (`site_models/wilton_1976_ev/`).

Does not apply to: interior or home digital twins, pricing or quotes, or anything that must be
survey-grade. The model supports planning. It is not a survey and never replaces Dig Safe (811)
or the utility's records.

## How to start

Paste this into Claude Code and fill in the intake:

```
Build a new location model using site_models/LOCATION_BUILD_PLAYBOOK.md
(Notion skill "Location build-out: true-scale 3D site model in Blender + web walkthrough").

Job intake:
- Job: <JobTread #> / <client> / <project name>
- Purpose: <EV charging | solar | service upgrade | other>
- Center point: <lat, lon>   Overview radius: <default 2 mi>   Detail radius per site: <default 400 m>
- Sites (one line each): <key> | <name> | <address> | <lat, lon> | <coordinate source> | <type: lot / street-side / roof / grass> | <what to lay out> | <notes and constraints>
- Known facts from the site walk: <transformers, pole tags, meters, exits, snow storage, deeds, hazards>
- Captures available: <CompanyCam timeline, Polycam scans, photos>
- Funding or program rules: <e.g. ports per site, ADA, operating term>
- Deliverables: <default: all of section 'Outputs'>
- Deadline: <date or 'on site now'>
```

## Inputs

| Input | Required? | If missing |
|---|---|---|
| Center point and site list with coordinates | Required | Ask for it. Nothing can start without it. |
| Site type and what to lay out | Needed per site | Default to 2 dual-port pedestals, 18 ft × 9 ft stalls, 1 ADA van stall with 8 ft aisle, 3 ft plow buffer, 24 ft drive aisle, and say so. |
| Site-walk facts | Optional | Leave as placeholders and list on the missing-measurements list. |
| Captures (Polycam, CompanyCam) | Optional | Ship the import and registration tools so they can be added later. |
| Google Maps Platform key (Map Tiles API) | Optional | Skip Google tiles. Never ask for the key in chat. |

## Fixed rules

- **No guessing.** Every number is either measured from a named dataset, or labeled
  **CALCULATED ESTIMATE** with its method and source, or put on the missing-measurements list.
- **Coordinates.** Use NAD83 / UTM for the site's zone (EPSG:269xx) or the state plane, and say
  which. Heights are NAVD88. Blender: 1 unit = 1 m, display in feet. Record the scene origin offset
  (E0, N0 rounded to 1 km near the center) in the file and the README.
- **Precedence.** LiDAR or site measurement > parcel GIS > orthophoto digitizing > OSM / Overture >
  Google 3D Tiles (visual only).
- **Every layer** carries a source, date and accuracy note.
- **Google 3D Tiles** are visual only: never measured, never committed to git, imported only in a
  working copy. The key lives only in Blender's add-on preferences or an environment secret.
- **Never** put an API key or token in chat or in any file. No pricing in shared outputs. No
  customer account or meter numbers, or anything an owner said in confidence, in shared files.
- **Verify every site coordinate** against landmarks (USGS structures, Overture places, address
  points). Report the distance and flag conflicts. Never move a site silently.

## Reference implementation

- Folder `site_models/wilton_1976_ev/`. The current pipeline is in `v2/`; `v2` imports helpers
  from the v1 scripts one folder up. Read `v2/README_v2.md` first.
- Example outputs to match: `v2/docs/SITE_LAYOUTS.md`, `v2/docs/MILL_ROOF.md`,
  `v2/MISSING_MEASUREMENTS.md`, `v2/SOURCE_LOG.md`, `v2/NEXT_PHOTO_LIST.md`,
  `v2/utilities/UTILITY_ITEMS.csv`, `v2/web/Wilton_Downtown_Viewer.html`.

| Script | Role | Wilton-specific parts to replace |
|---|---|---|
| `frame.py` | Sites, origin, UTM / state plane math (no pyproj inside Blender) | `SITES`, `CENTER`, radii, UTM zone, `E0`/`N0` |
| `prepare_downtown.py` | Downloads and processes DEM, lidar, Overture, NHD, USGS structures; registration checks | DEM project and tile list, lidar (EPT) project, NHD watershed file, structures state file |
| `layouts.py` | Charger layouts, slopes, trenches, overlays | Per-site rules in `search()` and the site overlays (deed area, police exit, hazard, flood rings, bridge, dike) |
| `mill_roof.py` | Roof planes, setbacks, solar estimate | Which buildings to analyze, claim comparison |
| `build_downtown_v2.py` | Builds the .blend | Collection and site names, labels |
| `export_web.py`, `web/viewer_template.html`, `web/tour.json` | Browser viewer with walk, drive/fly, measure, narrated tour | Site titles, addresses, tour stops and narration |
| Tools embedded in the .blend | `import_gis_layer.py`, `drape_orthophoto.py`, `import_field_points.py`, `register_capture.py`, `google_tiles_to_utm.py` | None (CRS handling is generic) |

On the first new job, move the Wilton-specific parts into a per-job config file (sites, origin,
datasets, layout rules, tour) so later jobs only change config. Keep the Wilton folder unchanged.

## Steps

1. **Set up.** Work on a new branch `claude/<job-slug>-3d`. Create `site_models/<job-slug>/`.
   Python 3.11 with numpy, scipy, shapely, pyproj, pyarrow, laspy, lazrs, rasterio, requests,
   pillow, pyogrio. Blender work uses Blender 4.5 LTS or the `bpy` 4.5 wheel in a separate venv
   with `numpy<2`.
2. **Frame.** Set the sites, center, radii, UTM zone and origin. Check the transforms against
   pyproj (expect under 1 mm).
3. **Find data that covers the area.** Record each source's URL, date and status in the source log
   as you go.
   - USGS 3DEP 1 m DEM from the `prd-tnm` S3 bucket (`StagedProducts/Elevation/1m/Projects/`).
     Tiles are named like `USGS_1M_19_x27y475_<project>.tif` on a 10 km UTM grid; Wilton used
     x27y475 and x27y476. Read each tile's bounds to confirm coverage.
   - USGS lidar points from the `usgs-lidar-public` S3 bucket (EPT, Web Mercator bounds in each
     project's `ept.json`). Pick the project whose bounds contain the sites **and** that returns
     points for a small test query. For Wilton, NH_Coastal_2_2019 worked and NH_Coastal_1_2019
     returned none.
   - Overture Maps, latest release (buildings, transportation, places, land use, infrastructure).
   - USGS NHD High Resolution HU8 GeoPackage for the watershed, and the USGS National Structures
     state GeoPackage.
4. **Prepare and check.** Run the prepare step. Check lidar ground vs DEM (Wilton: median 0.1 cm,
   RMS 5.6 cm) and the footprint-to-lidar shift (Wilton: 0.5 m E, −1.25 m N). Stop and report if
   lidar does not cover a site or the RMS is over 0.15 m.
5. **Check the site points** against landmarks and write the conflicts into the README findings.
6. **Lay out each site** from the intake: paved area from lidar intensity, clearances to
   buildings, water and footways, ADA slope limit 2.08 % for the van stall and aisle. Trenches
   start from a labeled placeholder until the real power source is tagged. Add the overlays the
   intake calls for (keep-clear zones, undelineated deed areas shaded whole, hazards,
   flood-distance rings, bridge corridors). Pick water features by proximity to the site, not by
   size.
7. **Roofs**, when a roof matters: fit planes to lidar single returns, apply 3 ft and 4 ft
   setbacks, and give solar as a CALCULATED ESTIMATE at a stated W/m². Compare against any claimed
   floor areas.
8. **Build the .blend** with the collections listed below. Pack textures with relative paths,
   embed the docs and tools as text blocks, set the scene georeference keys, and preset the Blosm
   extent.
9. **Write the docs**: README (frame, headline findings, site summary table, Mac steps, accuracy
   table, rebuild commands), site layouts, roof table, missing measurements (with who can supply
   each), source log, next photo list, utility items CSV.
10. **Viewer**: export the web viewer (keep it under 16 MB), write `tour.json` stops and narration
    from measured numbers only, and test it in headless Chromium for page errors and logic.
    Headless rendering is about 1 frame per second, so judge logic, not speed. Publish it as a
    private page and give the link.
11. **Commit and push**: run `ruff format` and `ruff check`, keep the .blend under 100 MB (GitHub
    warns over 50 MB), and never commit a file with Google tiles in it.

## Outputs

- `<Town><Job>_<Area>_v1.blend` with these collections: 00 Terrain · 01 Orthophoto drape ·
  02 Buildings (detail and overview) · 03 Trees · 04 Water (NHD + traced features) · 05 Flood
  zones · 06 Wetlands · 07 Parcels · 08 Roads + sidewalks · 09 Utilities · 10+ one per site · Roof
  planes · 20 Cameras + lights · 30 Google 3D Tiles (optional). Empty layers are named with the
  tool that fills them.
- Per site: stalls, ADA stall and aisle, pedestals on pads, plow buffer, trench routes with
  lengths in ft (CALCULATED ESTIMATE), power placeholder, overlays, a facts label, and eye-level
  and aerial cameras.
- Docs: README, SITE_LAYOUTS, roof table (if any), MISSING_MEASUREMENTS, SOURCE_LOG,
  NEXT_PHOTO_LIST, UTILITY_ITEMS.csv.
- Web viewer HTML with the narrated tour, plus its published link.

## Completion checks

- Every number in the docs traces to a dataset or is labeled CALCULATED ESTIMATE with its method.
- The site-coordinate check is in the README, with conflicts called out.
- The missing list covers at least: service size, voltage and phase per site; transformer kVA and
  locations; wheel-measured trench lengths; parcel lines; flood zone and BFE; wetlands;
  orthophoto; utilities; roof structure.
- The viewer loads with no page errors and is under 16 MB.
- Everything is committed and pushed. The final message lists findings, conflicts, blocked
  sources and links.

## When something is missing or blocked

- **Host blocked from a cloud session.** USGS and Overture S3 buckets usually work. State GIS
  clearinghouses, FEMA, town sites and Overpass are often blocked. Write the Mac download steps
  and ship the import tools, or ask the user to add the hosts in the environment's network
  settings.
- **No 1 m lidar coverage.** Say so, use the best available DEM, and mark building heights as not
  measured.
- **Site coordinate conflicts.** Lay out at the best-supported location, label it, and put the
  conflict on the missing list.
- **No Google key.** Skip the tiles. The model is complete without them.
- **Location outside the US.** The USGS sources do not apply. Stop and ask before choosing other
  data.

## Lessons from Wilton

- Blosm 2.7 needs Blender 4.5 LTS; Blender 5.1+ lacks Python's `distutils`. In headless `bpy`,
  exit with `os._exit(0)` or it hangs.
- Blosm computes its origin in 32-bit floats, a constant 28–36 cm shift. Convert imported tiles
  with `google_tiles_to_utm.py`, never by eye.
- Only ground was classified in the Wilton lidar. Split buildings from trees with footprints and
  single returns.
- The DEM's water surface is a height reference only. It is not a flood elevation.
- OSM footprints needed a small measured shift to sit on the lidar roofs.
- Pack the base64 data and densify lines adaptively to keep the viewer under 16 MB. The viewer
  uses three.js r147, the last release with the classic controls scripts.
- Run `ruff` before committing; CI checks it.

## Field capture to request

- Nameplates and tags (close-up, then a wide shot from about 20 ft showing a building corner or
  curb), with GPS on.
- Wheel readings along every trench path, with surface types.
- Cones at each proposed charger spot.
- Polycam scans with at least 4 named control points spread around each scan and one taped
  distance. Report the registration RMS in feet.
