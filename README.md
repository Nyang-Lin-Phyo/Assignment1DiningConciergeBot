# Assignment 1 Dining Concierge Bot

Cloud Computing and Big Data — Fall 2026  
Dining Concierge chatbot project.

## Repository Structure

```text
Assignment1DiningConciergeBot/
│
├── README.md
├── .gitignore
│
├── frontend/
│   └── .gitkeep
│
├── lambda-functions/
│   └── LF2.py
│
└── other-scripts/
    ├── buildFinalManhattanDataset.py
    ├── manhattan_restaurants_1000_final.json
    ├── testDynamoDB.py
    └── uploadTestRestaurants.py
```

## Final Restaurant Dataset

`manhattan_restaurants_1000_final.json` contains:

- 1,000 unique Manhattan restaurants
- 200 American restaurants
- 200 Italian restaurants
- 200 Japanese restaurants
- 200 Chinese restaurants
- 200 Pizza restaurants

Each restaurant record contains:

- Business ID
- Name
- Cuisine
- Address
- Coordinates
- Number of Reviews
- Rating
- Zip Code
- `insertedAtTimestamp`

## Planned AWS Architecture

```text
Frontend
   ↓
API Gateway
   ↓
LF0
   ↓
Amazon Lex
   ↓
LF1
   ↓
SQS
   ↓
LF2
   ↓
OpenSearch
   ↓
DynamoDB
   ↓
SES
   ↓
Recommendation Email
```

## Final Deployment Tasks

The remaining backend deployment work includes:

1. Create the final DynamoDB `yelp-restaurants` table.
2. Upload all 1,000 final restaurant records.
3. Create the SQS queue.
4. Connect LF1 to SQS.
5. Create the OpenSearch restaurant index.
6. Upload restaurant ID and cuisine information to OpenSearch.
7. Deploy the final LF2 implementation.
8. Configure SES email sending.
9. Configure EventBridge to invoke LF2 every minute.
10. Run a complete end-to-end test from chatbot to recommendation email.
11. Create the final GitHub release and attach the submission ZIP.
12. Decommission cloud resources after the assignment is complete.
