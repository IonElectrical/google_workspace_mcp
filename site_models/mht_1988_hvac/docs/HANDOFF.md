# MHT #1988: handoff, where we left off (2026-10-22, evening)

Read this first when you come back. It is everything needed to pick the job up without re-reading the chat.
**Private. Security-sensitive. No pricing in this file or anywhere in the repo.** Site-access, badging and
gate details are deliberately left out. They are in the pre-bid transcript in Plaud (see §1).

---

## 1. Where everything is

| What | Where |
|---|---|
| Model, docs, pipeline | Repo `ionelectrical/google_workspace_mcp`, branch **`claude/mht-1988-hvac-3d`**, folder `site_models/mht_1988_hvac/`. No PR opened. |
| Browser viewer (hosted) | https://claude.ai/artifact/DL499YM4TVbjTPKbvKBJt2. **Its sharing reads "Anyone with the link". Switch it to private in the page's Share menu.** Local copy: `web/MHT1988_Terminal_Viewer.html`. |
| Blender model | `blend/MHT1988_Terminal_v1.blend` (44.5 MB, Blender 4.5+). The 5 import/registration tools are in its Scripting tab and in `tools/`. |
| RFP documents | Google Drive folder `1n2F8Mff6J8VTs2L0242kab8t-PDMUlKt` (Vol 1 front end, Vol 2 standard specs, Vol 3 scope §002000 + tech specs + Appendix A drawings). |
| Site-walk photos | Google Drive folder `1_zLdlR-PoxzI5OzVF3Dk4jSduHjxpnXN` (82 iPhone HEIC, 12:40–12:46). Photos are NOT in the repo; their metadata is in `job_config.py` → `FIELD_PHOTOS`. |
| CompanyCam gallery | `app.companycam.com/galleries/cyTx1a8g`. **Not reviewed:** the cloud environment blocks that host. Either export the photos to Drive, or add the host under the environment's Network access → Allowed domains. |
| Meeting recordings | Plaud: "10-22 Meeting: Manchester Airport AHU-5 Replacement Re-bid…" (10:30, 82 min, the formal pre-bid) and "10-22 Manchester Airport HVAC and Electrical Modernization Site Walk" (12:00, 75 min). Both fully transcribed and read. |
| Quote to Granite State Plumbing & Heating | **Gmail draft** to Matt Cruite, mcruite@gsphinc.com, (603) 235-7041, for MHT #1988. **Price left blank on purpose. Fill it in and send.** (Plaud's AI summary misspells him "Pruitt"; in the recording he spells it C-R-U-I-T-E. The draft is correct.) |
| JobTread | Job #1988. |

The cloud session's scratch folder (cached lidar, venvs, transcripts as text) is **temporary**. Everything that matters is in the repo, Drive, Plaud or Gmail.

---

## 2. The job in one paragraph

Manchester-Boston Regional Airport, *Airport Terminal & Walkway HVAC Equipment Replacement*, City requisition **2600049** (the airport also calls it 266049; it's the re-bid of 26028). FAA AIP / Airport Terminals Program FY2026 money. **AmeriTech Contracting is prime; Ion Electrical bids the electrical** (and possibly to other primes, see §4). It is a **modified design-build**, about 40–60 % designed: the contractor's engineers of record finish it. **Base bid: AHU-5 plus RTU-1 to RTU-5 on the pedestrian bridge.** AHU-6 and AHU-7 come out as a separate bid with FY2027 money. They are not in this contract, but the heat-load calculation has to include them.

---

## 3. Key dates and process

| Item | Detail |
|---|---|
| Questions | **In writing, by email to John Goodrow, by Nov 17, 2026.** Send them as they come up; addenda answer them. The final addendum comes before Thanksgiving. |
| Proposal due | Said aloud as "Monday the 13th", which isn't a Monday. **Check the RFP:** Monday Dec 14, 2026 is the likely date. |
| Evaluation | 70 % price / 30 % technical approach and qualifications. The **schedule (Gantt) is scored**: shorter wins points. |
| Lead times (airport's guidance) | RTU-1 to 5: about 6–9 weeks (standard packaged units; the airport suggests spring, staged one or two a week). AHU-5: 7–12 months. |
| Contract start assumed | About mid-January 2027, then a design phase of a couple of months. |
| Pre-qualification | City pre-qual applies to the prime bidder. Anyone pre-qualified under 26028 is covered. New packages go to procurement@flymanchester.com. |
| Return visits | Allowed. Give the airport 3–4 days' notice so they can arrange escorts. |
| Permits / inspections | The airport is self-jurisdictional: **no city permits or city inspections.** The building superintendent and John Goodrow inspect. The superintendent fills out a tenant work permit. |

---

## 4. People

| Person | Role | Notes |
|---|---|---|
| **John Goodrow** | Airport's on-call engineer and project rep (23 yrs at MHT) | All questions, submittals and reviews go through him. |
| Building superintendent / facility manager ("John", 33 yrs on site) | Airport | Inspector with John Goodrow. Runs crane days and road closures himself, with no police details. Zero tolerance for rule breaking. |
| Christina Adams | Airport office administrator | Check-in. |
| **Tony Page** | AmeriTech Contracting (on site) | AmeriTech is out of Connecticut; Tony is also on a Manchester VA job. |
| Paul Kusheba | AmeriTech senior estimator | Called Tony in. |
| Hunter | AmeriTech junior / assistant estimator | Sent us the request for electrical. |
| Mark Washington | AmeriTech | Contracts and bonding. |
| **Matt Cruite** | Granite State Plumbing & Heating (GSPH Inc.) | NH only. Quote draft waiting (§1). |
| Controls contractor | The airport's Metasys controls company | Did the last unit's controls. New units need 24 V AC controls, Metasys-compatible, ready for a future Metasys upgrade. |
| Capstone | Possible prime / partner | Edward plans to send them the electrical + controls quote too. Minority-business status is going away by year end, so they don't need to plan around it. |
| Abel Rigging (Merrimack) | Rigger the airport has used | For crane coordination. |
| Ramon Ruiz | Ion Electrical | Attended with Edward. |

---

## 5. Electrical scope as we understand it

From §002000, Appendix A and what John Goodrow said:

- **Disconnect and reconnect, turnkey.** Cut existing feeders back, dead-end them, make them safe in a box, then extend and reconnect to the new units. The site walk added: disconnect, label, and trim conductors to the new terminal blocks.
- **Ion's electrical engineer of record** must verify that the existing feeders and breakers suit the final equipment, and must **stamp the final electrical drawings (NH PE)**. That is a design cost in the electrical number.
- **Single lines (E-1/E-2) give every feeder and breaker.** No run lengths are shown anywhere.

  | Unit | Feeder | OCPD | Source |
  |---|---|---|---|
  | AHU-5 | (2)[3-250 kcmil + 1#2 G in 3 in] | 500 A | SWBD E, room #1077 |
  | RTU-1 | 3#10 + 1#10, 1 in | 25 A | panel M3, #105 |
  | RTU-2 | 3#6 + 1#8, 1 in | 60 A | M3, #105 |
  | RTU-3 | 3#6 + 1#8, 1 in | 60 A | M2, bridge room #204 |
  | RTU-4 | 3#8 + 1#10, 1 in | 45 A | M2, #204 |
  | RTU-5 | 3#8 + 1#10, 1 in | 40 A | M1, #103 |

- **Power system studies must be done in SKM** (owner's only accepted software). Conductors are copper.
- **AHU-5 disconnect:** on the walk, line voltage enters through the top of the unit and **no external disconnect could be found**. It is probably inside the unit. Ask (§8).
- **Controls:** the Metasys controls contractor handles the take-down and reconnection of controls. Clarify with the primes whether the 24 V control wiring is ours or his.
- **Electrical rooms:** lockout/tagout only; no work in them is expected beyond the feeders.
- **New UPS** is coming into the mechanical space where the AHU-5 glycol riser valves are today. Coordinate.
- Mechanical scope that touches us: glycol isolation valves on the AHU-5 risers above the TSA inspection table (Fig. 1, Appendix A), smoke-damper live test with controls, rooftop gas lines replaced, four roof specs (1998, 2000, 2015 under warranty, ped bridge 2000).

---

## 6. The model: what it says now

Built from the 2019 USGS lidar (15.2 pts/m², ±0.1–0.5 ft vertical), USGS 1 m DEM, Overture/OSM outlines, NAD83 / UTM 19N, NAVD88.
Roofs are now drawn as flat lidar-traced blocks (looks cleaner; the measurements are unchanged).

**Units**

| Unit | Status | Roof above grade | Notes |
|---|---|---|---|
| AHU-5 | Lidar candidate, 60.5 × 18.9 × 13.0 ft on the valley roof | 18.9 ft (airport: "about 18") | Three smaller alternates on the same roof. Crane from the Gate 7 apron: pick radius about 110 ft to centre, 129 ft to far corner, about 57,900 lb (an earlier review of the drawings showed it ships in two sections, about 35,300 + 22,600 lb; re-check). |
| RTU-1 | Lidar candidate **B2**, 9.0 × 7.4 × 3.5 ft, **tagged by position + size** | 28.0 ft | Garage end. The York unit in photo IMG_5255 is RTU-1 or RTU-2. |
| RTU-2 | Lidar candidate **B1**, 13.9 × 11.5 × 6.0 ft, **tagged by position + size** | 26.5 ft | Garage end, on the head house. |
| RTU-3, RTU-4 | **Not in the lidar** (mid-bridge per the airport; black EPDM gives dropouts) | ≤ 14.2 ft riser from #204 (bound) | Must be found on the roof. |
| RTU-5 | Lidar candidate, 10.7 × 9.8 × 5.6 ft, **photo-matched** (IMG_5256/5257) | 33.2 ft | Terminal end, behind the parapet over the curb canopy; **lightning-protection air terminals next to it.** Night lift with the road closed (see below). |

Tags are set in `job_config.py` → `BRIDGE_UNIT_TAGS`. Change them there if the nameplates say otherwise.

**Your four estimate numbers vs. the model** (`ROUTE_LENGTHS.md`, all CALCULATED ESTIMATE because the rooms are interior):

| Your number | Riser | Left for horizontal + roof run |
|---|---|---|
| 250 ft, #1077 → AHU-5 | 18.9 ft | 231 ft |
| 120 ft, #103 → RTU-5 | 33.2 ft | 87 ft (tightest) |
| 120 ft, #105 → RTU-1 / RTU-2 | 28.0 / 26.5 ft | about 92 ft |
| 60 ft, #204 → RTU-3 / RTU-4 | ≤ 14.2 ft | ≥ 46 ft |

Watch-out from the RFP: the 1200 A bridge MDP in #204 feeds M1 (#103) and M3 (#105). So #103 and #105 may sit on the bridge side of the terminal, which would change the 120 ft runs. Confirm the room locations.

**Other measured facts:**
- **Bridge:** 359 ft from garage face to terminal face, 38 ft deck. Its roof is 34.2 ft above Airport Road and rises 5.3 ft toward the terminal. 6 roof arches about 54.5 ft apart.
- **Terminal roofs:** main roof 31.0 ft above grade, parts at 32.6 and 34.2 ft. The airport says the high roof is 34–35 ft.
- **Crane distances on the general plan:** 1,860 ft from the RWY 17/35 centreline and 2,280 ft from 6/24. The model measures 1,779 ft for the AHU-5 candidate, so GP-1's point is about 80 ft off.
- **RTU-5 night closure has three versions:**

  | Source | Window |
  |---|---|
  | Spec | 1:30–4:00 AM |
  | GP-1 sheet | 1:30–4:30 AM |
  | Pre-bid (verbal) | 1:00–4:00 AM |

**Google 3D Tiles would not improve accuracy.** It is a visual-only photogrammetry mesh with metre-level error, and its terms don't allow keeping it. Better numbers only come from field capture and drawings.

---

## 7. What the photos and recordings changed today

1. **Photos (82 reviewed):**
   - 78 are walkthrough shots with no electrical gear visible.
   - 4 show roof units from the curb. Matched by GPS and heading in `docs/FIELD_PHOTOS.md`, and shown as purple posts and sight lines in the viewer.
   - No nameplate is legible from the curb.
2. **Unit positions (pre-bid):**
   - RTU-1/2 at the garage end, RTU-3/4 mid-bridge, RTU-5 on the escalator/elevator building. All York units from 2000.
   - Two bridge units are dead; the AHU-5/6/7 units break down constantly.
3. **Getting close to RTU-1 to RTU-4:**
   - From the garage, levels 2–3, through the screen, RTU-1/2 are "within arm's reach"; RTU-3/4 are visible in the distance.
   - The bridge roof has a ladder and hatch, but you "play limbo under the beam" to get up there.
4. **Valley roof structure:** 16–20 in cast-in-place concrete beams and a 10 in slab. New units reuse the footprint; a structural memo is needed, not structural work.
5. **Crane for the bridge RTUs:**
   - Lifts from the landside lot/lanes with partial closures; the airport places the barricades the night before.
   - RTU-1/2 is a long reach.
   - AHU-5 needs a big crane on the Gate 7 apron. That gate hosts military aircraft overnight, so the work area is cleared by about 4:30 AM, though up to 48 h can be arranged through the CSPP.
   - The contractor files **FAA Form 7460** early (about 30-day review) and prepares the CSPP; the tower may hold lifts.

---

## 8. Questions to send John Goodrow (draft list, before Nov 17)

1. AHU-5: where is the existing disconnecting means? It isn't visible outside the unit. Is a new unit-mounted or separate disconnect required?
2. Locations of electrical rooms #1077, #103, #105, #204, and the riser/chase from each to its roof. Can the airport release floor plans showing them? (This is the biggest unknown in our run lengths.)
3. Lightning protection: air terminals sit on the bridge roof next to RTU-5. Must the new units be bonded to the LPS (NFPA 780), and by whom?
4. RTU-5 closure window: spec 1:30–4:00, GP-1 1:30–4:30, pre-bid 1:00–4:00. Which governs?
5. Controls: is the 24 V control wiring between the new units and Metasys in the electrical scope or the controls contractor's?
6. Is the SKM study scope limited to the units' feeders, or the whole distribution from SWBD E / the bridge MDP?
7. Is reuse of the existing feeders acceptable if the EOR shows they're code-compliant, or are new conductors expected anywhere?
8. Proposal due date: please confirm (said "Monday the 13th").

---

## 9. Next steps, in order

1. **Switch the viewer to private** (Share menu on the claude.ai page).
2. **Fill in and send the GSPH quote** (Gmail draft).
3. **Send the electrical quote to AmeriTech** (Paul Kusheba / Hunter), and decide on Capstone.
4. **Send the §8 questions** to John Goodrow, ideally through or alongside the prime.
5. **Book a return visit** (3–4 days' notice) for the blocking captures on `NEXT_PHOTO_LIST.md`:
   - nameplates for all 6 units (from the garage for RTU-1 to 4; the roof for AHU-5 and RTU-5);
   - wheel or tape readings room → riser → roof;
   - Polycam scans of rooms #1077, #103, #105, #204 with 4 control points each;
   - roof penetration per circuit;
   - the disconnect for each unit.
6. **CompanyCam:** export to Drive or allow the host, then have Claude review those photos like the Drive set.
7. When field data comes in:
   - register scans with `register_capture.py` and points with `import_field_points.py`;
   - fix tags in `BRIDGE_UNIT_TAGS`;
   - rerun the pipeline. `ROUTE_LENGTHS.md` then flips from CALCULATED ESTIMATE to MEASURED.
8. Still pending model edits (offered, not yet done):
   - mark the #103/#105 bridge-side room hypothesis;
   - add GP-1 checks and a per-RTU table to `ROUTE_LENGTHS.md`;
   - split the AHU-5 pick into its two section weights;
   - draw AHU-6/7 as "not in contract".

---

## 10. Rules that stay in force

- **No drone** (MHT is controlled airspace).
- **No Google 3D Tiles** unless Edward sets the key in Blender preferences himself. Visual only, never measured, never committed (`*_google.blend` is git-ignored).
- **Security-sensitive:** private viewer only; no restricted-area, gate, checkpoint or security-camera details in shared outputs; the prepare step strips them. **No pricing anywhere.**
- **Never put an API key in chat or files.**
- **Every number is MEASURED, CALCULATED ESTIMATE (with method), or listed in `MISSING_MEASUREMENTS.md`.** Nothing is guessed.

## 11. Rebuilding (for Claude or anyone picking it up)

`README.md` → "Rebuilding" has the commands. Order:

```
prepare_site.py → hvac_routes.py → hvac_viewer.py → export_web.py [--bare for the hosted page] → build_blend.py
```

`prepare_site.py` re-downloads the lidar, DEM, Overture, NHD and USGS Structures data, because the cloud scratch cache is gone after the session. Lint with `uv run --frozen ruff check/format`, not a newer local ruff. To update the hosted viewer, republish to the same artifact link above.
