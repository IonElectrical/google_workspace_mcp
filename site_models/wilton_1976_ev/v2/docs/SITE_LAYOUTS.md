# Site layouts - measurements (Wilton #1976, v2)

Layouts are DESIGN PROPOSALS for discussion. Measured values come from the 2019 USGS 1 m DEM (NAVD88), lidar-registered OSM footprints and NHD. Trench lengths are CALCULATED ESTIMATES: they start at a placeholder on the nearest building wall because no transformer or service location is mapped yet.

## S1_PoliceLot

Inside the police lot; the flattest valid row, preferring the back (away from the riverwalk front along Stony Brook) and staying near the building.

| Measure | Value | Source |
|---|---|---|
| Ground elevation at stalls | 357.09 ft NAVD88 | USGS 3DEP 1 m DEM |
| Clearance to nearest building | 9.8 ft | lidar-registered OSM footprint |
| Nearest named stream | Stony Brook | NHD HR |
| Distance to stream centreline | 140.6 ft | NHD HR |
| Distance to mapped water edge | 117.9 ft | NHD area/waterbody |
| Height above stream water surface | 8.6 ft | DEM (hydro-flattened) - NOT a FEMA BFE |
| Distance to riverwalk / footway | 94.4 ft | OSM footway |
| Max slope, any stall or aisle | 2.44 % | DEM plane fit (ADA max 2.08 %) |
| Trench to pedestal 1 | 40.8 ft along ground (40.8 ft plan) | CALCULATED ESTIMATE from placeholder |
| Trench to pedestal 2 | 29.1 ft along ground (29.0 ft plan) | CALCULATED ESTIMATE from placeholder |
| deed_area | {"area_sqft": 24811, "source": "Overture/OSM parking polygon minus lidar-registered building footprint", "label": "40 SPACES DEEDED TO WILTON FALLS BLDG - DEED UNDELINEATED (whole paved lot shown)"} | see notes |
| police_exit | {"length_ft": 108.7, "zone": [[132.519, 207.236], [130.042, 186.537], [98.799, 192.185], [110.306, 234.889]], "zone_area_sqft": 10373, "note": "ASSUMED from the brief (front = riverwalk side NE, exit = road behind = SW to Burns Hill Rd). Confirm with WPD."} | see notes |
| hazard | {"xy": [126.78, 225.06], "text": "REPORTED: sodium cyanide vault under a concrete cap 'adjacent to the Wilton Police Department' (Abbott Trust Lot J-104-2, EPA 2023). Exact location NOT mapped - locate before any trenching."} | see notes |

| Stall / aisle | Slope % | Relief m |
|---|---|---|
| ADA van stall | 1.22 | 0.043 |
| ADA access aisle 8 ft | 1.15 | 0.043 |
| EV stall 1 | 2.35 | 0.093 |
| EV stall 2 | 2.44 | 0.106 |
| EV stall 3 | 2.42 | 0.144 |

## S2_MainStLot

Paved area nearest the given point off Main St (SW of the Main St / Burns Hill Rd junction), preferring distance from Stony Brook.

| Measure | Value | Source |
|---|---|---|
| Ground elevation at stalls | 359.09 ft NAVD88 | USGS 3DEP 1 m DEM |
| Clearance to nearest building | 120.1 ft | lidar-registered OSM footprint |
| Nearest named stream | Souhegan River | NHD HR |
| Distance to stream centreline | 82.5 ft | NHD HR |
| Distance to mapped water edge | 51.5 ft | NHD area/waterbody |
| Height above stream water surface | 23.0 ft | DEM (hydro-flattened) - NOT a FEMA BFE |
| Distance to riverwalk / footway | 6.1 ft | OSM footway |
| Max slope, any stall or aisle | 10.72 % | DEM plane fit (ADA max 2.08 %) |
| Trench to pedestal 1 | 19.7 ft along ground (19.7 ft plan) | CALCULATED ESTIMATE from placeholder |
| Trench to pedestal 2 | 34.8 ft along ground (34.8 ft plan) | CALCULATED ESTIMATE from placeholder |
| bands | {"given_point_to_stony_brook_ft": 134.7, "rings_ft": [150, 250], "center": [237.06, 182.32], "note": "Brief: possible FEMA AE / floodway 150-250 ft SW toward Stony Brook. NFHL not loaded - rings are distances only."} | see notes |

| Stall / aisle | Slope % | Relief m |
|---|---|---|
| ADA van stall | 2.46 | 0.148 |
| ADA access aisle 8 ft | 3.06 | 0.162 |
| EV stall 1 | 2.98 | 0.157 |
| EV stall 2 | 2.87 | 0.186 |
| EV stall 3 | 10.72 | 0.41 |

## S3_Library

Street-side parallel stalls on the library side of the road between the library and Stony Brook (OSM: Forest Road; brief: Main St - confirm); curb line = measured pavement edge.

| Measure | Value | Source |
|---|---|---|
| Ground elevation at stalls | 357.48 ft NAVD88 | USGS 3DEP 1 m DEM |
| Clearance to nearest building | 72.7 ft | lidar-registered OSM footprint |
| Nearest named stream | Stony Brook | NHD HR |
| Distance to stream centreline | 94.6 ft | NHD HR |
| Distance to mapped water edge | 57.3 ft | NHD area/waterbody |
| Height above stream water surface | 9.0 ft | DEM (hydro-flattened) - NOT a FEMA BFE |
| Distance to riverwalk / footway | 5.0 ft | OSM footway |
| Max slope, any stall or aisle | 0.97 % | DEM plane fit (ADA max 2.08 %) |
| Trench to pedestal 1 | 70.6 ft along ground (69.1 ft plan) | CALCULATED ESTIMATE from placeholder |
| Trench to pedestal 2 | 74.6 ft along ground (73.2 ft plan) | CALCULATED ESTIMATE from placeholder |

| Stall / aisle | Slope % | Relief m |
|---|---|---|
| ADA van stall (parallel) | 0.44 | 0.04 |
| ADA access aisle (in-line, PROWAG R309 - design detail) | 0.46 | 0.025 |
| EV stall 1 (parallel) | 0.45 | 0.034 |
| EV stall 2 (parallel) | 0.8 | 0.035 |
| EV stall 3 (parallel) | 0.97 | 0.041 |

## S4_Mill

Paved area beside the mill's north building (holds Computer Haven), near the Riverside Way / Mill St entrance.

| Measure | Value | Source |
|---|---|---|
| Ground elevation at stalls | 349.15 ft NAVD88 | USGS 3DEP 1 m DEM |
| Clearance to nearest building | 12.2 ft | lidar-registered OSM footprint |
| Nearest named stream | Souhegan River | NHD HR |
| Distance to stream centreline | 256.4 ft | NHD HR |
| Distance to mapped water edge | 71.7 ft | NHD area/waterbody |
| Height above stream water surface | 17.2 ft | DEM (hydro-flattened) - NOT a FEMA BFE |
| Distance to riverwalk / footway | 84.4 ft | OSM footway |
| Max slope, any stall or aisle | 2.08 % | DEM plane fit (ADA max 2.08 %) |
| Trench to pedestal 1 | 42.5 ft along ground (42.5 ft plan) | CALCULATED ESTIMATE from placeholder |
| Trench to pedestal 2 | 20.5 ft along ground (20.5 ft plan) | CALCULATED ESTIMATE from placeholder |
| bridge_corridor | {"length_ft": 317.9, "water_width_ft": 141.9, "crosses_souhegan": true, "note": "CALCULATED ESTIMATE: shortest line from the mill complex to Howard St centreline (NRPC 2025: bridge 'Riverside Way & Howard Street'). Plan A / Plan B landings TBD on site."} | see notes |
| dike_candidate | {"pond_surface_z_ft": 354.3, "crest_z_ft_range": [357.58, 364.34], "crest_height_above_pond_ft_median": 3.7, "pond_area_sqft": 88954, "source": "NHD Lake/Pond (unnamed) + crest = highest 1 m DEM cell within 14 m outward of the pond edge", "label": "DIKE - CALCULATED ESTIMATE (traced from lidar DEM); confirm it is the Waterworks dike"} | see notes |

| Stall / aisle | Slope % | Relief m |
|---|---|---|
| ADA van stall | 0.32 | 0.065 |
| ADA access aisle 8 ft | 0.26 | 0.033 |
| EV stall 1 | 1.58 | 0.076 |
| EV stall 2 | 2.08 | 0.113 |
| EV stall 3 | 1.98 | 0.129 |
