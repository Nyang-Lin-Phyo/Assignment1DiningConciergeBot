import json
import math
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone

import pandas as pd


# ==================================================
# FILES
# ==================================================

NYC_FILE = (
    "DOHMH_New_York_City_Restaurant_"
    "Inspection_Results_20260922.csv"
)

GOOGLE_FILE = "meta-New_York.json"

OUTPUT_FILE = "manhattan_restaurants_1000_final.json"


# ==================================================
# SETTINGS
# ==================================================

# We will test all of these.
#
# The script automatically chooses the FIRST FIVE
# cuisines in this order that have at least 200
# confident Google matches.
CANDIDATE_CUISINES = [
    "American",
    "Italian",
    "Japanese",
    "Chinese",
    "Mexican",
    "Pizza",
    "Coffee/Tea",
    "Bakery Products/Desserts",
    "French"
]

TARGET_PER_CUISINE = 200
NUMBER_OF_CUISINES = 5

MAX_DISTANCE_METERS = 150


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def normalize_text(value):
    if value is None or pd.isna(value):
        return ""

    value = str(value).upper()

    # Remove punctuation
    value = re.sub(r"[^A-Z0-9 ]", " ", value)

    # Collapse repeated spaces
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_address(value):
    value = normalize_text(value)

    replacements = {
        " AVE ": " AVENUE ",
        " ST ": " STREET ",
        " RD ": " ROAD ",
        " BLVD ": " BOULEVARD ",
        " PL ": " PLACE ",
        " PKWY ": " PARKWAY ",
        " HWY ": " HIGHWAY ",
    }

    padded = f" {value} "

    for old, new in replacements.items():
        padded = padded.replace(old, new)

    return re.sub(r"\s+", " ", padded).strip()


def similarity(a, b):
    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def haversine_meters(lat1, lon1, lat2, lon2):
    """
    Distance between two latitude/longitude points.
    """

    earth_radius = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


def grid_key(lat, lon):
    """
    Geographic bucket used to avoid comparing every
    NYC restaurant against every Google business.
    """

    return (
        round(lat, 3),
        round(lon, 3)
    )


def neighboring_keys(lat, lon):
    """
    Return nearby geographic buckets.
    """

    lat_key = round(lat, 3)
    lon_key = round(lon, 3)

    offsets = [
        -0.002,
        -0.001,
        0,
        0.001,
        0.002
    ]

    for lat_offset in offsets:
        for lon_offset in offsets:
            yield (
                round(lat_key + lat_offset, 3),
                round(lon_key + lon_offset, 3)
            )


def extract_google_street_address(address, business_name):
    """
    Google Local addresses normally look like:

    The Smith, 956 2nd Ave, New York, NY 10022

    We only want:
    956 2nd Ave
    """

    if not address:
        return ""

    parts = [
        part.strip()
        for part in str(address).split(",")
    ]

    if len(parts) < 2:
        return str(address)

    first_part = normalize_text(parts[0])
    clean_name = normalize_text(business_name)

    # First component is usually business name
    if (
        first_part == clean_name
        or similarity(first_part, clean_name) >= 0.75
    ):
        return parts[1]

    # Otherwise assume first component is street
    return parts[0]


# ==================================================
# 1. LOAD NYC DATA
# ==================================================

print("Loading NYC restaurant data...")

df = pd.read_csv(
    NYC_FILE,
    low_memory=False
)

print("Total inspection rows:", len(df))


# ==================================================
# 2. FILTER MANHATTAN + CANDIDATE CUISINES
# ==================================================

df["BORO"] = (
    df["BORO"]
    .astype(str)
    .str.strip()
)

df["CUISINE DESCRIPTION"] = (
    df["CUISINE DESCRIPTION"]
    .astype(str)
    .str.strip()
)

df = df[
    (df["BORO"].str.upper() == "MANHATTAN")
    & (
        df["CUISINE DESCRIPTION"]
        .isin(CANDIDATE_CUISINES)
    )
].copy()

print(
    "Relevant Manhattan inspection rows:",
    len(df)
)


# ==================================================
# 3. KEEP MOST RECENT RECORD FOR EACH CAMIS
# ==================================================

df["INSPECTION DATE"] = pd.to_datetime(
    df["INSPECTION DATE"],
    errors="coerce"
)

df = df.sort_values(
    "INSPECTION DATE",
    ascending=False
)

df = df.drop_duplicates(
    subset=["CAMIS"],
    keep="first"
)

print(
    "Unique CAMIS after inspection dedup:",
    len(df)
)


# ==================================================
# 4. REMOVE BAD / INCOMPLETE DATA
# ==================================================

df = df[
    df["CAMIS"].notna()
    & df["DBA"].notna()
    & df["BUILDING"].notna()
    & df["STREET"].notna()
    & df["ZIPCODE"].notna()
    & df["Latitude"].notna()
    & df["Longitude"].notna()
    & (df["Latitude"] != 0)
    & (df["Longitude"] != 0)
].copy()


# ==================================================
# 5. BUILD CLEAN NAME + ADDRESS
# ==================================================

df["clean_name"] = (
    df["DBA"]
    .apply(normalize_text)
)

df["full_address"] = (
    df["BUILDING"]
    .astype(str)
    .str.strip()
    + " "
    + df["STREET"]
    .astype(str)
    .str.strip()
)

df["clean_address"] = (
    df["full_address"]
    .apply(normalize_address)
)


# ==================================================
# 6. REMOVE SAME RESTAURANT WITH MULTIPLE CAMIS IDs
# ==================================================

before = len(df)

df = df.drop_duplicates(
    subset=[
        "clean_name",
        "clean_address"
    ],
    keep="first"
)

removed = before - len(df)

print(
    "Removed duplicate name/address records:",
    removed
)


# ==================================================
# 7. SHOW NYC CANDIDATE COUNTS
# ==================================================

print("\nNYC candidate counts:")

for cuisine in CANDIDATE_CUISINES:

    count = (
        df["CUISINE DESCRIPTION"]
        == cuisine
    ).sum()

    print(
        f"{cuisine}: {count}"
    )


# ==================================================
# 8. LOAD GOOGLE LOCAL METADATA
# ==================================================

print(
    "\nReading Google Local metadata..."
)

google_grid = {}

google_count = 0

with open(
    GOOGLE_FILE,
    "r",
    encoding="utf-8"
) as f:

    for line_number, line in enumerate(
        f,
        start=1
    ):

        try:
            place = json.loads(line)

        except json.JSONDecodeError:
            continue


        lat = place.get("latitude")
        lon = place.get("longitude")

        rating = place.get("avg_rating")

        review_count = place.get(
            "num_of_reviews"
        )


        if (
            lat is None
            or lon is None
            or rating is None
            or review_count is None
        ):
            continue


        try:
            lat = float(lat)
            lon = float(lon)

            rating = float(rating)
            review_count = int(review_count)

        except (
            ValueError,
            TypeError
        ):
            continue


        # Broad Manhattan geographic area
        if not (
            40.68 <= lat <= 40.90
            and -74.05 <= lon <= -73.90
        ):
            continue


        # Ignore obviously invalid values
        if (
            rating <= 0
            or review_count <= 0
        ):
            continue


        # Ignore explicitly permanently closed places
        state = str(
            place.get("state") or ""
        ).lower()

        if "permanently closed" in state:
            continue


        name = place.get("name") or ""
        address = place.get("address") or ""

        if not name:
            continue


        street_address = (
            extract_google_street_address(
                address,
                name
            )
        )


        google_record = {
            "name":
                name,

            "clean_name":
                normalize_text(name),

            "address":
                address,

            "clean_address":
                normalize_address(
                    street_address
                ),

            "latitude":
                lat,

            "longitude":
                lon,

            "rating":
                rating,

            "review_count":
                review_count,

            "gmap_id":
                place.get("gmap_id")
        }


        key = grid_key(
            lat,
            lon
        )

        google_grid.setdefault(
            key,
            []
        ).append(
            google_record
        )

        google_count += 1


        # Small progress indicator
        if line_number % 50000 == 0:
            print(
                "Processed Google lines:",
                line_number
            )


print(
    "\nGoogle Manhattan-area businesses loaded:",
    google_count
)


# ==================================================
# 9. MATCH NYC RESTAURANTS → GOOGLE
# ==================================================

print(
    "\nMatching NYC restaurants "
    "to Google Local businesses..."
)

all_matches = []


for _, row in df.iterrows():

    nyc_lat = float(
        row["Latitude"]
    )

    nyc_lon = float(
        row["Longitude"]
    )

    nyc_name = row[
        "clean_name"
    ]

    nyc_address = row[
        "clean_address"
    ]


    nearby_google = []

    for key in neighboring_keys(
        nyc_lat,
        nyc_lon
    ):

        nearby_google.extend(
            google_grid.get(
                key,
                []
            )
        )


    scored_candidates = []


    for google in nearby_google:

        distance = haversine_meters(
            nyc_lat,
            nyc_lon,
            google["latitude"],
            google["longitude"]
        )

        if distance > MAX_DISTANCE_METERS:
            continue


        name_score = similarity(
            nyc_name,
            google["clean_name"]
        )

        address_score = similarity(
            nyc_address,
            google["clean_address"]
        )

        distance_score = max(
            0,
            1 - (
                distance
                / MAX_DISTANCE_METERS
            )
        )


        total_score = (
            0.65 * name_score
            + 0.25 * address_score
            + 0.10 * distance_score
        )


        scored_candidates.append({
            "google":
                google,

            "distance":
                distance,

            "name_score":
                name_score,

            "address_score":
                address_score,

            "total_score":
                total_score
        })


    if not scored_candidates:
        continue


    scored_candidates.sort(
        key=lambda x: x[
            "total_score"
        ],
        reverse=True
    )


    best = scored_candidates[0]


    second_score = (
        scored_candidates[1]["total_score"]
        if len(scored_candidates) > 1
        else 0
    )


    margin = (
        best["total_score"]
        - second_score
    )


    # ==============================================
    # CONSERVATIVE MATCH RULES
    # ==============================================

    confident = False


    # Very close coordinates
    if (
        best["distance"] <= 35
        and best["name_score"] >= 0.60
        and best["total_score"] >= 0.65
    ):
        confident = True


    # Slightly farther -> require better name
    elif (
        best["distance"] <= 80
        and best["name_score"] >= 0.75
        and best["total_score"] >= 0.70
    ):
        confident = True


    # Farther still -> require excellent name
    elif (
        best["distance"] <= 150
        and best["name_score"] >= 0.90
        and best["total_score"] >= 0.75
    ):
        confident = True


    # Reject ambiguous matches
    if (
        confident
        and len(scored_candidates) > 1
        and margin < 0.05
    ):
        confident = False


    if not confident:
        continue


    google = best["google"]


    zipcode = str(
        row["ZIPCODE"]
    ).strip()

    if zipcode.endswith(".0"):
        zipcode = zipcode[:-2]


    match = {
        "business_id":
            str(
                row["CAMIS"]
            ).strip(),

        "name":
            str(
                row["DBA"]
            ).strip(),

        "cuisine":
            str(
                row[
                    "CUISINE DESCRIPTION"
                ]
            ).strip(),

        "address":
            str(
                row[
                    "full_address"
                ]
            ).strip(),

        "coordinates": {
            "latitude":
                nyc_lat,

            "longitude":
                nyc_lon
        },

        "review_count":
            google[
                "review_count"
            ],

        "rating":
            google[
                "rating"
            ],

        "zip_code":
            zipcode,

        # Internal matching info
        "_gmap_id":
            google["gmap_id"],

        "_match_score":
            best["total_score"],

        "_name_score":
            best["name_score"],

        "_distance":
            best["distance"]
    }


    all_matches.append(
        match
    )


# ==================================================
# 10. ENSURE ONE GOOGLE BUSINESS ISN'T USED TWICE
# ==================================================

all_matches.sort(
    key=lambda x: x[
        "_match_score"
    ],
    reverse=True
)

unique_matches = []

used_gmap_ids = set()

for match in all_matches:

    gmap_id = match[
        "_gmap_id"
    ]

    if (
        gmap_id
        and gmap_id
        in used_gmap_ids
    ):
        continue

    unique_matches.append(
        match
    )

    if gmap_id:
        used_gmap_ids.add(
            gmap_id
        )


# ==================================================
# 11. SHOW CONFIDENT MATCH COUNTS
# ==================================================

print(
    "\nConfident unique Google matches:"
)

match_counts = {}

for cuisine in CANDIDATE_CUISINES:

    count = sum(
        1
        for restaurant
        in unique_matches
        if restaurant["cuisine"]
        == cuisine
    )

    match_counts[
        cuisine
    ] = count

    marker = (
        "  OK"
        if count >= TARGET_PER_CUISINE
        else ""
    )

    print(
        f"{cuisine}: "
        f"{count}"
        f"{marker}"
    )


# ==================================================
# 12. AUTOMATICALLY CHOOSE FIVE CUISINES
# ==================================================

selected_cuisines = [
    cuisine
    for cuisine
    in CANDIDATE_CUISINES
    if (
        match_counts[cuisine]
        >= TARGET_PER_CUISINE
    )
][
    :NUMBER_OF_CUISINES
]


if (
    len(selected_cuisines)
    < NUMBER_OF_CUISINES
):
    print(
        "\nERROR:"
    )

    print(
        "Fewer than five cuisines "
        "have at least 200 confident matches."
    )

    print(
        "No final file was created."
    )

    exit()


print(
    "\nSelected final cuisines:"
)

for cuisine in selected_cuisines:
    print(
        "-",
        cuisine
    )


# ==================================================
# 13. SELECT BEST 200 MATCHES PER CUISINE
# ==================================================

final_restaurants = []

used_business_ids = set()
used_name_addresses = set()
used_google_ids = set()


for cuisine in selected_cuisines:

    cuisine_matches = [
        restaurant
        for restaurant
        in unique_matches
        if restaurant["cuisine"]
        == cuisine
    ]


    # Best matches first
    cuisine_matches.sort(
        key=lambda restaurant: (
            restaurant[
                "_match_score"
            ],

            restaurant[
                "_name_score"
            ],

            -restaurant[
                "_distance"
            ]
        ),
        reverse=True
    )


    chosen = []


    for restaurant in cuisine_matches:

        business_id = (
            restaurant[
                "business_id"
            ]
        )

        name_address = (
            normalize_text(
                restaurant[
                    "name"
                ]
            ),

            normalize_address(
                restaurant[
                    "address"
                ]
            )
        )

        gmap_id = restaurant[
            "_gmap_id"
        ]


        if (
            business_id
            in used_business_ids
        ):
            continue


        if (
            name_address
            in used_name_addresses
        ):
            continue


        if (
            gmap_id
            and gmap_id
            in used_google_ids
        ):
            continue


        chosen.append(
            restaurant
        )

        used_business_ids.add(
            business_id
        )

        used_name_addresses.add(
            name_address
        )

        if gmap_id:
            used_google_ids.add(
                gmap_id
            )


        if (
            len(chosen)
            == TARGET_PER_CUISINE
        ):
            break


    if (
        len(chosen)
        < TARGET_PER_CUISINE
    ):
        print(
            "\nERROR:"
        )

        print(
            cuisine,
            "only produced",
            len(chosen),
            "unique final restaurants."
        )

        exit()


    final_restaurants.extend(
        chosen
    )


# ==================================================
# 14. CLEAN INTERNAL MATCHING FIELDS
# ==================================================

timestamp = (
    datetime.now(
        timezone.utc
    ).isoformat()
)


for restaurant in final_restaurants:

    google_id = restaurant.pop(
        "_gmap_id"
    )

    restaurant.pop(
        "_match_score"
    )

    restaurant.pop(
        "_name_score"
    )

    restaurant.pop(
        "_distance"
    )


    restaurant[
        "insertedAtTimestamp"
    ] = timestamp


    # Keep source information so we know
    # where rating/review_count came from.
    restaurant[
        "rating_source"
    ] = (
        "UCSD Google Local Data 2021"
    )

    restaurant[
        "rating_source_id"
    ] = google_id


# ==================================================
# 15. FINAL VALIDATION
# ==================================================

print(
    "\nFinal cuisine counts:"
)


for cuisine in selected_cuisines:

    count = sum(
        1
        for restaurant
        in final_restaurants
        if restaurant["cuisine"]
        == cuisine
    )

    print(
        f"{cuisine}: {count}"
    )


total = len(
    final_restaurants
)

unique_business_ids = len({
    restaurant["business_id"]
    for restaurant
    in final_restaurants
})

unique_name_addresses = len({
    (
        normalize_text(
            restaurant["name"]
        ),
        normalize_address(
            restaurant["address"]
        )
    )
    for restaurant
    in final_restaurants
})

unique_google_ids = len({
    restaurant[
        "rating_source_id"
    ]
    for restaurant
    in final_restaurants
})


missing_ratings = sum(
    restaurant["rating"]
    is None
    for restaurant
    in final_restaurants
)

missing_reviews = sum(
    restaurant["review_count"]
    is None
    for restaurant
    in final_restaurants
)


print(
    "\nTotal:",
    total
)

print(
    "Unique business IDs:",
    unique_business_ids
)

print(
    "Unique name/address pairs:",
    unique_name_addresses
)

print(
    "Unique Google IDs:",
    unique_google_ids
)

print(
    "Missing ratings:",
    missing_ratings
)

print(
    "Missing review counts:",
    missing_reviews
)


assert total == 1000

assert (
    unique_business_ids
    == 1000
)

assert (
    unique_name_addresses
    == 1000
)

assert (
    unique_google_ids
    == 1000
)

assert (
    missing_ratings
    == 0
)

assert (
    missing_reviews
    == 0
)


# ==================================================
# 16. SAVE FINAL DATASET
# ==================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        final_restaurants,
        f,
        indent=2,
        ensure_ascii=False
    )


print(
    "\nSUCCESS"
)

print(
    "Saved:",
    OUTPUT_FILE
)