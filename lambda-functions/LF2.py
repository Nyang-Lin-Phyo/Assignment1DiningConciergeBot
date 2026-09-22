import json
import boto3
import random

TABLE_NAME = "yelp-restaurants"
REGION = "us-east-1"

# Replace this with the email address you verified in SES
SOURCE_EMAIL = "0monsuno82@gmail.com"

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

table = dynamodb.Table(TABLE_NAME)

ses = boto3.client(
    "ses",
    region_name=REGION
)


def lambda_handler(event, context):

    # Accept fake SQS-shaped event or direct event
    if "Records" in event:
        body = json.loads(event["Records"][0]["body"])
    else:
        body = event

    cuisine = body.get("cuisine", "Japanese")
    email = body.get("email")

    if not email:
        return {
            "statusCode": 400,
            "message": "Missing email address"
        }

    # TEMPORARY:
    # Scan DynamoDB directly.
    # OpenSearch will replace this later.
    response = table.scan()

    matching = [
        item
        for item in response.get("Items", [])
        if item.get("cuisine") == cuisine
    ]

    if not matching:
        return {
            "statusCode": 404,
            "message": f"No restaurants found for {cuisine}"
        }

    restaurant = random.choice(matching)

    subject = f"Your {cuisine} Restaurant Recommendation"

    message = (
        f"Hello!\n\n"
        f"Here is your {cuisine} restaurant recommendation:\n\n"
        f"{restaurant['name']}\n"
        f"Address: {restaurant['address']}\n"
        f"Rating: {restaurant['rating']}\n"
        f"Reviews: {restaurant['review_count']}\n\n"
        f"Enjoy your meal!"
    )

    ses_response = ses.send_email(
        Source=SOURCE_EMAIL,
        Destination={
            "ToAddresses": [email]
        },
        Message={
            "Subject": {
                "Data": subject
            },
            "Body": {
                "Text": {
                    "Data": message
                }
            }
        }
    )

    return {
        "statusCode": 200,
        "message": "Recommendation email sent successfully",
        "email": email,
        "restaurant": {
            "name": restaurant["name"],
            "cuisine": restaurant["cuisine"],
            "address": restaurant["address"],
            "rating": str(restaurant["rating"]),
            "review_count": int(restaurant["review_count"])
        },
        "sesMessageId": ses_response["MessageId"]
    }