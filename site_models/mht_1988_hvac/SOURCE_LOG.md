# Source log: MHT #1988 terminal model (checked 2026-10-22)

- **USED** means the data was downloaded from the source and is in the model.
- **NOT USED** means it was deliberately left out, with the reason given.
- Every download ran from the cloud build container through its proxy. The S3 buckets below all answered.

## Data in the model

| Layer | Source (exact) | Status 2026-10-22 | Data date | Accuracy / check |
|---|---|---|---|---|
| Terrain 1 m | USGS 3DEP 1 m DEM, `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/NH_Coastal_2019_B19/TIFF/USGS_1M_19_x30y476_NH_Coastal_2019_B19.tif` (detail) and `…x29y476…` (overview) | **USED** (S3 range reads); 0 empty cells in the detail area | Flown 2019–2020 | QL2 spec ≤ 10 cm RMSEz. Own check: lidar ground vs DEM median 0.2 cm, RMS 2.1 cm over 200,000 points; best horizontal shift (0, 0) m |
| Lidar points | USGS 3DEP EPT `https://usgs-lidar-public.s3.amazonaws.com/NH_Coastal_2_2019/` | **USED**: 14,112,264 points in the detail area, 15.2 pts/m² | 2019–2020 | Classes present: 1 (unclassified), 2 (ground), 7, 17, 18. Buildings, equipment and trees split by footprints, return count and roof fitting. NH_Coastal_1_2019 also covers MHT; the pipeline takes the first project in the config list that returns points. |
| Buildings, roads, airfield land use, places | Overture Maps release **2026-10-21.0** (`overturemaps-us-west-2` S3; OSM-derived; buildings also Microsoft ML) | **USED** | 2026-10-21 | OSM traces. Footprint vs lidar best shift (0.5, −1.0) m gained only 1.4 % roof points, so **not applied** (rule: apply only if ≥ 0.5 m and > 2 % gain). |
| Pedestrian bridge outline | 2019 lidar (no OSM / Overture footprint exists) | **USED** | 2019 | Outline from elevated lidar cells; roof from single returns; underside not visible |
| Water | USGS NHD HR HU8 01070006 GPKG `https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHD/HU8/GPKG/NHD_H_01070006_HU8_GPKG.zip` | **USED** (context only: Cohas Brook, Little Cohas Brook, Merrimack River, Pine Island Pond) | Static (NHD retired 2023-10-01) | 1:24k or better |
| Landmark check | USGS National Structures `https://prd-tnm.s3.amazonaws.com/StagedProducts/Struct/GPKG/STRUCT_New_Hampshire_State_GPKG.zip` (Last-Modified 2026-03-03) | **USED** for the centre check. **It has no terminal point.** Its only airport feature is the ARFF fire station, 402 Kelly Ave. | per feature (station loaded 2019-04-10) | See README "Centre check" |
| Google 3D Tiles | Map Tiles API via Blosm | **NOT USED**: only if Edward sets the key in Blender's preferences himself | live | Visual only; never measured |
| Orthophoto, parcels, FEMA, wetlands | GRANIT, NH Parcel Mosaic, FEMA NFHL, NWI | **NOT USED** tonight: not needed for the route check | | Collections exist empty; load with the tools in the .blend |
| Drone capture | n/a | **NOT USED**: MHT is controlled airspace; nothing in this model assumes a flight | | |

## Removed on purpose (security)

The prepare step drops security items before anything is written, so no later output can carry them (`job_config.py` → `REDACT`):

| Removed | Count |
|---|---|
| Overture infrastructure features of class gate, barrier, fence, camera, surveillance, lift gate, bollard, and aeroway gate / jet bridge / holding or parking position | 104 |
| Places and structures whose name or address mentions a gate, security, TSA, checkpoint, SIDA, police, camera, CCTV, badge, customs or screening | 10 |

The crane-staging page shows a ramp pad only. Contractor access routes, gate numbers and restricted-area boundaries are not drawn or described anywhere in the model, the viewer or these docs.

## Tools

| Tool | Source | Status |
|---|---|---|
| Blender | 4.5 LTS (`bpy` 4.5.15 wheel used for the build) | OK |
| three.js | r147 from `cdn.jsdelivr.net` (viewer) | Loads in a normal browser. The build container cannot reach jsDelivr, so the headless test used the same r147 files from the npm registry. |
