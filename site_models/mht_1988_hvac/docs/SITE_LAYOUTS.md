# Site measurements: MHT #1988 rooftop units

No EV layouts on this job. Every value is **MEASURED** from the 2019 USGS lidar / 1 m DEM, or a **CALCULATED
ESTIMATE** with its method, or listed in `MISSING_MEASUREMENTS.md`. Unit tags cannot be read from lidar: the
positions below are **lidar candidates** until the nameplates are photographed in place.

Grade (ground-floor reference) = median DEM in a 5–13 ft band around the terminal footprint = 68.81 m NAVD88 (225.8 ft); 5th–95th percentile 67.67–69.08 m.

## Unit candidates

| Tag | Basis | Lat, lon (NAD83) | Model X, Y (m) | Size L × W × H (ft) | Roof surface (ft NAVD88) | Roof above grade (ft) | Top of unit above grade (ft) | To roof drop edge (ft) | To wall / higher roof (ft) |
|---|---|---|---|---|---|---|---|---|---|
| AHU-5 | LIDAR CANDIDATE | 42.927379, -71.438307 | 19.3, -365.1 | 60.5 × 18.9 × 13.0 | 244.6 | 18.9 | 31.9 | 54.1 | 1.1 |
| RTU-5 | LIDAR CANDIDATE | 42.928048, -71.438018 | 45.0, -291.4 | 10.7 × 9.8 × 5.6 | 259.0 | 33.2 | 38.9 | 16.1 | 9.8 |
| RTU-2 | LIDAR CANDIDATE B1, TAGGED BY POSITION AND SIZE | 42.928502, -71.439541 | -77.8, -237.4 | 13.9 × 11.5 × 6.0 | 252.2 | 26.5 | 32.5 | 6.9 | 1.0 |
| RTU-1 | LIDAR CANDIDATE B2, TAGGED BY POSITION AND SIZE | 42.928438, -71.439274 | -56.2, -245.2 | 9.0 × 7.4 × 3.5 | 253.7 | 28.0 | 31.5 | 1.0 | 4.6 |
| AHU-5 alt 1 | alternate | 42.927528, -71.437905 | 52.6, -349.5 | 23.8 × 10.1 × 13.1 | 245.1 | 19.3 | 32.4 | 62.7 | 1.0 |
| AHU-5 alt 2 | alternate | 42.92759, -71.437978 | 46.8, -342.4 | 23.3 × 9.8 × 13.0 | 245.5 | 19.7 | 32.7 | 50.4 | 1.0 |
| AHU-5 alt 3 | alternate | 42.927632, -71.437907 | 52.8, -337.9 | 18.9 × 9.0 × 12.8 | 245.3 | 19.5 | 32.3 | 53.0 | 1.2 |

Method: DSM = highest lidar return per 0.25 m cell. Terminal: roof surface = grey opening of the DSM (6.25 m window);
equipment = blobs 0.8–6 m above it; AHU-5 = the largest unit-shaped blob on the lowest roof level (alternates ranked by
volume). Bridge: roof = cubic fit of the along-axis profile; objects 0.45–5 m above it; arches (narrow, spanning the deck)
and wing roofs (reaching past the deck edge) are excluded; RTU-5 = the candidate nearest Airport Road. Size = minimum
rotated rectangle of the blob (±1 ft on each side, lidar spacing). Drop edge = nearest cell more than 1.5 m below the
unit's roof; wall = nearest cell more than 1.5 m above it. Edge distances are plan distances from the unit outline.

## Pedestrian bridge (terminal to garage)

| Measure | Value | Basis |
|---|---|---|
| Length, garage face to terminal face (along the axis) | 359.4 ft | lidar outline + OSM footprints |
| Deck width at roof level | 38.1 ft | lidar |
| Roof height | 254.0–259.4 ft NAVD88; rises 5.3 ft toward the terminal | lidar |
| Roof above Airport Road at the crossing | 34.2 ft | lidar − DEM |
| Structural arches on the roof | 6, every 54.5 ft | lidar |
| Lidar returns on the roof | 12.3 pts/m²; 61.3 % of 0.25 m cells hit (black EPDM) | lidar |
| Underside / deck level | NOT MEASURED (not visible to lidar) | missing list |
| Unit-sized objects on the deck roof | RTU-5, RTU-2, RTU-1 (3 for 5 RTUs in the bid package) | lidar |

## Crane staging (CALCULATED ESTIMATE)

| Pick | Crane spot | Pick radius | Height | Notes |
|---|---|---|---|---|
| AHU-5 (57,900 lb, daylight) | 36 × 36 ft pad on the ramp, model X, Y 23.7, -398.2 | 109.8 ft to unit centre, 129.2 ft to far corner | low roof 19.0 ft above ramp | CALCULATED ESTIMATE: 36 x 36 ft pad (placeholder outrigger footprint) on the OSM apron polygon, on the line from the AHU-5 candidate to the nearest apron, the first spot clear of lidar objects over 3 ft (jet bridges, GSE). Radius measured centre of pad to unit centre and to the unit's far corner. Location to confirm with AmeriTech and airport operations; crane not selected. |
| RTU-5 (night, Airport Road closed 1:30–4:00 AM; 1:00 AM start said at the pre-bid) | Airport Road centreline, model X, Y 21.6, -293.6 | 77.0 ft | bridge roof 34.1 ft above road | CALCULATED ESTIMATE: crane spot = nearest point on the Airport Road centreline (OSM) at least 13 ft clear of the bridge outline; closure band = 150 ft each way along the centreline, 40 ft wide (roadway width NOT measured; replace with the MOT plan). Night work 1:30 to 4:00 AM per the bid package (1:00 to 4:00 AM said at the pre-bid meeting). |

Security: access routes, gates and restricted-area boundaries are not drawn or described in this model.
