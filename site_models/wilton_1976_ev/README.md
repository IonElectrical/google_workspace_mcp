# Wilton NH job #1976 – 3D site models for RANH Level 2 chargers

Three Blender files, one per candidate site, built at real-world scale around a 400 m × 400 m
box (±200 m / ±656 ft) centred on each site:

| File | Site | Centre (lat, lon) |
|---|---|---|
| `blend/Wilton1976_Site1_PoliceLot.blend` | Police station lot, 7 Burns Hill Rd | 42.84485, -71.73967 |
| `blend/Wilton1976_Site2_MainSt.blend` | Main St curbside by Stony Brook / library (7 Forest Rd) | 42.84532, -71.73847 |
| `blend/Wilton1976_Site3_MunicipalLot.blend` | Municipal lot, SE corner Main St & Burns Hill Rd (near 42 Main St) | 42.84448, -71.73830 |

Each file already contains a measurable base model built from free public data (no Google key needed),
and is set up so that the Google Photorealistic 3D Tiles drop in on top of it with one click.
Previews are in `blend/previews/`.

## Which tool, and what key

**Use Blosm (free base version).** It is the add-on that imports Google Photorealistic 3D Tiles
(the 3D mesh you see in Google Earth / Maps) straight into Blender for a lat/lon box. You pick the
box on a map ("select" button), paste it, choose the level of detail and click import.

**BlenderGIS is not needed.** It does basemaps, GeoTIFF/DEM terrain and shapefiles, but it cannot
import Google's 3D Tiles; its Google basemap option uses unofficial tile URLs (against Google's terms);
and its built-in terrain (SRTM, ~30 m) needs a separate OpenTopography key. These files already
have 1 m lidar terrain, so BlenderGIS adds nothing here.

**Key:** a Google Maps Platform API key on a Google Cloud project with **billing enabled** and the
**Map Tiles API** turned on. Photorealistic 3D Tiles are billed per *root tileset request*, and one
Blosm import = one root request. Google lists 1,000 free per month, then $6 per 1,000
([pricing](https://developers.google.com/maps/billing-and-pricing/pricing)), so this job is
effectively free. Check the live pricing page and set a budget alert anyway.

The key lives only in Blender's add-on preferences on your Mac. Blosm does not write it into
.blend files, and the files in this folder contain no key, so you can share them.

## Step-by-step on your Mac

### 1. Install Blender 4.5 LTS
1. Go to <https://www.blender.org/download/lts/4-5/> and download **macOS – Apple Silicon**
   (or **Intel** on an older Mac).
2. Open the .dmg and drag Blender into Applications. Start it.
3. On the first-run screen, keep the defaults. If it asks about **online access**, choose
   **Allow**. You can also turn it on later in Edit → Preferences → System → Network.

Why 4.5 LTS rather than 5.x: Blosm 2.7 declares Blender 4.5. Blender 5.1+ runs Python 3.13, which no
longer ships the `distutils` module that Blosm imports. Tested with the Blender 5.2 Python module
build, Blosm only enabled after adding a `distutils` stand-in; on 4.5 it loaded cleanly. If you
already have 5.x and Blosm enables without an error, it is fine to use. The model files open in 4.5
and newer.

### 2. Get the Google key (about 10 minutes)
1. Go to <https://console.cloud.google.com/> and sign in with the Ion Electrical Google account.
2. Use the project picker at the top, choose **New Project**, name it `Ion Electrical Maps`, and click Create.
3. Go to **Billing** and link a billing account. A card is required, even for free usage.
4. Go to **APIs & Services → Library**, search **Map Tiles API**, open it and click **Enable**.
5. Go to **APIs & Services → Credentials → + Create credentials → API key** and copy it.
6. Click the key to edit it:
   - **API restrictions → Restrict key →** tick **Map Tiles API** only. Click **Save**.
   - Leave **Application restrictions = None**. Website/IP restrictions block Blender's
     requests, and Blosm's own docs say not to restrict the key. If an import ever fails with a
     permission error, remove the API restriction too.
7. Optional: **Billing → Budgets & alerts →** add a budget of $10 with email alerts.
8. Don't email or text the key, and don't type it into the .blend notes. It goes in one place only, in step 3.6 below.

### 3. Install the Blosm add-on
1. Open <https://prochitecture.gumroad.com/l/blender-osm>. Enter **0** as the price (or pay to
   support the author), then download the zip, e.g. `blosm_2.7.x.zip`.
   - Safari may unzip it automatically. If you end up with a folder instead of a .zip,
     right-click the folder → **Compress**, or re-download with right-click → *Download Linked File*.
2. In Blender, go to **Edit → Preferences → Add-ons**.
3. Click the **⌄** menu at the top-right of the Add-ons list → **Install from Disk…** → pick the zip
   (don't unpack it) → **Install from Disk**.
4. Tick the checkbox next to **Blosm** to enable it, then click the ▸ arrow to expand its settings.
5. Under **"Directory to store downloaded OpenStreetMap and terrain files"**, click the folder icon
   and pick or create `Documents/Blosm data`. Untick **Relative Path** in the file browser.
6. **Google 3D Tiles Key:** click in the field and press **⌘V** to paste the key. The "Get it!" button
   next to the field only opens Google's how-to page.
7. Preferences are saved automatically. If they aren't, use **☰ (bottom-left) → Save Preferences**.
8. Check that **glTF 2.0 format** is enabled in the same Add-ons list. It is built in and on by default,
   and Blosm needs it.

### 4. Import Google 3D Tiles into each site file
Do this for each of the three .blend files:

1. Double-click `Wilton1976_Site1_PoliceLot.blend` to open it.
2. Move the mouse over the 3D view. If the right sidebar is hidden, press **N**. Click the **Blosm** tab.
3. The panel is already filled in:
   - **Extent:** the site's box (the panel shows 4 decimals).
   - The dropdown next to **import** reads **3D Tiles**, with **Source: Google** below it.
   - **Level of details:** *buildings with details*.
   - **Join 3D Tiles objects** and **Relative to initial import** are both ticked. Keep "Relative to
     initial import" ticked; it is what lands the tiles on this model.
   - If the extent fields are blank, copy the line for that site from the table below and click **paste**.
4. Click **import**. It takes 1–5 minutes; Blender is busy until it finishes. A new
   **Google 3D Tiles** collection appears.
5. Click the **Scripting** tab at the top of the window. In the text editor, use the text dropdown
   to pick **align_google_tiles.py**, then click **▶ Run Script**. A popup reports how far the
   Google mesh was moved (normally under 1 m vertically). Go back to the **Layout** tab.
6. Save with **⌘S**, or use **File → Save As** with a new name if you want to keep a version without the tiles.

| Site | String for the Blosm **paste** button |
|---|---|
| Site 1 – Police lot | `-71.742120,42.843050,-71.737220,42.846650` |
| Site 2 – Main St | `-71.740920,42.843520,-71.736020,42.847120` |
| Site 3 – Municipal lot | `-71.740750,42.842680,-71.735850,42.846280` |

*Level of detail:* "buildings with details" (lod5) is right for proposal views of a small town. Use
"separate buildings" (lod4) for a faster first look. The top level is Pro-only.

*Any other spot later:* in the Blosm panel click **select**. A map opens in your browser; draw a box,
copy, then back in Blender click **paste** and **import**. Or run `python3 sites.py LAT LON [RADIUS_M]`
to get a paste string for a point copied from Google Maps.

### 5. Using the model for layout, trenching and proposal views
- **Outliner collections** (top-right) – click the eye icons to show/hide:
  - *Open data base*: terrain, lidar buildings and trees, street labels.
  - *Site pins + rings*: orange = this site, blue = the other two, 50/100/200 ft rings, yellow
    box = import extent.
  - *Planning – EDIT ME*: the example kit.
  - *Google 3D Tiles*: after import.
- **Charger + stalls:** click the **CHARGER KIT** empty, press **G** to move and **R** to rotate. The
  example dual-port pedestal on a 30×24 in pad, plus two 9×18 ft stalls, follow it. Use **Shift+D**
  to duplicate for more spaces.
- **Service point:** move the yellow **SERVICE POINT** box to the panel or transformer you found on site.
- **Trench routes:** select **TRENCH route example**, press **Tab**, move points with **G**, add
  points with **E**, then press **Tab** again. Turn on snapping (magnet icon, *Snap to: Face Project*)
  so the route follows the ground. The red tube shows the trench, and the label shows its length in
  feet, updating live. **Shift+D** makes another route. The **Measure** tool (ruler in the left
  toolbar) gives point-to-point distances in feet.
- **Proposal views:** the cameras are *Aerial from SE*, *Aerial from NW*, *Plan view* (orthographic,
  150 m wide) and *Street level*. To use one, right-click it in the Outliner → **Set Active Camera**,
  then press **F12** to render. To re-aim, move the **AIM** empties.
  - No numpad on a Mac keyboard? Turn on Preferences → Input → **Emulate Numpad**, or use View → Cameras.
- **Attribution:** any render with the Google mesh must show **Google** plus the data providers listed
  in the **Copyright** panel that appears in the Blosm tab after the import. Lidar and Overture data credits are in each file's
  **README_SITE** text (Scripting tab).

## What's in the base model, and how good it is

| Layer | Source | Notes |
|---|---|---|
| Terrain | USGS 3DEP 1 m DEM, NH_Coastal 2019 lidar project | Relative accuracy about 10 cm. Absolute height ±1 m (see below). |
| Ground texture | 2019 lidar intensity + Overture roads/parking/water | Paint striping in the police lot is visible. Not a photo. |
| Buildings | Overture Maps footprints (Sept 2026) + 2019 lidar roofs | Roof shape from lidar points. **Purple** = no 2019 lidar on that footprint (newer building, or height estimated). |
| Trees | Tree tops found in the 2019 lidar canopy | Height and crown size are real; species/shape are generic (about 30% drawn as conifers). |
| Labels | Overture (OpenStreetMap-based) street names and landmarks | Landmark labels show in the viewport only, not in renders. |

**Utilities are not in any open dataset here.** No poles, laterals, panels or transformers are mapped
around these sites (Overture only has a regional transmission line and long-haul telecom cables). Place
the service point from today's site visit.

**Coordinate check against mapped landmarks:**
- **Site 1:** 23 m from the "Wilton Police Department" point. The pin sits on the police building,
  in the middle of its lot.
- **Site 2:** about 9 m from the "Wilton Public Library" point; the pin is on the library building.
  The nearest curbs are **Forest Rd** (36 m west, the street along Stony Brook) and Gregg St (36 m
  east). **Main St is about 80 m away**, near where it crosses the brook and meets Burns Hill Rd.
  If "Main St curbside" means a specific spot, confirm it on site. The example charger kit was
  placed on the Forest Rd side.
- **Site 3:** about 21 m SE of the Main St × Burns Hill Rd intersection, 4.6 m from the Main St
  centreline (on the pavement). Town Hall Theatre / Town Clerk are about 110–120 m SSE, and a
  "Town of Wilton" office point is about 48 m SSE.
- Once the exact spots are confirmed, drag the pins and the charger kit. Moves within about 150 m stay
  inside the imported box.

## Technical notes

- Every layer is built in the exact local frame Blosm uses for Google 3D Tiles: origin at the site
  centre, X east, Y north, Z ≈ height above the WGS84 ellipsoid. Blosm computes its origin in 32-bit
  floats, which shifts imported tiles by a constant 28–36 cm (depending on the site). The build applies
  the same shift.
  `verify_alignment.py` checks this end to end. It feeds marker tiles at known WGS84 positions through
  Blosm's real import into each file. Result: **0.00 cm** error at all three pins.
- Lidar heights are NAVD88, converted to ellipsoid with an approximate geoid separation of −28.4 m
  (±1 m). `align_google_tiles.py` removes whatever is left once the Google mesh is in. Height
  differences within the model (grades, trench depth vs. ground) are not affected.
- Blosm's "up" axis is the geocentric radial direction, about 0.19° off true vertical at this
  latitude. Distances and areas are unaffected. Absolute slopes read off the model can be off by up
  to 0.3%.
- Google's Map Tiles policies require attribution and limit storing tile content. The imported mesh
  lives inside your .blend, so keep those files internal and put rendered images (with attribution)
  in proposals. The open-data layers carry no such restriction (USGS: public domain; Overture/OSM:
  ODbL, credit "© OpenStreetMap contributors, Overture Maps Foundation").

## Rebuilding (only needed for changes or new sites nearby)

```bash
# Python 3.11 with: numpy scipy shapely pyproj pyarrow laspy lazrs rasterio requests pillow
python prepare_data.py --cache ~/wilton_cache --work ~/wilton_work      # ~2 min, ~150 MB download
# Blender 4.5 (or `pip install bpy==4.5.14 "numpy<2"`), with the Blosm folder's parent as --blosm
ADDONS="$HOME/Library/Application Support/Blender/4.5/scripts/addons"   # folder that contains blosm/
blender -b --factory-startup -P build_site_blend.py -- --work ~/wilton_work --out blend --blosm "$ADDONS" [--previews]
python verify_alignment.py blend/Wilton1976_Site1_PoliceLot.blend ~/wilton_work "$ADDONS"   # bpy wheel
```
Site list and box size are in `sites.py`. The lidar project (NH_Coastal_2019) and DEM tile
(x27y475) in `prepare_data.py` cover the Wilton village area only. For another town, the Blosm
"select → paste → import" route works anywhere.

Optional batch Google import for all three files without clicking. The key is read from the macOS
Keychain, never written to a file, and masked in any output:
```bash
security add-generic-password -a "$USER" -s google-map-tiles -w     # prompts for the key once
/Applications/Blender.app/Contents/MacOS/Blender -b -P import_google_tiles.py -- --blends "blend/*.blend"
```
