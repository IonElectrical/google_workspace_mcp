# Missing measurements: MHT #1988 (as of 2026-10-22)

Nothing on this list was guessed in the model. Each item shows as a placeholder, an empty collection, a "NOT MEASURED" cell or a labelled candidate until it is measured. **Who** is the person or source that can supply it. **How to load it** is the tool in the .blend Scripting tab that puts the answer into the model.

## Routes (the reason the model exists)

| # | Missing | Units | Who / how to get it | How to load it |
|---|---|---|---|---|
| 1 | **Electrical room locations**: #1076, #1077 (SWBD E), #103 (M1), #105 (M3), #204 (M2). Interior, so not in any public dataset. Shown only as a labelled placeholder row. | all | Polycam scan of each room with 4 control points; or the airport's floor plans through AmeriTech | `register_capture.py` (scan); `import_field_points.py` (points) |
| 2 | **Horizontal run** from each room to its riser | all | Wheel or tape (photo list item 1) | Write into `ROUTE_LENGTHS.md` as MEASURED |
| 3 | **Floor levels** (ground-floor slab vs grade; bridge deck / room #204 floor). Risers use slab = grade, an assumption. For #204, only an upper bound (≤ 14.2 ft) is possible. | all | Tape floor to floor at each riser; airport drawings | Edit the riser in `ROUTE_LENGTHS.md` |
| 4 | **Roof penetration** point per circuit, so the roof run | all | Photo list item 3d | `import_field_points.py`, type `roof_penetration` |
| 5 | **Unit tags.** AHU-5 and RTU-5 are lidar candidates. RTU-1 to RTU-4 can't be told apart (B1, B2). The **RTU-5 nameplate is unread**. | all | Nameplate close-up + 20 ft wide shot | Rename the box in Blender; rerun `hvac_routes.py` with the tag order |
| 6 | **Two RTUs not seen in the lidar.** The bid package lists 5 RTUs on bridge roofs; the 2019 lidar shows 3 unit-sized objects on the deck roof. The others may be under 3 ft tall, on a wing roof, in a dropout on the black EPDM (61 % cell cover), or installed after 2019. | RTU-1 to RTU-5 | Site walk | As item 5 |
| 7 | Roof hatches and ladders | low roof, bridge | Photo list item 3e | `import_field_points.py`, type `roof_hatch` |

## Power and equipment

| # | Missing | Who / how | How to load |
|---|---|---|---|
| 8 | Service size, voltage and phase at SWBD E, M1, M2, M3 | Panel nameplates and schedules (photo list 3c) | `UTILITY_ITEMS.csv`, then `import_field_points.py` |
| 9 | Unit disconnect ratings and locations | Photo list 3b | as above |
| 10 | Existing conduit routes (reuse or new) | Site walk; as-builts through AmeriTech / the airport | Digitise, then `import_gis_layer.py` |

## Crane and staging

| # | Missing | Who / how | How to load |
|---|---|---|---|
| 11 | Actual crane position and outrigger pad for AHU-5. The model's 36 × 36 ft pad is a placeholder on the OSM apron. | AmeriTech lift plan; airport operations | Move the pad in Blender; radius lines update with the measure tool |
| 12 | Crane model and capacity chart at the pick radius (110–129 ft to the AHU-5 candidate; 57,900 lb) | Crane vendor via AmeriTech | Not modelled |
| 13 | RTU-5 crane spot, Airport Road closure limits and roadway width (the model's band is 300 × 40 ft, width NOT measured) | MOT plan; airport | Edit the closure polygon |
| 14 | Overhead clearances and obstructions not in 2019 lidar (signs, lights, canopies added since) | Site walk | Field points |

## Data layers not loaded

| # | Missing | Note |
|---|---|---|
| 15 | Orthophoto | GRANIT NH 2021/22 6-inch is the usual source; not downloaded here. Load with `drape_orthophoto.py`. The ground colour is lidar intensity, **not a photo**. |
| 16 | Parcels, FEMA flood zones, wetlands | Not needed for the route check. The collections exist empty. |
| 17 | Google 3D Tiles | Only if Edward sets the key in Blender's preferences himself. Visual only; never measured. |
| 18 | Roof structure, deck type and load capacity for AHU-5 (57,900 lb) | Structural engineer. The model shows geometry only. |

Not included by design: restricted-area boundaries, gates, checkpoints and security cameras (FAA AIP / IIJA airport job), and pricing.
