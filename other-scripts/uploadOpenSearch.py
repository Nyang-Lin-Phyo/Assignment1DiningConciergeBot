import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path


INDEX_NAME = "restaurants"
DOC_TYPE = "Restaurant"

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_FILE = SCRIPT_DIR / "manhattan_restaurants_1000_final.json"

ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"].rstrip("/")
USERNAME = os.environ["OPENSEARCH_USERNAME"]
PASSWORD = os.environ["OPENSEARCH_PASSWORD"]


def request(method, path, body=None, content_type="application/json"):
    url = ENDPOINT + path

    credentials = f"{USERNAME}:{PASSWORD}"
    token = base64.b64encode(
        credentials.encode("utf-8")
    ).decode("utf-8")

    headers = {
        "Authorization": f"Basic {token}"
    }

    if body is None:
        data = None

    elif isinstance(body, bytes):
        data = body
        headers["Content-Type"] = content_type

    else:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = content_type

    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")

            if not text:
                return {}

            return json.loads(text)

    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8")

        if (
            e.code == 400
            and "resource_already_exists_exception" in details
        ):
            return {"already_exists": True}

        raise RuntimeError(
            f"OpenSearch error {e.code}: {details}"
        )


print("Loading:", DATA_FILE)

with open(DATA_FILE, "r", encoding="utf-8") as f:
    restaurants = json.load(f)

print("Restaurants loaded:", len(restaurants))

if len(restaurants) != 1000:
    raise ValueError(
        f"Expected 1000 restaurants, found {len(restaurants)}"
    )


# --------------------------------------------------
# CREATE INDEX + TYPE
# --------------------------------------------------

mapping = {
    "mappings": {
        "Restaurant": {
            "properties": {
                "RestaurantID": {
                    "type": "keyword"
                },
                "Cuisine": {
                    "type": "keyword"
                }
            }
        }
    }
}

result = request(
    "PUT",
    f"/{INDEX_NAME}",
    mapping
)

if result.get("already_exists"):
    print("Index already exists.")
else:
    print("Created restaurants index.")


# --------------------------------------------------
# BULK UPLOAD
# --------------------------------------------------

bulk_lines = []

for restaurant in restaurants:
    business_id = str(restaurant["business_id"])
    cuisine = restaurant["cuisine"]

    bulk_lines.append(
        json.dumps({
            "index": {
                "_index": INDEX_NAME,
                "_type": DOC_TYPE,
                "_id": business_id
            }
        })
    )

    bulk_lines.append(
        json.dumps({
            "RestaurantID": business_id,
            "Cuisine": cuisine
        })
    )

payload = (
    "\n".join(bulk_lines) + "\n"
).encode("utf-8")

print("Uploading 1000 restaurants...")

result = request(
    "POST",
    "/_bulk?refresh=true",
    payload,
    "application/x-ndjson"
)

if result.get("errors"):
    raise RuntimeError(
        "One or more bulk operations failed."
    )

print("Bulk upload successful.")


# --------------------------------------------------
# VERIFY
# --------------------------------------------------

total = request(
    "GET",
    f"/{INDEX_NAME}/{DOC_TYPE}/_count"
)

print(
    "\nTotal OpenSearch documents:",
    total["count"]
)

cuisines = [
    "American",
    "Italian",
    "Japanese",
    "Chinese",
    "Pizza"
]

for cuisine in cuisines:
    result = request(
        "POST",
        f"/{INDEX_NAME}/{DOC_TYPE}/_count",
        {
            "query": {
                "term": {
                    "Cuisine": cuisine
                }
            }
        }
    )

    print(
        cuisine,
        ":",
        result["count"]
    )