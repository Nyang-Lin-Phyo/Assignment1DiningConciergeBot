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
