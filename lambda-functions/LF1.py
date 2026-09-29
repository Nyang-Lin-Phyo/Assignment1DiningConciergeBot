import json
import boto3



# Config

REGION = "us-east-1"

QUEUE_URL = (
    "https://sqs.us-east-1.amazonaws.com/456157355328/food_info"
)

# Role that exists in Ramsey's AWS account.
STATE_ROLE_ARN = (
    "arn:aws:iam::180382394287:"
    "role/lf1accesDB"
)

STATE_TABLE_NAME = "dining-user-state"

SES_FROM_EMAIL = "0monsuno82@gmail.com"



# AWS clients in Ramsey's account


sqs = boto3.client(
    "sqs",
    region_name=REGION
)

sts = boto3.client(
    "sts",
    region_name=REGION
)



# Helper: get Lex slot value


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



# Helper: normalize strings for comparison


def normalize(value):

    if value is None:
        return None

    return str(value).strip().lower()



# Assume role in Ramsey's account

def get_ramsey_aws_resources():

    print("Assuming role in recommendation AWS account...")

    response = sts.assume_role(
        RoleArn=STATE_ROLE_ARN,
        RoleSessionName="LF1DiningStateSession"
    )

    credentials = response["Credentials"]

    boto_args = {
        "aws_access_key_id": credentials["AccessKeyId"],
        "aws_secret_access_key": credentials["SecretAccessKey"],
        "aws_session_token": credentials["SessionToken"],
        "region_name": REGION
    }

    # DynamoDB in Ramsey's account
    ramsey_dynamodb = boto3.resource(
        "dynamodb",
        **boto_args
    )

    state_table = ramsey_dynamodb.Table(
        STATE_TABLE_NAME
    )

    # SES in Ramsey's account
    ramsey_ses = boto3.client(
        "ses",
        **boto_args
    )

    return state_table, ramsey_ses


# 
# Helper: send previous recommendation email
# 

def send_previous_recommendation_email(
    ses,
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
        response["MessageId"]
    )

    return response


# Helper: close Lex conversation


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



# Lambda handler

def lambda_handler(event, context):

    print("========== LF1 START ==========")

    print(
        "Invocation source:",
        event.get("invocationSource")
    )

    intent_data = event[
        "sessionState"
    ]["intent"]

    slots = intent_data.get(
        "slots",
        {}
    )

    intent = intent_data["name"]

    print("Intent:", intent)
    print("Slots:", slots)

    # Get normal dining values

    email = get_slot_value(
        slots,
        "Email"
    )

    location = get_slot_value(
        slots,
        "city_man"
    )

    cuisine = get_slot_value(
        slots,
        "Cusine"
    )

    date = get_slot_value(
        slots,
        "date"
    )

    dining_time = get_slot_value(
        slots,
        "Time"
    )

    number_people = get_slot_value(
        slots,
        "Number_people"
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


    # 
    # Check whether normal search slots are complete
    # 

    required_slots = [
        "date",
        "Email",
        "Cusine",
        "Number_people",
        "Time",
        "city_man"
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


    # 
    # Lex still needs to collect normal search information
    # 

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


    # 
    # All normal slots exist.
    # Access Ramsey's DynamoDB + SES.
    # 

    state_table, ramsey_ses = (
        get_ramsey_aws_resources()
    )


    # 
    # Look up user's previous recommendation
    # 

    print(
        "Checking dining-user-state..."
    )

    result = state_table.get_item(
        Key={
            "email": email.strip().lower()
        }
    )

    previous_search = result.get(
        "Item"
    )

    print(
        "Previous search:",
        previous_search
    )


    # Previous state exists 

    if previous_search:

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


        same_search = (
            normalize(previous_location)
            ==
            normalize(location)

            and

            normalize(previous_cuisine)
            ==
            normalize(cuisine)
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
            "Same search:",
            same_search
        )


        # Same location + same cuisine

        if (
            same_search
            and previous_recommendations
        ):

            # 
            # We have not asked Yes/No yet
            # 

            if use_previous is None:

                print(
                    "Same search detected."
                )

                print(
                    "Asking whether to reuse recommendations."
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
                            "contentType": "PlainText",
                            "content": (
                                "I found the same location "
                                "and cuisine from your previous "
                                "search. Would you like the same "
                                "recommendations as last time?"
                            )
                        }
                    ]
                }


            normalized_answer = normalize(
                use_previous
            )
 
            # YES            
            if normalized_answer in [
                "yes",
                "yeah",
                "yep",
                "sure"
            ]:

                print(
                    "User wants previous recommendations."
                )

                print(
                    "Previous recommendations:",
                    previous_recommendations
                )


                # Send directly through Ramsey's SES
                send_previous_recommendation_email(
                    ses=ramsey_ses,
                    email=email,
                    cuisine=cuisine,
                    date=date,
                    time=dining_time,
                    number_people=number_people,
                    restaurants=previous_recommendations
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
 
            # NO
            

            if normalized_answer in [
                "no",
                "nope"
            ]:

                print(
                    "User wants new recommendations."
                )


    
    # No previous recommendation, different search,or user answered NO.
    # Send normal request to SQS.


    message = {
        "intent": intent,
        "slots": slots
    }

    print(
        "Message:",
        message
    )

    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(
            message
        )
    )

    print(
        "SQS Message ID:",
        response.get("MessageId")
    )


    # LF1 does NOT save the recommendation.
    # LF2 chooses the actual restaurants and will save them into dining-user-state (Ramsey's account) after the recommendation email succeeds.


    return close_intent(
        intent,
        slots,
        (
            "Thanks! I am finding new restaurant "
            "recommendations and will email them to you."
        )
    )