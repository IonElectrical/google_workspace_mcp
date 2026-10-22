"""Per-job configuration: JobTread #1988, MHT terminal and walkway HVAC replacement.

Everything specific to this job lives here. The scripts in pipeline/ are job-agnostic and read
this module (or another job's config passed with --config). The Wilton #1976 values that used
to be hard-coded in frame.py, prepare_downtown.py, layouts.py, export_web.py and tour.json map
onto the sections below:

    frame.py            -> FRAME
    prepare_downtown.py -> DATASETS, CENTER_RESOLVE, DETAIL, SITE_CHECKS
    layouts.py          -> ANALYSIS (here: HVAC route lengths, not EV layouts)
    export_web.py, tour -> VIEWER, TOUR
    security / privacy  -> REDACT

Only plain Python literals, so Blender can import it too.
"""

JOB = {
    "slug": "mht_1988_hvac",
    "number": "1988",
    "title": "MHT terminal and walkway HVAC replacement",
    "client": "AmeriTech Contracting (prime); Ion Electrical is the electrical sub",
    "owner": "Manchester-Boston Regional Airport",
    "project": "Airport Terminal & Walkway HVAC Equipment Replacement, RFP 2600049",
    "purpose": "Check electrical estimating quantities: feeder and branch-circuit route lengths "
    "from electrical rooms to rooftop units, riser heights, roof-edge distances, crane staging.",
    "funding": "FAA AIP and IIJA funded",
    "blend_name": "MHT1988_Terminal_v1.blend",
    "viewer_name": "MHT1988_Terminal_Viewer.html",
}

# --------------------------------------------------------------------------- frame
FRAME = {
    "epsg": 26919,  # NAD83 / UTM zone 19N, metres (Manchester NH is at 71.44 W, inside 72-66 W)
    "utm_lon0": -69.0,
    "E0": 301000.0,  # scene origin, rounded to 1 km near the terminal (resolved centre)
    "N0": 4756000.0,
    "Z0": 0.0,
    "vertical": "NAVD88 metres (GEOID12B per the NH_Coastal_2019 metadata)",
    "state_plane": {  # NH State Plane NAD83, EPSG:3437, US survey feet
        "epsg": 3437,
        "lon0": -71.66666666666667,
        "k0": 0.999966667,
        "fe": 300000.0,
        "fn": 0.0,
        "lat0": 42.5,
    },
    "overview_radius_m": 1609.3,  # 1 mile
    "detail_radius_m": 300.0,  # around the terminal and the pedestrian bridge
}

# --------------------------------------------------------------------------- data sources
DATASETS = {
    "retrieved": "2026-10-22",
    "dem": {
        "project": "NH_Coastal_2019_B19",
        "tile_url": "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/"
        "NH_Coastal_2019_B19/TIFF/USGS_1M_19_x{x}y{y}_NH_Coastal_2019_B19.tif",
        # 10 km UTM tiles; tiles are picked from the area bounds and checked by reading bounds
    },
    "ept": [  # tried in order; the first that returns points for the detail box is used
        "https://usgs-lidar-public.s3.amazonaws.com/NH_Coastal_2_2019/",
        "https://usgs-lidar-public.s3.amazonaws.com/NH_Coastal_1_2019/",
    ],
    "overture_release": "release/2026-10-21.0",
    "nhd_gpkg": "NHD_H_01070006_HU8_GPKG.gpkg",  # Merrimack HU8 (covers Manchester)
    "nhd_url": "https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHD/HU8/GPKG/"
    "NHD_H_01070006_HU8_GPKG.zip",
    "struct_gpkg": "STRUCT_New_Hampshire_State_GPKG.gpkg",
    "struct_url": "https://prd-tnm.s3.amazonaws.com/StagedProducts/Struct/GPKG/"
    "STRUCT_New_Hampshire_State_GPKG.zip",
    "google_3d_tiles": False,  # only if Edward sets the key in Blender's preferences himself
}

# --------------------------------------------------------------------------- centre
# The centre is resolved, never typed in. A seed box (from the USGS Structures airport fire
# station, zip 03103) bounds the search; the centre is the Overture terminal building that
# contains the "1 Airport Rd" tenant places, and it is checked against the Overture airport
# place and every USGS structure on airport property. Distances go into meta.json/README.
CENTER_RESOLVE = {
    "address": "1 Airport Road, Manchester, NH 03103",
    "seed_struct": {"name_contains": "Airport", "zipcode": "03103"},
    "seed_pad_deg": 0.02,
    "overture_place_names": ["Manchester-Boston Regional Airport"],
    "overture_address": "1 airport r",
    "terminal_building": {"name": "Terminal Building"},
}

# Detail area = these footprints buffered by FRAME["detail_radius_m"]
DETAIL = {
    "buildings": [
        {"name": "Terminal Building"},
        {"class": "parking", "near_terminal_m": 250},  # parking garage (bridge end)
    ]
}

# --------------------------------------------------------------------------- sites
# Positions are resolved in pipeline/hvac_routes.py from footprints and 2019 lidar; nothing
# here is a coordinate. "kind" drives what is drawn.
SITES = [
    {
        "key": "ahu5",
        "title": "AHU-5",
        "where": "Terminal low (valley) roof, 1998 expansion",
        "kind": "roof_unit",
        "units": [{"tag": "AHU-5", "tons": 184, "weight_lb": 57900}],
        "roof": "light gray TPO (1998)",
        "notes": "184-ton custom packaged DX unit, ~57,900 lb, replaced in Phase 3.",
        "room": "erm_1077",
        "lay_out": "unit footprint, roof-edge distances, conduit route roof penetration to unit",
    },
    {
        "key": "rtu1_4",
        "title": "RTU-1 to RTU-4",
        "where": "Pedestrian bridge roof (terminal to garage)",
        "kind": "roof_unit",
        "units": [
            {"tag": "RTU-1", "tons": 6, "room": "erm_105"},
            {"tag": "RTU-2", "tons": 20, "room": "erm_105"},
            {"tag": "RTU-3", "tons": 20, "room": "erm_204"},
            {"tag": "RTU-4", "tons": 20, "room": "erm_204"},
        ],
        "roof": "black EPDM (2000)",
        "lay_out": "unit spots, roof hatch, conduit riser points, roof-edge distances",
    },
    {
        "key": "rtu5",
        "title": "RTU-5",
        "where": "Bridge roof over the terminal curb roadway",
        "kind": "roof_unit",
        "units": [{"tag": "RTU-5", "tons": 12.5, "room": "erm_103"}],
        "notes": "Replaced at night with Airport Road closure 1:30 to 4:00 AM.",
        "lay_out": "unit spot, crane pick zone, road closure area",
    },
    {
        "key": "erooms",
        "title": "Electrical rooms",
        "kind": "interior_placeholder",
        "notes": "Interior locations are not in public data. Placeholders only.",
    },
    {
        "key": "crane",
        "title": "Crane staging",
        "where": "Airside ramp next to the terminal (location per AmeriTech / airport ops)",
        "kind": "staging",
        "notes": "Daylight picks, possibly weekends.",
    },
]

# Electrical rooms: interior, so placeholders. "floor" is the level used for the riser
# arithmetic; the building is the footprint the placeholder sits in.
ROOMS = {
    "erm_1076": {
        "label": "Terminal Main Electrical Room #1076",
        "building": "terminal",
        "floor": "ground",
    },
    "erm_1077": {
        "label": "Terminal Main Electrical Room #1077 (SWBD E)",
        "building": "terminal",
        "floor": "ground",
    },
    "erm_103": {
        "label": "Ground Floor Electrical Room #103 (panel M1)",
        "building": "terminal",
        "floor": "ground",
    },
    "erm_105": {
        "label": "Ground Floor Electrical Room #105 (panel M3)",
        "building": "terminal",
        "floor": "ground",
    },
    "erm_204": {
        "label": "Pedestrian Bridge Electrical Room #204 (panel M2)",
        "building": "bridge",
        "floor": "bridge",
    },
}

# Feeders per single lines E-1 / E-2 (bid package). No run lengths are shown anywhere in it.
FEEDERS = [
    {
        "unit": "AHU-5",
        "room": "erm_1077",
        "source": "SWBD E",
        "conductors": "(2)[3-250 kcmil + 1#2 GND in 3in]",
        "ocpd_a": 500,
        "parallel_sets": 2,
    },
    {
        "unit": "RTU-1",
        "room": "erm_105",
        "source": "Panel M3",
        "conductors": "3#10 + 1#10 in 1in",
        "ocpd_a": 25,
        "parallel_sets": 1,
    },
    {
        "unit": "RTU-2",
        "room": "erm_105",
        "source": "Panel M3",
        "conductors": "3#6 + 1#8 in 1in",
        "ocpd_a": 60,
        "parallel_sets": 1,
    },
    {
        "unit": "RTU-3",
        "room": "erm_204",
        "source": "Panel M2",
        "conductors": "3#6 + 1#8 in 1in",
        "ocpd_a": 60,
        "parallel_sets": 1,
    },
    {
        "unit": "RTU-4",
        "room": "erm_204",
        "source": "Panel M2",
        "conductors": "3#8 + 1#10 in 1in",
        "ocpd_a": 45,
        "parallel_sets": 1,
    },
    {
        "unit": "RTU-5",
        "room": "erm_103",
        "source": "Panel M1",
        "conductors": "3#8 + 1#10 in 1in",
        "ocpd_a": 40,
        "parallel_sets": 1,
    },
]

# Current estimate assumptions to confirm or replace (Edward's estimate, ft)
ESTIMATE_ASSUMED_FT = {"erm_103": 120, "erm_105": 120, "erm_204": 60, "erm_1077": 250}

KNOWN_FACTS = [
    ("Upper terminal roof height", "approx. 34 ft", "bid package GP-1 note"),
    ("AHU-5 roof", "light gray TPO, 1998", "bid package"),
    ("Bridge roof (RTU-1 to RTU-4)", "black EPDM, 2000", "bid package"),
    ("RTU-5 night work", "Airport Road closure 1:30 to 4:00 AM", "bid package"),
]

# --------------------------------------------------------------------------- analysis
ANALYSIS = {
    "module": "hvac_routes",
    "unit_detect": {  # rooftop equipment = lidar blobs standing above the fitted roof surface
        "min_height_m": 0.9,
        "max_height_m": 4.5,
        "min_area_m2": 2.0,
        "cell_m": 0.5,
    },
    "roof_edge_setback_ft": [
        6,
        10,
    ],  # OSHA 1926.501 / 1910.28 fall-protection distances to show
}

# --------------------------------------------------------------------------- security
# FAA AIP / IIJA, airport: private viewer only. Nothing below may appear in any output.
REDACT = {
    "place_name_terms": [
        "gate",
        "security",
        "tsa",
        "checkpoint",
        "sida",
        "police",
        "camera",
        "cctv",
        "badge",
        "customs",
        "screening",
    ],
    "place_categories": ["police_station", "security_systems_service"],
    "infrastructure_classes": [
        "gate",
        "barrier",
        "fence",
        "camera",
        "surveillance",
        "lift_gate",
        "bollard",
    ],
    "aeroway_classes": ["gate", "jet_bridge", "holding_position", "parking_position"],
    "no_pricing": True,
}

# --------------------------------------------------------------------------- field photos
# Pre-bid walk photos (iPhone, Drive folder "1_zLdl...", 82 HEIC, 2026-10-22 12:40-12:46).
# Only the roof-equipment shots are listed; position and heading are the photo's own EXIF
# (GPS horizontal accuracy in metres, heading true). The photo files are NOT in the repo
# (security-sensitive site); only this metadata is.
FIELD_PHOTOS = {
    "source": "Pre-bid walk photos, 2026-10-22 (82 iPhone HEIC in the job Drive folder)",
    "match_max_deg": 12,  # compass + GPS error: a unit within this of the heading is a match
    "summary": "78 of the 82 photos are interior walk-through shots (baggage claim, the glass "
    "connector, ticketing hall) and the curb/garage approach. They show ceilings and finishes "
    "but no electrical equipment, panels or nameplates. Four show rooftop units from the curb.",
    "photos": [
        {
            "name": "IMG_5254",
            "time": "2026-10-22 12:46:01",
            "lat": 42.927728,
            "lon": -71.438644,
            "heading": 331.8,
            "hacc_m": 16.5,
            "subject": "Packaged RTU on the bridge roof, garage end (wide)",
        },
        {
            "name": "IMG_5255",
            "time": "2026-10-22 12:46:06",
            "lat": 42.927719,
            "lon": -71.438636,
            "heading": 328.8,
            "hacc_m": 8.2,
            "subject": "YORK packaged RTU: unit-mounted disconnect with conduit down the "
            "cabinet side, gas piping at the base, two condenser coil sections",
        },
        {
            "name": "IMG_5256",
            "time": "2026-10-22 12:46:29",
            "lat": 42.927733,
            "lon": -71.438606,
            "heading": 55.8,
            "hacc_m": 13.3,
            "subject": "Unit above the bridge parapet at the terminal end; lightning-"
            "protection air terminals on the roof edge either side of it",
        },
        {
            "name": "IMG_5257",
            "time": "2026-10-22 12:46:31",
            "lat": 42.927733,
            "lon": -71.438614,
            "heading": 56.4,
            "hacc_m": 12.6,
            "subject": "Same unit, wider: sits behind the parapet above the curb canopy",
        },
    ],
}

# --------------------------------------------------------------------------- viewer
VIEWER = {
    "page_title": "MHT Terminal HVAC Model",
    "brand": "MHT terminal HVAC · Job #1988",
    "sub": "Electrical routes check · 2019 USGS lidar · UTM 19N / NAVD88 · feet · PRIVATE",
    "loading": "Loading the MHT terminal model…",
    "aria": "3D model of the MHT terminal roofs. Drag to orbit, scroll to zoom.",
    "overview_title": "MHT terminal, rooftop HVAC units",
    "max_mb": 16,
}

TOUR = "web/tour.json"
