import boto3
import json
import os
import random
import urllib.request

from datetime import datetime, timezone
from urllib.error import HTTPError

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


# ============================================================
# CONFIG
# ============================================================

REGION = "us-east-1"

QUEUE_URL = os.environ.get(
    "QUEUE_URL",
    "https://sqs.us-east-1.amazonaws.com/456157355328/food_info"
)

TABLE_NAME = os.environ.get(
    "RESTAURANTS_TABLE",
    "yelp-restaurants"
)

STATE_TABLE_NAME = os.environ.get(
    "STATE_TABLE_NAME",
    "dining-user-state"
)

SES_FROM_EMAIL = os.environ.get(
    "SES_FROM_EMAIL"
)

OPENSEARCH_ENDPOINT = os.environ.get(
    "OPENSEARCH_ENDPOINT"
)


# ============================================================
# AWS CLIENTS
# ============================================================

sqs = boto3.client(
    "sqs",
    region_name=REGION
)

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

# Main restaurant table
table = dynamodb.Table(TABLE_NAME)

# Extra-credit user state table
state_table = dynamodb.Table(
    STATE_TABLE_NAME
)

ses = boto3.client(
    "ses",
    region_name=REGION
)


# ============================================================
# SLOT HELPER
# ============================================================

def get_slot(slots, name):

    slot = slots.get(name)

    if not slot:
        return None

    value = slot.get("value", {})

    return (
        value.get("interpretedValue")
        or value.get("originalValue")
    )


# ============================================================
# CUISINE NORMALIZATION
# ============================================================

def normalize_cuisine(cuisine):

    if not cuisine:
        return None

    cuisine = cuisine.strip().lower()

    mapping = {
        "american": "American",
        "italian": "Italian",
        "japanese": "Japanese",
        "chinese": "Chinese",
        "pizza": "Pizza"
    }

    return mapping.get(cuisine)


# ============================================================
# SIGNED OPENSEARCH REQUEST
# ============================================================

def opensearch_request(method, path, body=None):

    if not OPENSEARCH_ENDPOINT:
        raise RuntimeError(
            "OPENSEARCH_ENDPOINT environment variable "
            "is not configured."
        )

    endpoint = OPENSEARCH_ENDPOINT.rstrip("/")
    url = endpoint + path

    data = None

    headers = {
        "Content-Type": "application/json"
    }

    if body is not None:
        data = json.dumps(body).encode("utf-8")

    # Lambda automatically gets credentials from
    # its execution role.
    credentials = (
        boto3.Session()
        .get_credentials()
        .get_frozen_credentials()
    )

    request = AWSRequest(
        method=method,
        url=url,
        data=data,
        headers=headers
    )

    SigV4Auth(
        credentials,
        "es",
        REGION
    ).add_auth(request)

    prepared = request.prepare()

    http_request = urllib.request.Request(
        url=url,
        data=data,
        headers=dict(prepared.headers),
        method=method
    )

    try:

        with urllib.request.urlopen(
            http_request,
            timeout=10
        ) as response:

            response_body = (
                response.read().decode("utf-8")
            )

            if not response_body:
                return {}

            return json.loads(
                response_body
            )

    except HTTPError as e:

        error_body = (
            e.read().decode("utf-8")
        )

        print("OpenSearch HTTP error:")
        print(error_body)

        raise


# ============================================================
# GET RESTAURANTS FROM OPENSEARCH
# ============================================================

def get_restaurant_ids(
    cuisine,
    count=3
):

    print(
        f"Searching OpenSearch for cuisine: "
        f"{cuisine}"
    )

    search_body = {
        "size": 200,
        "_source": [
            "RestaurantID",
            "Cuisine"
        ],
        "query": {
            "term": {
                "Cuisine": cuisine
            }
        }
    }

    result = opensearch_request(
        "POST",
        "/restaurants/Restaurant/_search",
        search_body
    )

    hits = (
        result
        .get("hits", {})
        .get("hits", [])
    )

    restaurant_ids = []

    for hit in hits:

        source = hit.get(
            "_source",
            {}
        )

        restaurant_id = source.get(
            "RestaurantID"
        )

        if restaurant_id:

            restaurant_ids.append(
                str(restaurant_id)
            )

    print(
        f"OpenSearch returned "
        f"{len(restaurant_ids)} restaurant IDs."
    )

    if len(restaurant_ids) < count:

        raise RuntimeError(
            f"Not enough {cuisine} restaurants "
            f"in OpenSearch. "
            f"Found {len(restaurant_ids)}."
        )

    selected = random.sample(
        restaurant_ids,
        count
    )

    print(
        "Selected restaurant IDs:",
        selected
    )

    return selected


# ============================================================
# GET FULL DATA FROM DYNAMODB
# ============================================================

def get_restaurants_from_dynamodb(
    restaurant_ids
):

    restaurants = []

    for restaurant_id in restaurant_ids:

        response = table.get_item(
            Key={
                "business_id": restaurant_id
            }
        )

        item = response.get(
            "Item"
        )

        if item:
            restaurants.append(item)

    print(
        f"DynamoDB returned "
        f"{len(restaurants)} restaurants."
    )

    return restaurants


# ============================================================
# BUILD EMAIL
# ============================================================

def build_email_body(
    request_data,
    restaurants
):

    cuisine = request_data["cuisine"]
    people = request_data["number_people"]
    date = request_data["date"]
    time = request_data["time"]

    lines = [
        "Hello!",
        "",
        (
            f"Here are my {cuisine} restaurant "
            f"suggestions for {people} people, "
            f"for {date} at {time}:"
        ),
        ""
    ]

    for index, restaurant in enumerate(
        restaurants,
        start=1
    ):

        name = restaurant.get(
            "name",
            "Unknown Restaurant"
        )

        address = restaurant.get(
            "address",
            "Address unavailable"
        )

        rating = restaurant.get(
            "rating",
            "N/A"
        )

        review_count = restaurant.get(
            "review_count",
            "N/A"
        )

        lines.append(
            f"{index}. {name}"
        )

        lines.append(
            f"   Address: {address}"
        )

        lines.append(
            f"   Rating: {rating}"
        )

        lines.append(
            f"   Reviews: {review_count}"
        )

        lines.append("")

    lines.append(
        "Enjoy your meal!"
    )

    return "\n".join(lines)


# ============================================================
# SEND EMAIL
# ============================================================

def send_email(
    recipient,
    request_data,
    restaurants
):

    if not SES_FROM_EMAIL:

        raise RuntimeError(
            "SES_FROM_EMAIL environment variable "
            "is not configured."
        )

    body = build_email_body(
        request_data,
        restaurants
    )

    subject = (
        f"Your {request_data['cuisine']} "
        f"Restaurant Suggestions"
    )

    response = ses.send_email(
        Source=SES_FROM_EMAIL,

        Destination={
            "ToAddresses": [
                recipient
            ]
        },

        Message={
            "Subject": {
                "Data": subject
            },

            "Body": {
                "Text": {
                    "Data": body
                }
            }
        }
    )

    print(
        "SES Message ID:",
        response["MessageId"]
    )

    return response["MessageId"]


# ============================================================
# SAVE USER'S LAST RECOMMENDATION
# ============================================================

def save_user_state(
    request_data,
    restaurants
):

    email = request_data["email"]

    location = request_data.get(
        "city"
    )

    cuisine = request_data.get(
        "cuisine"
    )

    if not email:
        raise ValueError(
            "Cannot save user state without email."
        )

    saved_restaurants = []

    for restaurant in restaurants:

        saved_restaurants.append({
            "business_id": str(
                restaurant.get(
                    "business_id",
                    ""
                )
            ),

            "name": str(
                restaurant.get(
                    "name",
                    ""
                )
            ),

            "address": str(
                restaurant.get(
                    "address",
                    ""
                )
            ),

            "rating": str(
                restaurant.get(
                    "rating",
                    ""
                )
            ),

            "reviews": str(
                restaurant.get(
                    "review_count",
                    ""
                )
            )
        })

    item = {
        "email": email.strip().lower(),

        "lastLocation": (
            location.strip().lower()
            if location
            else ""
        ),

        "lastCuisine": (
            cuisine.strip().lower()
            if cuisine
            else ""
        ),

        "lastRecommendations":
            saved_restaurants,

        "updatedAt":
            datetime.now(
                timezone.utc
            ).isoformat()
    }

    state_table.put_item(
        Item=item
    )

    print(
        "Saved user recommendation "
        "to dining-user-state."
    )

    print(
        json.dumps(
            item,
            indent=2
        )
    )


# ============================================================
# DELETE SQS MESSAGE
# ============================================================

def delete_sqs_message(
    receipt_handle
):

    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=receipt_handle
    )

    print(
        "SQS message successfully deleted."
    )


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    print(
        "Polling food_info SQS queue..."
    )

    # --------------------------------------------------------
    # 1. GET ONE SQS MESSAGE
    # --------------------------------------------------------

    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=2,
        VisibilityTimeout=60
    )

    messages = response.get(
        "Messages",
        []
    )

    if not messages:

        print(
            "No messages currently available."
        )

        return {
            "statusCode": 200,
            "message":
                "No SQS messages available"
        }

    message = messages[0]

    receipt_handle = message[
        "ReceiptHandle"
    ]

    print(
        "SQS Message ID:",
        message["MessageId"]
    )

    # --------------------------------------------------------
    # 2. PARSE MESSAGE BODY
    # --------------------------------------------------------

    try:

        body = json.loads(
            message["Body"]
        )

    except json.JSONDecodeError:

        print(
            "Invalid JSON in SQS message."
        )

        raise

    print(
        "Received request:"
    )

    print(
        json.dumps(
            body,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 3. EXTRACT LEX SLOTS
    # --------------------------------------------------------

    slots = body.get(
        "slots",
        {}
    )

    raw_cuisine = (
        get_slot(
            slots,
            "Cuisine"
        )
        or
        get_slot(
            slots,
            "Cusine"
        )
    )

    cuisine = normalize_cuisine(
        raw_cuisine
    )

    # Your friend's Lex currently calls
    # the location slot "city_man".
    # Supporting City as well keeps LF2 flexible.
    city = (
        get_slot(
            slots,
            "City"
        )
        or
        get_slot(
            slots,
            "city_man"
        )
    )

    request_data = {

        "city": city,

        "cuisine": cuisine,

        "date": (
            get_slot(
                slots,
                "Date"
            )
            or
            get_slot(
                slots,
                "date"
            )
        ),

        "time": get_slot(
            slots,
            "Time"
        ),

        "number_people": (
            get_slot(
                slots,
                "Number_people"
            )
            or
            get_slot(
                slots,
                "NumberPeople"
            )
        ),

        "email": get_slot(
            slots,
            "Email"
        )
    }

    print(
        "Parsed restaurant request:"
    )

    print(
        json.dumps(
            request_data,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 4. VALIDATE REQUEST
    # --------------------------------------------------------

    if not cuisine:

        raise ValueError(
            f"Unsupported cuisine: "
            f"{raw_cuisine}. "
            "Supported cuisines are "
            "American, Italian, Japanese, "
            "Chinese, and Pizza."
        )

    if not request_data["email"]:

        raise ValueError(
            "SQS request does not "
            "contain an email."
        )

    # --------------------------------------------------------
    # 5. QUERY OPENSEARCH
    # --------------------------------------------------------

    restaurant_ids = (
        get_restaurant_ids(
            cuisine,
            count=3
        )
    )

    # --------------------------------------------------------
    # 6. GET FULL RESTAURANTS FROM DYNAMODB
    # --------------------------------------------------------

    restaurants = (
        get_restaurants_from_dynamodb(
            restaurant_ids
        )
    )

    if len(restaurants) != 3:

        raise RuntimeError(
            "Could not retrieve all 3 "
            "restaurants from DynamoDB."
        )

    # --------------------------------------------------------
    # 7. SEND EMAIL USING SES
    # --------------------------------------------------------

    ses_message_id = send_email(
        request_data["email"],
        request_data,
        restaurants
    )

    # --------------------------------------------------------
    # 8. SAVE WHAT WAS ACTUALLY RECOMMENDED
    #
    # This is extra-credit state.
    #
    # We do this AFTER SES succeeds because these are the
    # restaurants that were actually sent to the user.
    # --------------------------------------------------------

    state_saved = False

    try:

        save_user_state(
            request_data,
            restaurants
        )

        state_saved = True

    except Exception as e:

        # Extra-credit state should not cause the normal
        # recommendation pipeline to send duplicate emails.
        print(
            "WARNING: Could not save "
            "dining-user-state:"
        )

        print(
            str(e)
        )

    # --------------------------------------------------------
    # 9. DELETE SQS MESSAGE AFTER EMAIL SUCCESS
    # --------------------------------------------------------

    delete_sqs_message(
        receipt_handle
    )

    # --------------------------------------------------------
    # 10. SUCCESS RESPONSE
    # --------------------------------------------------------

    restaurant_summary = []

    for restaurant in restaurants:

        restaurant_summary.append({

            "business_id":
                restaurant.get(
                    "business_id"
                ),

            "name":
                restaurant.get(
                    "name"
                ),

            "address":
                restaurant.get(
                    "address"
                ),

            "rating":
                str(
                    restaurant.get(
                        "rating"
                    )
                )
        })

    return {

        "statusCode": 200,

        "message":
            "Restaurant recommendation "
            "email sent successfully",

        "email":
            request_data["email"],

        "cuisine":
            cuisine,

        "restaurants":
            restaurant_summary,

        "sesMessageId":
            ses_message_id,

        "stateSaved":
            state_saved
    }