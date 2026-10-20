# Wilton #1976: next photo list (after the 10/20 walk)

This list replaces `FIELD_CHECKLIST.md` for the next visit. It is in priority order: the items marked **Blocking** stop trench and electrical design until we have them.

## Before you shoot

- Turn on location for CompanyCam (phone Settings → CompanyCam → Location → While Using).
  - The public timeline hides GPS, but the API reads it. Without GPS a photo can't be placed on the map.
- Put a scale reference in every wide shot: a tape, the measuring wheel, a cone or a person.
- For nameplates, take one square-on close-up that fills the frame, then one wide shot from about 20 ft that also shows a building corner or curb. The wide shot is what places the item on the lidar model.
- Meter numbers and account numbers stay in CompanyCam. They don't go into shared files.

## The list

| # | Priority | What | Where | Why | Scale reference |
|---|---|---|---|---|---|
| 1 | **Blocking** | Mill pad-mount **kVA plate**: the rating plate, or the label inside the door if Eversource opens it. Also a wide shot of the door side with a cone placed 10 ft out. | Mill pad-mount (Howard, serial 2211802515) | The kVA isn't readable. The cone checks the 10 ft / 4 ft clearance zone. | Tape from the door to the cone |
| 2 | **Blocking** | **Police lot pad-mount**: the nameplate, the tag, a wide shot from about 20 ft, and a second wide shot from the back of the lot looking at it | S1, 7 Burns Hill Rd | Source for S1 trenches. Its location and size are unknown. | Cone at the pad corner; person in the wide shot |
| 3 | **Blocking** | **Panels and meters** at the police station, Town Hall and library, plus the mill main disconnect. Shoot the meter face (form / class / voltage), the main breaker handle (amps), the panel nameplate (voltage, phase, bus rating) and the panel schedule (spare spaces). | Electrical rooms / meter walls | Service size, voltage and phase per site | n/a (close-ups) |
| 4 | **Blocking** | **Tie pole tag "5" to its pole**: one shot that shows the tag and the pole top together, or a slow video pan from the tag up to the crossarm. Do the same for "Wilton Telco 3". | Mill alley and Mill St | We can't yet say whether tag 5 is the three-transformer pole | Person standing at the pole base |
| 5 | **Blocking** | **The three pole cans**: a zoom shot of each can's stenciled kVA number and its nameplate side | Mill alley pole | Bank size. A 3-phase bank is inferred, not confirmed. | n/a |
| 6 | **Blocking** | **Cones at each proposed charger spot**: one at each stall corner, plus a pedestal mark. Shoot from the drive aisle and from behind. | S1 back of lot, S2, S3 curb, S4 by the north building | Gives true positions and lets us check the model's layouts | Cones; wheel reading on the stall depth (18 ft) |
| 7 | **Blocking** | **Wheel readings along each trench path**, from the power source to each pedestal. Take a photo at every turn and surface change with the wheel counter visible, and note the surface (asphalt / concrete / lawn / gravel). | All 4 sites | Turns the trench lengths from CALCULATED ESTIMATE into measured. Also gives the restoration areas. | Wheel counter in frame |
| 8 | High | **Look up from each pedestal spot**: any overhead lines above or near, with the lowest wire in frame. Add a laser-measure height if you have one. | Each charger spot | Overhead clearance conflicts | Laser or known pole height |
| 9 | High | **Mill roof**: the access point (hatch or ladder), a surface close-up (membrane type), edges and parapet height, all equipment, and drains. Shoot from a high vantage or by drone if allowed. | Both mill buildings | Roof table: obstructions, setbacks, condition | Tape on the parapet; person on the roof |
| 10 | High | **Green sign at the hydro channel**: straight on, filling the frame and in focus, plus a wide shot for location | Hydro channel / sluiceway | The sign text names or dates the channel | n/a |
| 11 | Medium | **Building #15**: the street sign and house number in one frame, plus a wide shot that includes the pole and streetlight | Unknown street | Places it as a control point | Person or cone |
| 12 | Medium | **Route 101 grass area**: wide shots, the Greenville/Peterborough sign, and cones at the corners if it's a candidate | Rte 101 entrance | Site option and control point | Cones; wheel along one edge |
| 13 | Medium | **Pedestrian bridge Plan A / Plan B landings**: stand on each landing, drop a pin, and shoot each way | Riverside Way / Howard St | Bridge conflicts | Person |
| 14 | Medium | **Riverwalk and memorial benches at S1**: one wide shot from each bench toward the proposed chargers | S1 front | Sight lines for the Select Board's before/after views | Person |
| 15 | Medium | **Snow storage**: where the piles go at each lot, with a Town or DPW pointer if possible | S1, S2 (Town snow dump corner) | Snow storage and plow buffer | Cones at the pile limits |

## Polycam passes

Each pass needs at least 4 control points spread around the scan that are also visible in the lidar: building corners at the ground, curb corners, pole bases, manhole centres. Photograph and name each one (CP1, CP2…). Tape one distance inside the scan as a scale check.

| Pass | Covers | Mode |
|---|---|---|
| P1 | S1 back of lot: the proposed charger row, the pad-mount, and the building corner | LiDAR mode (iPhone Pro) or Photo mode; walk slowly, about 2 laps |
| P2 | S4: the mill pad-mount and its clearance zone, the alley with the three-can pole, and the meter wall | Same |
| P3 | S3: the library frontage curb, sidewalk and planting strip | Same |
| P4 | S2: the proposed stalls and the snow corner | Same |

After import, `register_capture.py` reports the scale and the RMS fit error in feet. Write that number down with the scan.
