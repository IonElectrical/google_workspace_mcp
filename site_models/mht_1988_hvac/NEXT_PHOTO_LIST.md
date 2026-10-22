# MHT #1988: next photo and measurement list (Edward on site now)

Priority order. The **Blocking** items are what moves `ROUTE_LENGTHS.md` from CALCULATED ESTIMATE to MEASURED.

## Before you shoot

- **No drone.** MHT is controlled airspace. Nothing on this list needs a flight.
- **Security.** Follow the escort and badge rules. Don't photograph checkpoints, restricted-area signs, access-gate hardware, or security cameras. If one is in frame, crop it before the photo leaves the phone. Those photos stay in CompanyCam and are never used in the model.
- **GPS on** for CompanyCam (Settings → CompanyCam → Location → While Using). Roof GPS is ±15 ft. The wide shot is what places an item on the lidar model.
- **Scale in every wide shot:** the wheel, a tape, a cone or a person.
- **Nameplates:** one square-on close-up that fills the frame, then one wide shot from about 20 ft that shows the unit and a roof edge, parapet corner or hatch.
- Account numbers and anything the owner says in confidence stay in CompanyCam, not in shared files. No pricing in any file.

## 1. Wheel or tape readings along each feeder route (Blocking)

Walk each route from the panel to the unit disconnect. Write the reading at every change of direction or surface. Note the surface type for each leg: corridor, ceiling space, chase, exposed on roof, sleepers, wall.

| Route | From | To | Legs to record | Your assumption |
|---|---|---|---|---|
| AHU-5 feeder, (2)[3-250 kcmil + 1#2 GND in 3in] | SWBD E, room #1077 | AHU-5 disconnect, low roof | room door → riser base (horizontal) · riser base → roof (vertical, count floors) · penetration → unit (roof) | 250 ft |
| RTU-5 branch, 3#8 + 1#10 in 1in | Panel M1, room #103 | RTU-5, bridge over Airport Road | same three legs | 120 ft |
| RTU-1 and RTU-2 branches | Panel M3, room #105 | RTU-1, RTU-2 on the bridge roof | same three legs, one per unit | 120 ft |
| RTU-3 and RTU-4 branches | Panel M2, room #204 | RTU-3, RTU-4 on the bridge roof | same three legs; record the #204 floor-to-roof height | 60 ft |

Also tape the floor-to-floor height at each riser. The lidar gives the roof surface (risers 18.9 to 33.2 ft above grade), but not the floor levels.

## 2. Polycam scans with control points (Blocking)

| # | Scan | Control points (4, spread to the corners of the scan) | Taped distance |
|---|---|---|---|
| 2a | Room #1077 (SWBD E) | 4 named marks: room corners or door jambs, plus one point visible through the door into the corridor | Wall to wall |
| 2b | Room #103 (panel M1) | same | same |
| 2c | Room #105 (panel M3) | same | same |
| 2d | Room #204 (panel M2) | same | same |
| 2e | AHU-5 low roof | 4 roof corners or parapet corners that also show in the lidar (the high-roof walls next to the unit are good) | Unit length |
| 2f | Bridge roof, garage end to terminal end | arch bases (the lidar shows 6 arches, about 54 ft apart) | One arch to the next |
| 2g | RTU-5 area | wing corners next to the unit | Unit length |

Name the control points `CP1`...`CP4` in the Polycam export and in the photo captions. In Blender, `register_capture.py` fits the scan to the model and prints the RMS in feet. Record it.

Indoor rooms have no lidar. To place them, carry the chain: corridor → door → exterior wall at a window or exit, with one control point you can also see from outside.

## 3. Nameplates, panels and penetrations (Blocking for tags)

| # | What | Why |
|---|---|---|
| 3a | Every unit nameplate: AHU-5, RTU-1, RTU-2, RTU-3, RTU-4, **RTU-5 (unread so far)**. Close-up plus a 20 ft wide shot. | Ties the tag to the lidar candidate. The lidar shows only 3 unit-sized objects on the bridge roofs for 5 RTUs. |
| 3b | Each unit disconnect: rating and fusing | Route end point |
| 3c | Panel schedules: SWBD E, M1, M2, M3, and the breaker for each circuit | Confirms circuit and spare space |
| 3d | **Roof penetration for every circuit**, with a wide shot that shows the unit | Roof run (now NOT MEASURED) |
| 3e | Roof hatches and ladders on the low roof and the bridge | Access and the roof-edge distances for the work plan |

## 4. Nice to have tonight

- A wide shot of each bridge cross-wing (mid-span and terminal end), to see whether units sit on the wing roofs. The lidar treats those as wing roof.
- The crane staging spot as AmeriTech plans it, as a pin or a sketch on a printout. The model's pad is a placeholder.
