from fastapi import FastAPI
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="MaxAI Productivity Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')


# Data model for incoming messages
class ChatMessage(BaseModel):
    message: str
    access_token: str 
    user_id: str = None

# Simple conversation state storage for multi-turn conversations
conversation_state = {}

# Data model for responses 
class ChatResponse(BaseModel):
    response: str
    success: bool

# Chat Endpoint 
@app.post("/api/chat", response_model=ChatResponse)
async def chat(chat_message: ChatMessage):
    user_message = chat_message.message
    access_token = chat_message.access_token

    print("="*100)
    print("User message: ", user_message)
    print("="*100)

    # Add logic to detect if the user is asking about scheduling a meeting
    if any(word in user_message.lower() for word in ["schedule", "meeting", "event", "appointment"]):
        print("DETECTED SCHEDULING REQUEST")

        parsed_event = await parse_scheduling_request(user_message)

        print("Parsed event: ", parsed_event)
        print("Parsed event type: ", type(parsed_event))

        if "error" not in parsed_event:
            print("Parsing successful")
            # create calendar event
            print("Creating calendar event...")
            result = create_calendar_event(parsed_event, access_token)

            return ChatResponse(
                response=result,
                success=True
            )
        else:
            return ChatResponse(
                response=parsed_event["error"],
                success=True
            )
   
    ai_response = model.generate_content(
        f""" 
        You are a helpful assistant that can help with scheduling meetings. 
        The user says: {user_message} 

        Respond in a friendly and helpful manner. If they ask about scheduling a meeting,
        work, a networking session, or any scheduling related questions, you should respond with a message that says:
        "I can help with that! I'll need to know the date, time, and name of the meeting."
        """
    )

    return ChatResponse(
        response=ai_response.text,
        success=True
    )

async def parse_scheduling_request(user_message):
    """
    Parse the user's message to extract scheduling information.
    """
    # TODO: Implement parsing logic

    current_datetime = datetime.now()
    current_date = current_datetime.strftime("%Y-%m-%d")

    # Tomorrow's date
    tomorrow = current_datetime + timedelta(days=1)
    tomorrow_date = tomorrow.strftime("%Y-%m-%d")


    parse_prompt = f"""
    Parse the following user message to extract scheduling information:
    {user_message}

    CURRENT DATE: {current_date}
    CURRENT YEAR: {current_datetime.year}

    Return JSON with the following fields:
    - date: The date of the meeting
    - start_time: The start time of the meeting
    - end_time: The end time of the meeting
    - name: The name of the meeting
    - attendees: A list of attendees (names or email addresses) (optional)
    - location: The location of the meeting (optional)
    - description: The description of the meeting (optional)
    - notes: Any additional notes or instructions (optional)

    IMPORTANT DATE CONVERSION RULES:
    - "today" → {current_date}
    - "tomorrow" → {tomorrow_date}
    - "8/14" → 2025-08-14 (use {current_datetime.year} as year)
    - "12/03" → 2025-12-03 (use {current_datetime.year} as year)
    - "this Friday" → next Friday from {current_date}
    - "next Monday" → Monday of next week
    - Always use {current_datetime.year} as the base year unless explicitly stated otherwise

    EXAMPLES:
    - "8/14 at 2pm" → date: "2025-08-14"
    - "tomorrow at 3pm" → date: "{tomorrow_date}"
    - "12/03 meeting" → date: "2025-12-03"
    """


    response = model.generate_content(parse_prompt)
    print("Raw AI Response: ", response.text)

    # Clean the response - extract just the JSON part
    response_text = response.text.strip()
    print("Cleaned Response: ", response_text)

    try:
        import json
        # Find the first { and last } to extract just the JSON
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        
        if start != -1 and end != -1:
            json_part = response_text[start:end]
            print("Extracted JSON: ", json_part)

            parsed_json = json.loads(json_part)
            print("Successfully parsed JSON")
            return parsed_json
        else:
            return {"error": "No JSON found in response"}
            
    except json.JSONDecodeError:
        return {"error": f"AI response wasn't valid JSON: {response_text}"}

def get_calendar_service(access_token):
    """
    Get a Google Calendar service object using the user's access token.
    """
    if not access_token:
        raise Exception("Access token is required to get a calendar service")
    
    try:
        creds = Credentials(access_token)
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        return {f"Error getting calendar service: {e}"}

def create_calendar_event(event_details, access_token):
    """
    Create a new calendar event using the user's Google Calendar service.
    """
    try:
        service = get_calendar_service(access_token)
        # My parsed data looks like this:
        # {'date': '2025-08-14', 'start_time': '14:00', 'end_time': '15:00', 'name': 'Meeting with Alex'}

        # Google Calender Event
        event = { 
            'summary': event_details['name'],
            'start': {
                'dateTime': f"{event_details['date']}T{event_details['start_time']}:00",
                'timeZone': 'America/Los_Angeles'
            },
            'end': {
                'dateTime': f"{event_details['date']}T{event_details['end_time']}:00",
                'timeZone': 'America/Los_Angeles'
            }
        }

        if event_details.get('attendees'):
            event['attendees'] = []
            for attendee in event_details['attendees']: 
                if '@' in attendee: # email address
                    event['attendees'].append({'email': attendee})
                else: # name
                    event['attendees'].append({'displayName': attendee})

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Event created successfully! View it here: {created_event.get('htmlLink')}"

    except Exception as e:
        return f"Error creating calendar event: {e}"








       





    
    