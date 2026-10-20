# Mill roof measurements - 1 Riverside Way, Wilton (from 2019 USGS lidar)

Grid convergence at the mill: 1.863 deg (true azimuths below are corrected for it).

## Totals

| Measure | Value | Basis |
|---|---|---|
| Building footprints (mill complex) | 46,782 sq ft | lidar-registered OSM footprints, MEASURED |
| Roof planes, sloped area | 42,875 sq ft | lidar plane fits, MEASURED |
| Usable after 3 ft setback | 32,437 sq ft | CALCULATED ESTIMATE |
| Usable after 4 ft setback | 29,505 sq ft | CALCULATED ESTIMATE |
| Solar, 4 ft setback | 412.6 kW-DC | CALCULATED ESTIMATE (method below) |

## Claimed sizes vs measured footprint

The claims are floor areas (the 2022 article calls it a three-story mill); the lidar measures roofs / footprints. Claim / footprint is the floor-area ratio each claim implies - a CALCULATED ESTIMATE, not a story count.

| Claim | Source | Claim / measured footprint |
|---|---|---|
| 93,000 sq ft | Ledger-Transcript 2022-09-14 ('three-story mill building houses 93,000 square feet') | 1.99 |
| 93,890 sq ft | WRCRE broker listing 1-riverside-way-sold ('combined ... approximately 93,890 square feet') | 2.01 |
| 94,000 sq ft | cityfeet / LoopNet listing ('Total Building Size 94,000 SF') - also Ted's figure per brief | 2.01 |
| 100,000 sq ft | chillybears.com storage-3pl page / Pidcock LinkedIn ('100K SF') | 2.14 |

## North building (Computer Haven, Sentry Solutions, WS Packaging) - footprint 14,139 sq ft, lidar roof extent 12,989 sq ft, ground 346.6 ft NAVD88

| Plane | Plan sq ft (m²) | Sloped sq ft (m²) | Slope ° / pitch | Azimuth (true) | Height NAVD88 / above ground ft | Obstructions (sq ft) | Usable 3 ft / 4 ft sq ft | Solar kW-DC (est.) |
|---|---|---|---|---|---|---|---|---|
| 1 | 4,604 (427.8) | 4,606 (427.9) | 1.3 / 0.3:12 | 248.0 | 395.0 / 48.4 | 3 (83) | 3,774 / 3,370 | 47.1 (GCR 0.7) |
| 2 | 2,083 (193.5) | 2,085 (193.7) | 2.3 / 0.5:12 | 62.0 | 359.5 / 12.8 | 4 (148) | 1,524 / 1,355 | 18.9 (GCR 0.7) |
| 3 | 1,604 (149.0) | 1,604 (149.1) | 1.5 / 0.3:12 | 66.0 | 394.8 / 48.1 | 3 (151) | 791 / 498 | 7.0 (GCR 0.7) |
| 4 | 1,693 (157.2) | 1,695 (157.4) | 2.8 / 0.6:12 | 253.0 | 370.6 / 23.9 | 0 (0) | 1,266 / 1,027 | 14.4 (GCR 0.7) |
| 5 | 1,187 (110.2) | 1,188 (110.4) | 3.0 / 0.6:12 | 249.0 | 359.0 / 12.3 | 11 (355) | 342 / 237 | 3.3 (GCR 0.7) |
| 6 | 280 (26.0) | 280 (26.0) | 0.8 / 0.2:12 | flat (<1 deg) | 369.4 / 22.7 | 0 (0) | 48 / 0 | 0.0 (GCR 0.7) |
| 7 | 587 (54.5) | 587 (54.5) | 0.8 / 0.2:12 | flat (<1 deg) | 370.2 / 23.6 | 0 (0) | 301 / 140 | 2.0 (GCR 0.7) |
| 8 | 283 (26.2) | 283 (26.3) | 0.3 / 0.1:12 | flat (<1 deg) | 402.2 / 55.6 | 0 (0) | 145 / 78 | 1.1 (GCR 0.7) |

## South building (Printorium Apparel) - footprint 32,643 sq ft, lidar roof extent 31,382 sq ft, ground 342.9 ft NAVD88

| Plane | Plan sq ft (m²) | Sloped sq ft (m²) | Slope ° / pitch | Azimuth (true) | Height NAVD88 / above ground ft | Obstructions (sq ft) | Usable 3 ft / 4 ft sq ft | Solar kW-DC (est.) |
|---|---|---|---|---|---|---|---|---|
| 1 | 18,334 (1703.2) | 18,334 (1703.3) | 0.0 / 0.0:12 | flat (<1 deg) | 361.1 / 18.2 | 28 (1181) | 14,383 / 13,616 | 190.4 (GCR 0.7) |
| 2 | 11,870 (1102.8) | 11,870 (1102.8) | 0.0 / 0.0:12 | flat (<1 deg) | 374.9 / 32.0 | 5 (519) | 9,720 / 9,090 | 127.1 (GCR 0.7) |
| 3 | 342 (31.8) | 343 (31.8) | 4.3 / 0.9:12 | 159.0 | 358.8 / 15.9 | 3 (43) | 143 / 94 | 1.3 (GCR 0.7) |

## Method and assumptions

- **plane_fit**: RANSAC 0.15 m tolerance on single-return lidar points (NH_Coastal_2_2019, ~4.6 pts/m2), patches on a 0.5 m grid
- **setback**: usable = patch eroded by 3 ft / 4 ft from every patch edge, minus obstructions +1 m (CALCULATED ESTIMATE)
- **solar**: kW-DC = usable m2 x 215 W/m2 module power density x coverage (0.7 flat <5 deg on tilted rows, 0.85 pitched flush); north-facing pitched planes (>5 deg, azimuth 300-60 deg) excluded (CALCULATED ESTIMATE)
- Roof structure, membrane, age and load capacity are NOT measured - see the missing-measurements list.
- Parapets, skylights and equipment under ~0.5 m tall are below the lidar's resolution here.