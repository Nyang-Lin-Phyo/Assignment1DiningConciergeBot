# Assignment 1 Dining Concierge Bot

Cloud Computing and Big Data — Fall 2026  
Dining Concierge chatbot project.
![alt text](/images/image.png)

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


## Extra Credit

![image](<images/Screenshot 2026-09-29 190119.png>)

DynamoDB is used to maintain the user's previous search state. For each user, identified by their email, the application stores the previous search information, including location and cuisine, along with the recommendation returned by OpenSearch.

When a user starts a new search, LF1 checks whether their email exists in DynamoDB. If the user is not present, the request follows the normal flow and is sent to SQS for processing by LF2. LF2 processes the request, obtains the recommendation from OpenSearch, and stores the search information and recommendation in DynamoDB.

If the user is already present, LF1 compares the current location and cuisine with the user's previous search. If they are the same, the user is asked whether they would like to use the same recommendation as before. If the user responds yes, the previously stored recommendation is reused and sent to the user's email. If the user responds no, the new search information is sent through SQS to LF2, which generates a new recommendation. LF2 then stores the updated search information and recommendation in DynamoDB for future requests.

