import json
import boto3
from decimal import Decimal

INPUT_FILE = "philly_restaurants_400_test.json"
TABLE_NAME = "yelp-restaurants"
REGION = "us-east-1"

# Load JSON and preserve decimal values in a DynamoDB-friendly way
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    restaurants = json.load(f, parse_float=Decimal)

# Only use 5 for the first test
test_restaurants = restaurants[:5]

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

table = dynamodb.Table(TABLE_NAME)

for restaurant in test_restaurants:
    table.put_item(Item=restaurant)

    print(
        "Uploaded:",
        restaurant["name"],
        "|",
        restaurant["business_id"]
    )

print("\nDone. Uploaded", len(test_restaurants), "restaurants.")