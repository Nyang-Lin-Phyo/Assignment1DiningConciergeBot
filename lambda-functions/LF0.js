
import {
  LexRuntimeV2Client,
  RecognizeTextCommand
} from "@aws-sdk/client-lex-runtime-v2";

const lexClient = new LexRuntimeV2Client({
  region: "us-east-1"
});

export const handler = async (event) => {

  // Handle browser preflight request
  if (event.requestContext?.http?.method === "OPTIONS") {
    return {
      statusCode: 200,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
      },
      body: ""
    };
  }

  try {

    // 1. Extract message from API request
    const body = JSON.parse(event.body || "{}");
    const message = body.messages?.[0]?.unstructured?.text;

    if (!message) {
      return {
        statusCode: 400,
        headers: {
          "Access-Control-Allow-Origin": "*"
        },
        body: JSON.stringify({
          error: "Missing message"
        })
      };
    }

    // 2. Send message to Lex
    const command = new RecognizeTextCommand({
      botId: "KNTMSCJM0H",
      botAliasId: "TSTALIASID",
      localeId: "en_US",
      sessionId: "user-session-1",
      text: message
    });

    // 3. Wait for Lex response
    const lexResponse = await lexClient.send(command);

    // 4. Convert Lex response to the format expected by frontend
    const messages = (lexResponse.messages || []).map(msg => ({
      type: "unstructured",
      unstructured: {
        text: msg.content || ""
      }
    }));

    // 5. Return response
    return {
      statusCode: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
      },
      body: JSON.stringify({
        messages: messages
      })
    };

  } catch (error) {

    console.error("Lex error:", error);

    return {
      statusCode: 500,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
      },
      body: JSON.stringify({
        messages: [
          {
            type: "unstructured",
            unstructured: {
              text: "Sorry, there was an error contacting the chatbot."
            }
          }
        ]
      })
    };
  }
};