import json
import os
import random
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timezone

import boto3
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

RESTAURANTS_TABLE = os.environ.get(
    "RESTAURANTS_TABLE",
    "yelp-restaurants"
)

STATE_TABLE_NAME = os.environ.get(
    "STATE_TABLE_NAME",
    "dining-user-state"
)

SES_FROM_EMAIL = os.environ.get(
    "SES_FROM_EMAIL",
    "av4008@nyu.edu"
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

restaurants_table = dynamodb.Table(
    RESTAURANTS_TABLE
)

state_table = dynamodb.Table(
    STATE_TABLE_NAME
)

ses = boto3.client(
    "ses",
    region_name=REGION
)


# ============================================================
# HELPERS
# ============================================================

def get_slot_value(slots, slot_name):
    """
    Read a Lex V2 slot value.
    """

    slot = slots.get(slot_name)

    if not slot:
        return None

    value = slot.get("value")

    if not value:
        return None

    return (
        value.get("interpretedValue")
        or value.get("originalValue")
    )


def normalize(value):

    if value is None:
        return ""

    return str(value).strip().lower()


def normalize_cuisine(value):

    if not value:
        return None

    mapping = {
        "american": "American",
        "italian": "Italian",
        "japanese": "Japanese",
        "chinese": "Chinese",
        "pizza": "Pizza"
    }

    return mapping.get(
        normalize(value)
    )


# ============================================================
# OPENSEARCH REQUEST
# ============================================================

def opensearch_request(method, path, body=None):

    if not OPENSEARCH_ENDPOINT:
        raise RuntimeError(
            "OPENSEARCH_ENDPOINT environment variable "
            "is not configured."
        )

    url = (
        OPENSEARCH_ENDPOINT.rstrip("/")
        + path
    )

    data = None

    headers = {
        "Content-Type": "application/json"
    }

    if body is not None:
        data = json.dumps(
            body
        ).encode("utf-8")

    credentials = (
        boto3.Session()
        .get_credentials()
        .get_frozen_credentials()
    )

    aws_request = AWSRequest(
        method=method,
        url=url,
        data=data,
        headers=headers
    )

    SigV4Auth(
        credentials,
        "es",
        REGION
    ).add_auth(
        aws_request
    )

    prepared = aws_request.prepare()

    request = urllib.request.Request(
        url=url,
        data=data,
        headers=dict(
            prepared.headers
        ),
        method=method
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=10
        ) as response:

            response_body = (
                response
                .read()
                .decode("utf-8")
            )

            if not response_body:
                return {}

            return json.loads(
                response_body
            )

    except HTTPError as error:

        body = (
            error
            .read()
            .decode("utf-8")
        )

        print(
            "OpenSearch HTTP error:",
            error.code
        )

        print(body)

        raise


# ============================================================
# GET RANDOM RESTAURANTS FROM OPENSEARCH
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
# DYNAMODB RESTAURANT LOOKUP
# ============================================================

def get_restaurants_from_dynamodb(
    restaurant_ids
):

    restaurants = []

    for restaurant_id in restaurant_ids:

        response = restaurants_table.get_item(
            Key={
                "business_id": restaurant_id
            }
        )

        item = response.get(
            "Item"
        )

        if item:
            restaurants.append(
                item
            )

    print(
        f"DynamoDB returned "
        f"{len(restaurants)} restaurants."
    )

    return restaurants


# ============================================================
# EMAIL
# ============================================================

def build_email_body(
    request_data,
    restaurants
):

    lines = [
        "Hello!",
        "",
        (
            f"Here are my "
            f"{request_data['cuisine']} restaurant "
            f"suggestions for "
            f"{request_data['number_people']} people, "
            f"for {request_data['date']} "
            f"at {request_data['time']}:"
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

        reviews = restaurant.get(
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
            f"   Reviews: {reviews}"
        )

        lines.append("")

    lines.append(
        "Enjoy your meal!"
    )

    return "\n".join(
        lines
    )


def send_email(
    recipient,
    request_data,
    restaurants
):

    if not SES_FROM_EMAIL:

        raise RuntimeError(
            "SES_FROM_EMAIL is not configured."
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
                "Data": (
                    f"Your "
                    f"{request_data['cuisine']} "
                    f"Restaurant Suggestions"
                )
            },
            "Body": {
                "Text": {
                    "Data": build_email_body(
                        request_data,
                        restaurants
                    )
                }
            }
        }
    )

    print(
        "SES Message ID:",
        response["MessageId"]
    )

    return response[
        "MessageId"
    ]


# ============================================================
# EXTRA CREDIT STATE
# ============================================================

def save_user_state(
    request_data,
    restaurants
):

    recommendations = []

    for restaurant in restaurants:

        recommendations.append({

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

            "rating": restaurant.get(
                "rating",
                "N/A"
            ),

            # IMPORTANT:
            # LF1 expects this field to be called "reviews".
            "reviews": restaurant.get(
                "review_count",
                "N/A"
            )
        })

    item = {

        # LF1 normalizes email before GetItem,
        # so LF2 must store the key normalized too.
        "email": normalize(
            request_data["email"]
        ),

        "lastLocation": normalize(
            request_data["location"]
        ),

        "lastCuisine": normalize(
            request_data["cuisine"]
        ),

        "lastRecommendations":
            recommendations,

        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat()
    }

    state_table.put_item(
        Item=item
    )

    print(
        "Saved recommendation state:"
    )

    print(
        json.dumps(
            {
                "email": item["email"],
                "lastLocation":
                    item["lastLocation"],
                "lastCuisine":
                    item["lastCuisine"],
                "recommendationCount":
                    len(recommendations),
                "updatedAt":
                    item["updatedAt"]
            },
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
# PARSE LF1 SQS MESSAGE
# ============================================================

def parse_request(body):

    print(
        "Raw SQS body:"
    )

    print(
        json.dumps(
            body,
            indent=2
        )
    )

    slots = body.get(
        "slots",
        {}
    )

    raw_cuisine = get_slot_value(
        slots,
        "Cussine"
    )

    cuisine = normalize_cuisine(
        raw_cuisine
    )

    request_data = {

        "location": get_slot_value(
            slots,
            "Location"
        ),

        "cuisine": cuisine,

        "date": get_slot_value(
            slots,
            "Date"
        ),

        "time": get_slot_value(
            slots,
            "Time"
        ),

        "number_people": get_slot_value(
            slots,
            "people_count"
        ),

        "email": get_slot_value(
            slots,
            "Email"
        )
    }

    print(
        "Parsed request:"
    )

    print(
        json.dumps(
            request_data,
            indent=2
        )
    )

    if not request_data["location"]:
        raise ValueError(
            "Missing Location slot."
        )

    if not request_data["cuisine"]:
        raise ValueError(
            f"Unsupported or missing cuisine: "
            f"{raw_cuisine}"
        )

    if not request_data["date"]:
        raise ValueError(
            "Missing Date slot."
        )

    if not request_data["time"]:
        raise ValueError(
            "Missing Time slot."
        )

    if not request_data[
        "number_people"
    ]:
        raise ValueError(
            "Missing people_count slot."
        )

    if not request_data["email"]:
        raise ValueError(
            "Missing Email slot."
        )

    return request_data


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(
    event,
    context
):

    print(
        "========== LF2 START =========="
    )

    print(
        "Polling food_info SQS queue..."
    )

    # --------------------------------------------------------
    # 1. RECEIVE ONE SQS MESSAGE
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
        message.get(
            "MessageId"
        )
    )

    # --------------------------------------------------------
    # 2. PARSE JSON
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

    # --------------------------------------------------------
    # 3. PARSE LF1 / LEX SLOTS
    # --------------------------------------------------------

    request_data = parse_request(
        body
    )

    # --------------------------------------------------------
    # 4. OPENSEARCH
    # --------------------------------------------------------

    restaurant_ids = get_restaurant_ids(
        request_data["cuisine"],
        count=3
    )

    # --------------------------------------------------------
    # 5. DYNAMODB
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
    # 6. SES
    # --------------------------------------------------------

    ses_message_id = send_email(
        request_data["email"],
        request_data,
        restaurants
    )

    # --------------------------------------------------------
    # 7. EXTRA CREDIT STATE
    # --------------------------------------------------------

    state_saved = False

    try:

        save_user_state(
            request_data,
            restaurants
        )

        state_saved = True

    except Exception as error:

        # Recommendation already succeeded.
        # Do not send another email next minute just
        # because optional state storage failed.

        print(
            "WARNING: Could not save "
            "extra-credit state."
        )

        print(
            str(error)
        )

    # --------------------------------------------------------
    # 8. DELETE SQS MESSAGE
    # --------------------------------------------------------

    delete_sqs_message(
        receipt_handle
    )

    # --------------------------------------------------------
    # 9. RESPONSE
    # --------------------------------------------------------

    restaurant_summary = []

    for restaurant in restaurants:

        restaurant_summary.append({

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
            )
        })

    result = {

        "statusCode": 200,

        "message": (
            "Restaurant recommendation "
            "email sent successfully"
        ),

        "email":
            request_data["email"],

        "location":
            request_data["location"],

        "cuisine":
            request_data["cuisine"],

        "restaurants":
            restaurant_summary,

        "sesMessageId":
            ses_message_id,

        "stateSaved":
            state_saved
    }

    print(
        "LF2 completed successfully:"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )

    print(
        "========== LF2 END =========="
    )

    return result