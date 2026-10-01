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
# CONFIGURATION
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
    "nl2993@nyu.edu"
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
# CUISINE NORMALIZATION
# ============================================================

def normalize_cuisine(cuisine):

    if not cuisine:
        return None

    value = str(cuisine).strip().lower()

    mapping = {
        "american": "American",
        "italian": "Italian",
        "japanese": "Japanese",
        "chinese": "Chinese",
        "pizza": "Pizza"
    }

    return mapping.get(value)


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(value):

    if value is None:
        return ""

    return str(value).strip().lower()


# ============================================================
# SIGNED OPENSEARCH REQUEST
# ============================================================

def opensearch_request(method, path, body=None):

    if not OPENSEARCH_ENDPOINT:
        raise RuntimeError(
            "OPENSEARCH_ENDPOINT environment variable is not configured."
        )

    endpoint = OPENSEARCH_ENDPOINT.rstrip("/")
    url = endpoint + path

    data = None

    headers = {
        "Content-Type": "application/json"
    }

    if body is not None:
        data = json.dumps(body).encode("utf-8")

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
                response
                .read()
                .decode("utf-8")
            )

            if not response_body:
                return {}

            return json.loads(response_body)

    except HTTPError as error:

        error_body = (
            error
            .read()
            .decode("utf-8")
        )

        print(
            "OpenSearch HTTP error:",
            error.code
        )

        print(error_body)

        raise


# ============================================================
# GET RESTAURANT IDS FROM OPENSEARCH
# ============================================================

def get_restaurant_ids(cuisine, count=3):

    print(
        f"Searching OpenSearch for cuisine: {cuisine}"
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
# GET FULL RESTAURANTS FROM DYNAMODB
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

        item = response.get("Item")

        if item:
            restaurants.append(item)

    print(
        f"DynamoDB returned "
        f"{len(restaurants)} restaurants."
    )

    return restaurants


# ============================================================
# BUILD EMAIL BODY
# ============================================================

def build_email_body(
    request_data,
    restaurants
):

    cuisine = request_data["cuisine"]
    people = request_data["number_people"]
    date = request_data["date"]
    dining_time = request_data["time"]

    lines = [
        "Hello!",
        "",
        (
            f"Here are my {cuisine} restaurant "
            f"suggestions for {people} people, "
            f"for {date} at {dining_time}:"
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
# SAVE EXTRA-CREDIT USER STATE
# ============================================================

def save_user_state(
    request_data,
    restaurants
):

    email = normalize_text(
        request_data.get("email")
    )

    location = normalize_text(
        request_data.get("location")
    )

    cuisine = normalize_text(
        request_data.get("cuisine")
    )

    recommendation_list = []

    for restaurant in restaurants:

        recommendation_list.append({
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
                "rating"
            ),
            "review_count": restaurant.get(
                "review_count"
            )
        })

    state_table.put_item(
        Item={
            "email": email,
            "lastLocation": location,
            "lastCuisine": cuisine,
            "lastRecommendations": recommendation_list,
            "updatedAt": datetime.now(
                timezone.utc
            ).isoformat()
        }
    )

    print(
        "Saved user recommendation to "
        "dining-user-state."
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
# VALIDATE / PARSE SQS REQUEST
# ============================================================

def parse_request(body):

    print(
        "Received raw SQS request:"
    )

    print(
        json.dumps(
            body,
            indent=2
        )
    )

    raw_cuisine = body.get(
        "cuisine"
    )

    cuisine = normalize_cuisine(
        raw_cuisine
    )

    request_data = {
        "location": body.get(
            "location"
        ),
        "cuisine": cuisine,
        "date": body.get(
            "date"
        ),
        "time": body.get(
            "time"
        ),
        "number_people": body.get(
            "number_people"
        ),
        "email": body.get(
            "email"
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

    if not request_data["location"]:

        raise ValueError(
            "SQS request does not contain location."
        )

    if not cuisine:

        raise ValueError(
            f"Unsupported cuisine: {raw_cuisine}. "
            "Supported cuisines are American, "
            "Italian, Japanese, Chinese, and Pizza."
        )

    if not request_data["date"]:

        raise ValueError(
            "SQS request does not contain date."
        )

    if not request_data["time"]:

        raise ValueError(
            "SQS request does not contain time."
        )

    if not request_data["number_people"]:

        raise ValueError(
            "SQS request does not contain number_people."
        )

    if not request_data["email"]:

        raise ValueError(
            "SQS request does not contain email."
        )

    return request_data


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    print(
        "========== LF2 START =========="
    )

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
            "message": "No SQS messages available"
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
    # 2. PARSE JSON BODY
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
    # 3. PARSE FLAT LF1 MESSAGE
    # --------------------------------------------------------

    request_data = parse_request(
        body
    )

    cuisine = request_data[
        "cuisine"
    ]

    # --------------------------------------------------------
    # 4. QUERY OPENSEARCH
    # --------------------------------------------------------

    restaurant_ids = get_restaurant_ids(
        cuisine,
        count=3
    )

    # --------------------------------------------------------
    # 5. GET RESTAURANT DETAILS FROM DYNAMODB
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
    # 6. SEND EMAIL
    # --------------------------------------------------------

    ses_message_id = send_email(
        request_data["email"],
        request_data,
        restaurants
    )

    # --------------------------------------------------------
    # 7. SAVE EXTRA-CREDIT STATE
    # --------------------------------------------------------

    state_saved = False

    try:

        save_user_state(
            request_data,
            restaurants
        )

        state_saved = True

    except Exception as error:

        # The normal recommendation succeeded.
        # Do not leave the SQS message around and cause
        # duplicate emails just because state storage failed.

        print(
            "WARNING: Could not save "
            "extra-credit user state:"
        )

        print(str(error))

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
        "email": request_data["email"],
        "location": request_data["location"],
        "cuisine": cuisine,
        "restaurants": restaurant_summary,
        "sesMessageId": ses_message_id,
        "stateSaved": state_saved
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