import json
from pathlib import Path
from decimal import Decimal

import boto3


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

TABLE_NAME = "yelp-restaurants"
REGION = "us-east-1"

# The JSON lives in the same folder as this script,
# so this works even if you run Python from the repo root.
SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FILE = SCRIPT_DIR / "manhattan_restaurants_1000_final.json"


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

print("Loading:", INPUT_FILE)

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    restaurants = json.load(
        f,
        parse_float=Decimal
    )


print("Restaurants loaded:", len(restaurants))


# --------------------------------------------------
# VALIDATE DATA
# --------------------------------------------------

if len(restaurants) != 1000:
    raise ValueError(
        f"Expected 1000 restaurants, found {len(restaurants)}"
    )


required_fields = {
    "business_id",
    "name",
    "cuisine",
    "address",
    "coordinates",
    "review_count",
    "rating",
    "zip_code",
    "insertedAtTimestamp"
}


business_ids = set()


for index, restaurant in enumerate(restaurants, start=1):

    missing = required_fields - restaurant.keys()

    if missing:
        raise ValueError(
            f"Restaurant #{index} is missing fields: {missing}"
        )

    business_id = restaurant["business_id"]

    if business_id in business_ids:
        raise ValueError(
            f"Duplicate business_id found: {business_id}"
        )

    business_ids.add(business_id)


print("Validation passed.")
print("Unique business IDs:", len(business_ids))


# --------------------------------------------------
# CONNECT TO DYNAMODB
# --------------------------------------------------

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

table = dynamodb.Table(TABLE_NAME)


# Make sure the table actually exists before uploading
print("\nChecking DynamoDB table...")

table.load()

print(
    "Connected to:",
    TABLE_NAME,
    "| Status:",
    table.table_status
)


# --------------------------------------------------
# UPLOAD ALL 1000
# --------------------------------------------------

print("\nUploading restaurants...")

uploaded = 0


# batch_writer automatically handles batching and retries.
# overwrite_by_pkeys makes rerunning the script safe:
# the same business_id is overwritten instead of duplicated.
with table.batch_writer(
    overwrite_by_pkeys=["business_id"]
) as batch:

    for restaurant in restaurants:

        batch.put_item(
            Item=restaurant
        )

        uploaded += 1

        if uploaded % 100 == 0:
            print(
                f"Uploaded {uploaded}/1000"
            )


# --------------------------------------------------
# DONE
# --------------------------------------------------

print("\nUpload complete.")
print("Restaurants uploaded:", uploaded)
print("Table:", TABLE_NAME)
print("Region:", REGION)