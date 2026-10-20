# Source log: Wilton #1976 downtown model v2 (checked 2026-10-20)

How each source was checked:
- The build ran in a cloud container whose network policy only allows some hosts.
- **USED** means the data was downloaded and is in the model.
- **BLOCKED** means the container's proxy refused the host (HTTP 403 on CONNECT). The web-fetch tool also failed DNS for every host, including control sites. **This says nothing about whether the site is up**; open it on the Mac.
- **Index** means a search engine indexed the page recently. That does not prove it works today.
- GitHub was checked live through its API.

## Data in the model

| Layer | Source (exact) | Status 2026-10-20 | Data date | Accuracy |
|---|---|---|---|---|
| Terrain 1 m | USGS 3DEP 1 m DEM, `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/NH_Coastal_2019_B19/TIFF/USGS_1M_19_x27y475_…` and `…x27y476…` | **USED** (S3 range reads) | Flown fall 2019 / spring 2020 | Project NVA 7.6 cm at 95 % (USGS PRJ report, per search summary). Own check: lidar ground vs DEM median 0.1 cm, RMS 5.6 cm. |
| Lidar points | USGS 3DEP EPT `https://usgs-lidar-public.s3.amazonaws.com/NH_Coastal_2_2019/` (QL2) | **USED**: 4,448,332 points, 4.56 pts/m² | 2019–2020 | Only ground (class 2) is classified. Buildings and trees were split using footprints and return count. |
| Buildings, roads, footways, places | Overture Maps release 2026-09-23.1 (`overturemaps-us-west-2` S3; OSM-derived) | **USED** | 2026-09-23 | OSM traces. Footprints registered to the lidar with a measured shift of (0.5, −1.25) m. |
| Water | USGS NHD HR HU8 01070006 GPKG `https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHD/HU8/GPKG/NHD_H_01070006_HU8_GPKG.zip` | **USED** | Static: NHD was retired 2023-10-01 (3DHP is the successor) | 1:24k or better |
| Landmark check points | USGS National Structures `https://prd-tnm.s3.amazonaws.com/StagedProducts/Struct/GPKG/STRUCT_New_Hampshire_State_GPKG.zip` | **USED** | per feature | Used only to check site points |
| Google 3D Tiles | Map Tiles API via Blosm 2.7 (key on the Mac only) | Not imported here (no key in the container, by design) | live | **Visual only**; not measured |
| Add-ons | github.com/vvoovv/blosm (last push 2026-09-08); github.com/domlysz/BlenderGIS (last push 2025-12-20) | **OK** (GitHub API) | | |

## Links from the brief

The brief reports that these worked from Edward's side on 10/20: the National Map Downloader, the 2025 tax-map PDF, the zoning-maps page, the FEMA MSC, OSM / Overpass, Blosm and BlenderGIS. They were blocked only from the build container, so the Mac steps in README_v2 §5 use them directly.

| Link | Status 2026-10-20 | Replacement / note |
|---|---|---|
| granit.unh.edu | BLOCKED; index OK | Orthophoto (USGS NH 2021/22, 6-inch, 4-band, State Plane ft) is in the GRANIT Image Download Tool. The town zips are on `ftp.granit.unh.edu/GRANIT_Data/`. |
| nhgeodata.unh.edu | BLOCKED; index OK (datasets updated 2026) | Parcel Mosaic: `nhgeodata.unh.edu/nhgeodata/rest/services/CAD/ParcelMosiac/MapServer` |
| apps.nationalmap.gov/downloader | BLOCKED | The same USGS data was fetched directly from the `prd-tnm` S3 bucket |
| usgs.gov/3d-elevation-program | BLOCKED; index OK | — |
| coast.noaa.gov/dataviewer | BLOCKED | Not needed: USGS lidar was used directly |
| Town 2025 tax-map PDF (civiclive) | BLOCKED; no index hit | NRPC sheets: `nashuarpc.org/gis___mapping/tax_maps/wilton_tax_maps.php` (downtown = Map J) |
| wiltonnh.gov zoning maps page | BLOCKED; exact path not indexed | Parent page: `wiltonnh.gov/government/boards_and_committees/planning_board`; contact landuse@wiltonnh.gov |
| gis.vgsi.com/wiltonnh | Reported 404; BLOCKED here | **No Vision site found.** Use **NRPC MapGeo `nrpcnh.mapgeo.io`**, which carries Wilton CAMA data, or the "Assessor Database" link on `wiltonnh.gov/government/departments/assessor` (603-654-3299). Do **not** use `jeodonnell.com/cama/wilton` (Wilton, Maine). |
| msc.fema.gov | BLOCKED; index OK | County NFHL product ID `NFHL_33011C`. **FIRM effective 2009-09-25** (Wilton zoning Ch. 10, amended 2024-01-03, and FIRM index 33011CIND2A). Downtown panel number not verified. |
| hazards.fema.gov (NFHL) | BLOCKED | REST: `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer` |
| usgs.gov/national-hydrography | BLOCKED | NHD retired; data used from S3 (above) |
| NHDES WetlandsPermitViewer | BLOCKED; path not indexed (legacy) | Use the Wetlands Permit Planning Tool `nhdeswppt.unh.edu` or `www4.des.state.nh.us/lrmonestop/` |
| fws.gov NWI | BLOCKED; index OK | Download by HUC8 01070006: `fws.gov/program/national-wetlands-inventory/data-download` |
| openstreetmap.org / overpass-turbo.eu | BLOCKED | OSM content came through Overture 2026-09-23.1 |
| developers.google.com 3D Tiles | BLOCKED; index OK | Needs the Map Tiles API, billing and a key; attribution is required |

## Facts used, with source

| Fact | Source | Confidence |
|---|---|---|
| Mill claims 93,000 / 93,890 / 94,000 / 100,000 sq ft | Ledger-Transcript 2022-09-14; WRCRE listing; CityFeet/LoopNet; chillybears.com / Pidcock LinkedIn | Search excerpts, pages not opened |
| Mill = 6 parcels, 14.03 acres; bought 2022 by Wilton Mill Worx LLC | wrcre.com; Ledger-Transcript; Cabinet 2022 | Search excerpts |
| Cyanide vault next to the Police Dept (Abbott Trust Lot J-104-2) | NHBR / Concord Monitor 2022; Town "EPA Assessment Report" (Feb 2023) | Search excerpts. Location not mapped. |
| Wilton Falls Bldg = 6 Burns Hill Rd; gifted with "40 parking spaces" | Ledger-Transcript 2023-09-01 and 2025-05-02 | Deed location of the 40 spaces NOT FOUND |
| Souhegan pedestrian bridge Riverside Way ↔ Howard St | NRPC MPO minutes 2025-02-19; NRPC MTP list 2024 | Search excerpts |
| RANH: 80 %, $10k/port, $100k/municipality, first window closes 2026-11-15 | des.nh.gov RANH page (search summary) | 5-year term **not verified** |
| Street at the library = "Forest Road" | Overture/OSM | Brief says Main St; confirm |
| Riverwalk Phase 1 along the Stony Brook south bank by the police lot | wiltonnh.gov riverwalk pages | Search excerpts |

## To unblock this container next time
Add these hosts to the environment's allowed domains (Network access):
- granit.unh.edu, nhgeodata.unh.edu
- msc.fema.gov, hazards.fema.gov
- services6.arcgis.com, nrpcnh.mapgeo.io
- www.fws.gov, wiltonnh.gov

See <https://code.claude.com/docs/en/claude-code-on-the-web>.
