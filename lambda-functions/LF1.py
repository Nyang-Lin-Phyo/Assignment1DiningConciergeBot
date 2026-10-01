import json
import boto3


# ============================================================
# CONFIG
# ============================================================

REGION = "us-east-1"

QUEUE_URL = (
    "https://sqs.us-east-1.amazonaws.com/"
    "456157355328/food_info"
)

STATE_TABLE_NAME = "dining-user-state"

SES_FROM_EMAIL = "av4008@nyu.edu"


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

state_table = dynamodb.Table(
    STATE_TABLE_NAME
)

ses = boto3.client(
    "ses",
    region_name=REGION
)


# ============================================================
# HELPER: GET LEX SLOT VALUE
# ============================================================

def get_slot_value(slots, slot_name):

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


# ============================================================
# HELPER: NORMALIZE
# ============================================================

def normalize(value):

    if value is None:
        return None

    return str(value).strip().lower()


# ============================================================
# HELPER: CLOSE LEX INTENT
# ============================================================

def close_intent(
    intent,
    slots,
    message
):

    return {
        "sessionState": {

            "dialogAction": {
                "type": "Close"
            },

            "intent": {
                "name": intent,
                "slots": slots,
                "state": "Fulfilled"
            }
        },

        "messages": [
            {
                "contentType": "PlainText",
                "content": message
            }
        ]
    }


# ============================================================
# HELPER: SEND PREVIOUS RECOMMENDATIONS BY EMAIL
# ============================================================

def send_previous_recommendation_email(
    email,
    cuisine,
    date,
    time,
    number_people,
    restaurants
):

    lines = []

    lines.append("Hello!")
    lines.append("")

    lines.append(
        f"Here are the same {cuisine} restaurant "
        f"suggestions from your previous search."
    )

    if date or time or number_people:

        lines.append("")

        dining_info = "For"

        if number_people:
            dining_info += f" {number_people} people"

        if date:
            dining_info += f", on {date}"

        if time:
            dining_info += f" at {time}"

        dining_info += "."

        lines.append(dining_info)

    lines.append("")

    for index, restaurant in enumerate(
        restaurants,
        start=1
    ):

        name = restaurant.get(
            "name",
            "Unknown restaurant"
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
            "reviews",
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

    lines.append("Enjoy your meal!")

    body = "\n".join(lines)

    response = ses.send_email(

        Source=SES_FROM_EMAIL,

        Destination={
            "ToAddresses": [
                email
            ]
        },

        Message={

            "Subject": {
                "Data": (
                    f"Your {cuisine} Restaurant Suggestions"
                )
            },

            "Body": {

                "Text": {
                    "Data": body
                }

            }
        }
    )

    print(
        "Previous recommendation SES Message ID:",
        response.get("MessageId")
    )

    return response


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    print("========== LF1 START ==========")

    print(
        "Invocation source:",
        event.get("invocationSource")
    )

    # --------------------------------------------------------
    # Get intent
    # --------------------------------------------------------

    intent_data = (
        event
        .get("sessionState", {})
        .get("intent", {})
    )

    intent = intent_data.get(
        "name"
    )

    slots = intent_data.get(
        "slots",
        {}
    )

    print("Intent:", intent)
    print("Slots:", slots)


    # ========================================================
    # GREET
    # ========================================================

    if intent == "Greet":

        return close_intent(
            intent,
            slots,
            "Hello, can I help you find restaurants?"
        )


    # ========================================================
    # THANK
    # ========================================================

    if intent == "Thank":

        return close_intent(
            intent,
            slots,
            "You're welcome!"
        )


    # ========================================================
    # GET DINING SLOTS
    # ========================================================

    email = get_slot_value(
        slots,
        "Email"
    )

    location = get_slot_value(
        slots,
        "Location"
    )

    cuisine = get_slot_value(
        slots,
        "Cussine"
    )

    date = get_slot_value(
        slots,
        "Date"
    )

    dining_time = get_slot_value(
        slots,
        "Time"
    )

    number_people = get_slot_value(
        slots,
        "people_count"
    )

    use_previous = get_slot_value(
        slots,
        "UsePreviousRecommendation"
    )


    print("Email:", email)
    print("Location:", location)
    print("Cuisine:", cuisine)
    print("Date:", date)
    print("Time:", dining_time)
    print("Number people:", number_people)
    print("Use previous:", use_previous)


    # ========================================================
    # VALIDATE LOCATION
    # ========================================================

    if location is not None:

        normalized_location = normalize(
            location
        )

        if normalized_location != "manhattan":

            print(
                "Invalid location:",
                location
            )

            return {
                "sessionState": {

                    "dialogAction": {
                        "type": "ElicitSlot",
                        "slotToElicit": "Location"
                    },

                    "intent": {
                        "name": intent,
                        "slots": slots
                    }
                },

                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": (
                            "Sorry, I can't help with dining "
                            f"recommendations in {location}. "
                            "Please try Manhattan."
                        )
                    }
                ]
            }


    # ========================================================
    # VALIDATE CUISINE
    # ========================================================

    allowed_cuisines = {
        "american",
        "italian",
        "japanese",
        "chinese",
        "pizza"
    }

    if cuisine is not None:

        normalized_cuisine = normalize(
            cuisine
        )

        if normalized_cuisine not in allowed_cuisines:

            print(
                "Invalid cuisine:",
                cuisine
            )

            return {
                "sessionState": {

                    "dialogAction": {
                        "type": "ElicitSlot",
                        "slotToElicit": "Cussine"
                    },

                    "intent": {
                        "name": intent,
                        "slots": slots
                    }
                },

                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": (
                            "Sorry, I don't have "
                            f"{cuisine} recommendations. "
                            "Please choose American, Italian, "
                            "Japanese, Chinese, or pizza."
                        )
                    }
                ]
            }


    # ========================================================
    # CHECK REQUIRED SEARCH SLOTS
    # ========================================================

    required_slots = [

        "Email",

        "Location",

        "Cussine",

        "Date",

        "Time",

        "people_count"
    ]


    all_search_slots_collected = all(

        get_slot_value(
            slots,
            slot_name
        ) is not None

        for slot_name in required_slots
    )


    print(
        "All search slots collected:",
        all_search_slots_collected
    )


    # ========================================================
    # LEX STILL COLLECTING INFORMATION
    # ========================================================

    if not all_search_slots_collected:

        print(
            "Still collecting search information."
        )

        return {
            "sessionState": {

                "dialogAction": {
                    "type": "Delegate"
                },

                "intent": {
                    "name": intent,
                    "slots": slots
                }
            }
        }



    normalized_email = normalize(
        email
    )

    print(
        "Checking DynamoDB..."
    )

    print(
        "Table:",
        STATE_TABLE_NAME
    )

    print(
        "Region:",
        REGION
    )

    print(
        "Email key:",
        normalized_email
    )


    # --------------------------------------------------------
    # DynamoDB lookup
    # --------------------------------------------------------

    try:

        result = state_table.get_item(

            Key={
                "email": normalized_email
            }
        )

        print(
            "DynamoDB response:",
            result
        )

    except Exception as e:

        print(
            "========== DYNAMODB ERROR =========="
        )

        print(
            "Error type:",
            type(e).__name__
        )

        print(
            "Error:",
            str(e)
        )

        print(
            "===================================="
        )

        return close_intent(
            intent,
            slots,
            (
                "Sorry, I couldn't access your "
                "previous restaurant recommendations. "
                "Please try again."
            )
        )


    previous_search = result.get(
        "Item"
    )


    print(
        "Previous search:",
        previous_search
    )



    if not previous_search:

        print(
            "No previous search found."
        )

        print(
            "Sending new request directly to SQS."
        )



    else:

        previous_location = (
            previous_search.get(
                "lastLocation"
            )
        )

        previous_cuisine = (
            previous_search.get(
                "lastCuisine"
            )
        )

        previous_recommendations = (
            previous_search.get(
                "lastRecommendations",
                []
            )
        )


        print(
            "Previous location:",
            previous_location
        )

        print(
            "Previous cuisine:",
            previous_cuisine
        )

        print(
            "Previous recommendations:",
            previous_recommendations
        )


        # ----------------------------------------------------
        # Compare current search with previous search
        # ----------------------------------------------------

        same_search = (

            normalize(
                previous_location
            )
            ==
            normalize(
                location
            )

            and

            normalize(
                previous_cuisine
            )
            ==
            normalize(
                cuisine
            )
        )


        print(
            "Same search:",
            same_search
        )


        # ====================================================
        # SAME LOCATION + SAME CUISINE
        # ====================================================

        if (
            same_search
            and previous_recommendations
        ):


            # ------------------------------------------------
            # We have NOT asked the user yet
            # ------------------------------------------------

            if use_previous is None:

                print(
                    "Same search detected."
                )

                print(
                    "Asking whether to reuse "
                    "previous recommendations."
                )


                return {

                    "sessionState": {

                        "dialogAction": {

                            "type": "ElicitSlot",

                            "slotToElicit":
                                "UsePreviousRecommendation"
                        },

                        "intent": {

                            "name": intent,

                            "slots": slots
                        }
                    },

                    "messages": [

                        {
                            "contentType":
                                "PlainText",

                            "content": (
                                "I found the same location "
                                "and cuisine from your previous "
                                "search. Would you like the same "
                                "recommendations as last time?"
                            )
                        }

                    ]
                }


            # ------------------------------------------------
            # User answered YES
            # ------------------------------------------------

            normalized_answer = normalize(
                use_previous
            )


            if normalized_answer in [

                "yes",
                "yeah",
                "yep",
                "sure"

            ]:

                print(
                    "User wants previous recommendations."
                )


                try:

                    send_previous_recommendation_email(

                        email=email,

                        cuisine=cuisine,

                        date=date,

                        time=dining_time,

                        number_people=number_people,

                        restaurants=previous_recommendations
                    )


                except Exception as e:

                    print(
                        "========== SES ERROR =========="
                    )

                    print(
                        "Error type:",
                        type(e).__name__
                    )

                    print(
                        "Error:",
                        str(e)
                    )

                    print(
                        "================================"
                    )

                    return close_intent(
                        intent,
                        slots,
                        (
                            "Sorry, I couldn't send "
                            "your previous recommendations."
                        )
                    )


                return close_intent(

                    intent,

                    slots,

                    (
                        "Sure! I sent your previous "
                        "restaurant recommendations "
                        "to your email."
                    )
                )


            # ------------------------------------------------
            # User answered NO
            # ------------------------------------------------

            if normalized_answer in [

                "no",
                "nope"

            ]:

                print(
                    "User wants NEW recommendations."
                )

                # Continue below to SQS.

    message = {

        "intent": intent,

        "slots": slots
    }


    print(
        "Sending message to SQS:"
    )

    print(
        json.dumps(
            message,
            indent=2
        )
    )


    try:

        response = sqs.send_message(

            QueueUrl=QUEUE_URL,

            MessageBody=json.dumps(
                message
            )
        )


        print(
            "SQS Message ID:",
            response.get(
                "MessageId"
            )
        )


    except Exception as e:

        print(
            "========== SQS ERROR =========="
        )

        print(
            "Error type:",
            type(e).__name__
        )

        print(
            "Error:",
            str(e)
        )

        print(
            "================================"
        )

        return close_intent(
            intent,
            slots,
            (
                "Sorry, I couldn't submit "
                "your restaurant request. "
                "Please try again."
            )
        )

    return close_intent(

        intent,

        slots,

        (
            "Thanks! I am finding new restaurant "
            "recommendations and will email them to you."
        )
    )