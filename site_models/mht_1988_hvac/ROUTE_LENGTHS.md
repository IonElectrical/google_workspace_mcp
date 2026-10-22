# ROUTE_LENGTHS: MHT #1988 feeder and branch-circuit routes

Electrical room to rooftop unit, per unit. Each length is either **MEASURED** (named dataset, or a tape or wheel
reading) or a **CALCULATED ESTIMATE** with its method. The rooms are interior and are not in any public dataset,
so **every total stays CALCULATED ESTIMATE** until the Polycam scans or wheel readings on the photo list come in.

Built 2026-10-22 from the 2019 USGS lidar (15.22 pts/m²) and the USGS 1 m DEM. Ground-floor reference: grade = median DEM around the terminal = 68.81 m NAVD88 (225.8 ft).

## The four numbers to confirm

| Your assumption | Units | What the model can say tonight |
|---|---|---|
| 250 ft from #1077 | AHU-5 | Riser 18.9 ft (CALC. EST.). Leaves 231 ft for the room-to-riser run and roof run. The farthest terminal corner is 573 ft from the unit in plan, so 250 ft is possible but not checkable until #1077 is located. |
| 120 ft from #103 | RTU-5 | Riser 33.2 ft (bridge roof over Airport Road). Leaves 87 ft. |
| 120 ft from #105 | RTU-1, RTU-2 | RTU-1 riser 28.0 ft, RTU-2 riser 26.5 ft (candidates tagged by position and size; nameplates unread). Leaves about 92 ft. |
| 60 ft from #204 | RTU-3, RTU-4 | #204 is on the bridge level; its floor is not visible to lidar. Riser is at most 14 ft. Leaves at least 46 ft along the bridge. The bridge is 359 ft face to face. |

## Per unit

| Unit | Feeder (E-1/E-2) | From | Unit position | Horizontal run, room to riser | Riser height | Roof run, penetration to unit | Total |
|---|---|---|---|---|---|---|---|
| AHU-5 | (2)[3-250 kcmil + 1#2 GND in 3in], 500A | Terminal Main Electrical Room #1077 (SWBD E) | AHU-5 (LIDAR CANDIDATE) | NOT MEASURED: room interior, not in public data | 18.9 ft, CALCULATED ESTIMATE | NOT MEASURED: penetration not located | CALCULATED ESTIMATE pending; your assumption 250 ft |
| RTU-1 | 3#10 + 1#10 in 1in, 25A | Ground Floor Electrical Room #105 (panel M3) | RTU-1 (LIDAR CANDIDATE B2, TAGGED BY POSITION AND SIZE) | NOT MEASURED: room interior, not in public data | 28.0 ft, CALCULATED ESTIMATE | NOT MEASURED: penetration not located | CALCULATED ESTIMATE pending; your assumption 120 ft |
| RTU-2 | 3#6 + 1#8 in 1in, 60A | Ground Floor Electrical Room #105 (panel M3) | RTU-2 (LIDAR CANDIDATE B1, TAGGED BY POSITION AND SIZE) | NOT MEASURED: room interior, not in public data | 26.5 ft, CALCULATED ESTIMATE | NOT MEASURED: penetration not located | CALCULATED ESTIMATE pending; your assumption 120 ft |
| RTU-3 | 3#6 + 1#8 in 1in, 60A | Pedestrian Bridge Electrical Room #204 (panel M2) | NOT SEEN in the 2019 lidar (mid-bridge per the airport); riser bound from the bridge-roof units RTU-2, RTU-1 | NOT MEASURED: room interior, not in public data | ≤ 14.2 ft (bound), CALCULATED ESTIMATE | NOT MEASURED: penetration not located | CALCULATED ESTIMATE pending; your assumption 60 ft |
| RTU-4 | 3#8 + 1#10 in 1in, 45A | Pedestrian Bridge Electrical Room #204 (panel M2) | NOT SEEN in the 2019 lidar (mid-bridge per the airport); riser bound from the bridge-roof units RTU-2, RTU-1 | NOT MEASURED: room interior, not in public data | ≤ 14.2 ft (bound), CALCULATED ESTIMATE | NOT MEASURED: penetration not located | CALCULATED ESTIMATE pending; your assumption 60 ft |
| RTU-5 | 3#8 + 1#10 in 1in, 40A | Ground Floor Electrical Room #103 (panel M1) | RTU-5 (LIDAR CANDIDATE) | NOT MEASURED: room interior, not in public data | 33.2 ft, CALCULATED ESTIMATE | NOT MEASURED: penetration not located | CALCULATED ESTIMATE pending; your assumption 120 ft |

## Method

- **Riser height (CALCULATED ESTIMATE).** Roof surface at the unit from the 2019 lidar (measured, about ±0.2 ft) minus the
  ground-floor slab, taken as grade (median 1 m DEM in a 5–13 ft band around the terminal footprint). Slab-at-grade is an
  assumption; panel height, ceiling offsets and the roof curb are not included. Add them from the field readings.
- **#204 (bridge room).** The bridge floor is not visible to lidar. Upper bound = highest bridge-unit roof minus (Airport Road
  surface 68.59 m + 14.5 ft minimum vertical clearance over a roadway). The deck structure is not subtracted, so the
  real riser is shorter.
- **Roof run.** Not measured: roof penetrations are not in public data. If the conduit comes up through a curb under the
  unit, it is 0 ft. Measure it on the roof (photo list item 3).
- **Horizontal run.** Not measured: rooms are interior. The scans and wheel readings (photo list items 1 and 2) replace it.
- **Unit positions.** Lidar candidates: equipment-sized objects standing 0.8–6 m (bridge: 0.45–5 m) above the fitted roof
  surface. Tags cannot be read from lidar. See `README.md` for the candidate list and alternates.
- **Plan sanity bound.** Distance in plan from the unit to the farthest corner of the room's building. A total longer than
  riser + that distance + a reasonable roof run would need checking.

## Lengths that would change a column from CALCULATED ESTIMATE to MEASURED

1. Wheel or tape readings along each route: room door to riser, riser floor to roof, penetration to unit disconnect.
2. Polycam scans of rooms #1077, #103, #105, #204 and each roof area, with 4 named control points and one taped distance.
   Register them with `register_capture.py` (in the .blend) and record the RMS in ft.
3. The roof penetration point for each circuit (photo list item 3).

No pricing is included anywhere in this model.
