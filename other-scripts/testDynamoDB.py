import boto3

TABLE_NAME = "yelp-restaurants"
REGION = "us-east-1"

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

table = dynamodb.Table(TABLE_NAME)

business_id = "j19dK4wX22MnVkqmxa-lWA"

response = table.get_item(
    Key={
        "business_id": business_id
    }
)

restaurant = response.get("Item")

if restaurant:
    print("Restaurant found!\n")
    print("Name:", restaurant["name"])
    print("Cuisine:", restaurant["cuisine"])
    print("Address:", restaurant["address"])
    print("Rating:", restaurant["rating"])
    print("Reviews:", restaurant["review_count"])
else:
    print("Restaurant not found.")