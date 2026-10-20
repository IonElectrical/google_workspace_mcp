# Missing measurements: Wilton #1976 (as of 2026-10-20, updated for brief v3)

Nothing on this list was guessed in the model. Each item is shown as a placeholder, a ring, an empty collection or a label, and stays so until it is measured.

**Who** is the person or source that can supply the item. **How to load it** is the tool (in the .blend Scripting tab) that puts the answer into the model.

## Power and utilities (needed for every trench and for the RANH budget)

| # | Missing | Site | Who / how to get it | How to load it |
|---|---|---|---|---|
| 1 | Service size (A), voltage, phase at the source panel or transformer | S1–S4 | Panel and meter nameplates (photo); Eversource or NHEC work order | Fill the `notes` column in `field_points.csv` |
| 2 | Transformer kVA and spare capacity. Mill pad-mount: Howard, serial 2211802515, kVA plate unreadable (INFERRED on the order of 1,000 kVA from weight; see `utilities/UTILITY_ITEMS.csv`). The three mill pole cans and the S1 pad-mount: kVA unknown. | S1, S4 | Eversource (give them the serial number); kVA stencils on the cans; S1 nameplate photo | `import_field_points.py` |
| 3 | Pole and transformer positions. Pole tags "5" (PSNH) and "Wilton Telco 3" were read, but none is located, and it is unconfirmed whether tag 5 is on the three-can pole. | S4 (S2 street poles) | CompanyCam GPS through the API, then drag onto the pole base in the lidar; a wide shot tying tag 5 to its pole | `import_field_points.py` |
| 4 | Real trench and bore routes and lengths | all | Walk the route with a measuring wheel; re-route the `TRENCH` curves after #3 | Edit the curves; the length label updates |
| 5 | Existing underground (water, sewer, gas, telecom, storm) | all | Dig Safe ticket (811) before design; Town DPW / water works records | `import_field_points.py`, or digitise |
| 6 | Meter / panel location and spare breaker spaces | S1, S3, S4 | Photo of the panel schedule | CSV notes |

## Land, rights and layout

| # | Missing | Site | Who / how to get it | How to load it |
|---|---|---|---|---|
| 7 | Location of the **40 deeded spaces** (Wilton Falls Bldg, 6 Burns Hill Rd). The model shades the whole paved lot as "deed undelineated", 24,811 sq ft. | S1 | Deed / plan at the Hillsborough County Registry; Nick Germain | Digitise as GeoJSON, then `import_gis_layer.py` |
| 8 | **Cyanide vault** location and cap extent (Abbott Trust Lot J-104-2) | S1 | Town (EPA 2023 assessment report and its figures); NHDES | `import_field_points.py` (type `other`) |
| 9 | Police exit route and the keep-clear width the department needs. The model's zone is **assumed** from the brief. | S1 | Police chief | Move the overlay |
| 10 | Parcel lines: 21 Mill St, the **13-ft strip** and its owner, J-104-1/-2, J-105, J-61 (Proctor lot), Waterworks lot | S1, S2, S4 | NRPC MapGeo / NH Parcel Mosaic (see README §5); Assessor 603-654-3299; deeds | `import_gis_layer.py` |
| 11 | S2 lot boundary. The brief says the SE corner of Main / Burns Hill; the data shows paving **SW** of it, and Town Hall (USGS) is 1,284 ft from the brief point. | S2 | Jennifer / Town; site walk | Move the S2 layout |
| 12 | S3 street name (OSM: Forest Rd; brief: Main St) and the curb line (from lidar intensity; ±1.5 ft) | S3 | Site walk; Town | Field points on the curb |
| 13 | Snow-storage areas and plow routes at each lot; S2 "snow-storage corner" | all | DPW / plow contractor | Digitise, then `import_gis_layer.py` |
| 14 | Riverwalk future phases and bench / landing positions; pedestrian bridge **Plan A / Plan B** landings | S1, S4 | Economic Development team; NRPC; the 2018/2019 GPI design plans | Field points, or digitise |
| 15 | Route 101 grass strip and Waterworks lot pins | S4 | Ted Pidcock; survey | Field points |
| 16 | Pedestal model, footprint, cable entry; stall width (9 ft assumed); ADA layout confirmation | all | Ion Electrical design / owner choice | Edit the `DESIGN` dict in `layouts.py` |

## Water and flood

| # | Missing | Site | Who / how to get it | How to load it |
|---|---|---|---|---|
| 17 | **FEMA zone (AE / floodway) and BFE at each layout.** FIRM effective 2009-09-25; panel numbers not verified. | all (S2 brief: AE/floodway 150–250 ft SW) | FEMA MSC → NFHL_33011C (README §5) | `import_gis_layer.py`: S_FLD_HAZ_AR, S_BFE |
| 18 | FIS vertical datum (NAVD88 or NGVD29) | all | FIS report text (MSC) | Note in the file |
| 19 | Sluiceway location (not in NHD) | S4 | Ted Pidcock; site walk; orthophoto | Digitise, then `import_gis_layer.py` |
| 20 | Dike: confirm it is the Waterworks dike. The model's trace is a **CALCULATED ESTIMATE**: crest 357.6–364.3 ft, median 3.7 ft above the pond. | S4 | Site walk / owner | — |
| 21 | Wetland boundaries (NWI / NHDES) and Shoreland setbacks for Souhegan / Stony Brook | S2, S3, S4 | NWI HU8 01070006; NHDES WPPT | `import_gis_layer.py` |

## Buildings and imagery

| # | Missing | Site | Who / how to get it | How to load it |
|---|---|---|---|---|
| 22 | Mill roof structure, age, membrane, load capacity; parapets or equipment under ~1.5 ft | S4 | Roof walk; structural engineer; owner records | — |
| 23 | Mill floor area by level. Only the footprint (46,782 sq ft) is measured; 93–100k is claimed. | S4 | Owner plans / assessor card | — |
| 24 | Orthophoto (true photo texture) | all | GRANIT 2021/22 6-inch tiles | `drape_orthophoto.py` |
| 25 | Changes since the 2019 lidar (new buildings, repaving, the 2023 gazebo) | all | Polycam / site photos | `register_capture.py` |
| 26 | ~1 ft accuracy at the layouts (the lidar model is ~1.5–3 ft for edges) | all | Polycam with 4+ control points; **record the RMS residual** | `register_capture.py` |

## Program

| # | Missing | Who |
|---|---|---|
| 27 | RANH 5-year operating commitment (not on the NHDES page); the minimum of 2 ports per project (reported only locally) | RANH RFP / NHDES |
| 28 | Which sites the Town wants in the first application (the $100k cap is 10 ports at $10k each) | Select Board / Jennifer |

## Added from brief v3 (CompanyCam findings, 10/20 afternoon)

| # | Missing | Site | Who / how to get it | How to load it |
|---|---|---|---|---|
| 29 | Mill service voltage (208Y/120 or 480Y/277) and ampacity. The meter (Form 9S, 4-wire wye, transformer-rated) makes 3-phase LIKELY (INFERRED), but the 120–480V meter rating doesn't fix the voltage. | S4 | Eversource; the main disconnect nameplate | CSV notes |
| 30 | Positions for every CompanyCam photo. The public timeline shows neither GPS nor time. | all | CompanyCam API (read-only token), or an export with the original files | Photo layer (CSV / GeoJSON) |
| 31 | Pad-mount clearance zones (Eversource label: 10 ft door side, 4 ft other sides) can't be drawn until the pad-mounts are located | S1, S4 | #3 and #30 | Automatic once located |
| 32 | Overhead lines at the charger spots (height and route) | all | Look-up photos and a laser height; 2019 lidar wire candidates (INFERRED) | Utility layer |
| 33 | Hydro channel sign text | S4 | A readable photo | Label |
| 34 | Location of "Building #15" (street not confirmed) | ? | Street sign / house number photo | Control point |
| 35 | Wheel and tape readings at each charger spot and along each trench path, with surface types for restoration | all | Next visit (photo list items 6–7) | Replaces the CALCULATED ESTIMATE trench lengths |
| 36 | NEC edition in force for the permit. Sources point to the **2023 NEC**, but they disagree on the effective date (7/1/2025 vs 7/1/2026, transition to 1/1/2027). | all | Wilton building inspector | Trench / conduit tool setting |
| 37 | Souhegan designated-river reach through Wilton (RSA 483) and whether NH Shoreland (RSA 483-B, 250 ft protected shoreland) applies to the Souhegan and Stony Brook reaches. All four layouts are within 250 ft of mapped water (CALCULATED from the NHD edge; the legal line is the reference line / high-water mark). | all | NHDES Rivers and Shoreland programs; SoRLAC | Environmental layer |

