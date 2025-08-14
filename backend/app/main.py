from fastapi import FastAPI
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os.path
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
async def chat(message: ChatMessage):
    user_message = message.message
    access_token = message.access_token
    
    print("=" * 50)
    print(f"Received message: {user_message}")
    print(f"Access token: {access_token[:20]}...")

    # Check if this is a follow-up to a previous scheduling request
    user_key = access_token[:20]
    if user_key in conversation_state and conversation_state[user_key].get('building_event'):
        return await handle_scheduling_followup(access_token, user_message, user_key)

    # Check for calendar reading queries first (more specific patterns)
    if any(phrase in user_message.lower() for phrase in [
        "look through", "check my calendar", "what meetings", "am i free", 
        "calendar next week", "show my schedule", "do i have anything scheduled",
        "what do i have scheduled", "any meetings", "my schedule", "check schedule"
    ]):
        print("📅 DETECTED CALENDAR QUERY REQUEST")
        return await handle_calendar_query(access_token, user_message)
    
    # Then check for delete requests
    elif any(phrase in user_message.lower() for phrase in [
        "delete", "remove", "cancel", "delete event", "remove event", "cancel event"
    ]):
        print("🗑️ DETECTED DELETE REQUEST")
        return await handle_delete_request(access_token, user_message)
    
    # Then check for scheduling requests (action words)
    elif any(phrase in user_message.lower() for phrase in [
        "schedule a", "book a", "set up a", "create a meeting", "add meeting",
        "schedule meeting", "book appointment", "create event", "add event"
    ]):
        print("🎯 DETECTED SCHEDULING REQUEST")
        return await handle_scheduling_request(access_token, user_message, user_key)
    else:
        print("💬 Regular chat request")
        ai_response = model.generate_content(f"""
        You are MaxAI, a friendly and intelligent productivity consultant. You help people with:
        - Scheduling meetings and events
        - Task management and organization
        - Time management advice
        - Productivity tips and strategies
        - General questions and conversation

        The user says: {user_message}

        Respond as a helpful consultant who:
        - Is warm, friendly, and encouraging
        - Gives practical advice when asked
        - Offers to help with scheduling when relevant
        - Asks clarifying questions when needed
        - Shares productivity tips and insights
        - Maintains a conversational, helpful tone

        Keep responses concise but thorough. If they mention scheduling, remind them you can help create calendar events.
        """)

        return ChatResponse(
            response=ai_response.text,
            success=True
        )

async def handle_scheduling_request(access_token, user_message, user_key):
    """Handle initial scheduling requests and detect missing information."""
    from datetime import datetime, timedelta
    current_date = datetime.now()
    current_year = current_date.year
    
    parse_prompt = f"""
    Parse this scheduling request and extract details in JSON format: 
    "{user_message}"

    TODAY'S DATE: {current_date.strftime('%Y-%m-%d')} ({current_date.strftime('%A')})
    CURRENT YEAR: {current_year}

    Return ONLY a JSON object (no markdown, no code blocks) with these fields:
    - event_title: string (null if not mentioned)
    - date: string (YYYY-MM-DD format, null if not mentioned)
    - start_time: string (HH:MM format in 24-hour time, null if not mentioned)
    - end_time: string (HH:MM format in 24-hour time, null if not mentioned)
    - duration: string (e.g., "1 hour", "30 minutes", null if not mentioned)
    - attendees: list of strings (ONLY valid email addresses, leave empty array [] if no valid emails)

    IMPORTANT ATTENDEE RULES:
    - Only include VALID email addresses (e.g., "alex@gmail.com", "john@company.com")
    - If someone mentions a name without email (e.g., "with alex"), DO NOT include it in attendees
    - Leave attendees as empty array [] if no valid emails are provided
    - Names alone are NOT valid attendees

    IMPORTANT DATE CONVERSION RULES:
    - "tomorrow" → {current_date + timedelta(days=1)} (next day)
    - "this thursday" → next Thursday from {current_date.strftime('%Y-%m-%d')}
    - "next monday" → Monday of next week
    - "8/23" → {current_year}-08-23 (use {current_year} as year)
    - "today" → {current_date.strftime('%Y-%m-%d')}

    IMPORTANT TIME CONVERSION RULES:
    - "2pm" or "2:00 PM" → "14:00"
    - "3pm" or "3:00 PM" → "15:00"
    - "2am" or "2:00 AM" → "02:00"
    - "12pm" or "noon" → "12:00"
    - "12am" or "midnight" → "00:00"

    EXAMPLES:
    - "this thursday at 7pm" → date: "{current_year}-08-07" (next Thursday from today)
    - "tomorrow at 3pm" → date: "{(current_date + timedelta(days=1)).strftime('%Y-%m-%d')}"
    - "8/23 at 2pm" → date: "{current_year}-08-23"
    - "meeting with alex" → attendees: [] (no email provided)
    - "meeting with alex@gmail.com" → attendees: ["alex@gmail.com"]

    If any fields are missing or unclear, use null.
    """
    
    try:
        print("🤖 Asking AI to parse...")
        parse_response = model.generate_content(parse_prompt)
        print(f"🤖 AI Response: {parse_response.text}")

        import json
        import re

        # Clean the response - remove markdown code blocks
        response_text = parse_response.text.strip()
        if response_text.startswith('```'):
            response_text = re.sub(r'^```json\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
        
        print(f"🧹 Cleaned response: {response_text}")
        
        event_details = json.loads(response_text)
        print(f"📅 Parsed details: {event_details}")
        
        # Check what information is missing
        missing_fields = []
        if not event_details.get('event_title'):
            missing_fields.append('event_title')
        if not event_details.get('date'):
            missing_fields.append('date')
        if not event_details.get('start_time'):
            missing_fields.append('start_time')
        if not event_details.get('end_time') and not event_details.get('duration'):
            missing_fields.append('end_time')
        
        # Check if user mentioned a name but no email was provided
        import re
        potential_names = re.findall(r'\b[A-Z][a-z]+\b', user_message)
        mentioned_name = None
        print(f"🔍 Potential names found: {potential_names}")
        print(f"📧 Attendees in event: {event_details.get('attendees')}")
        
        if potential_names and not event_details.get('attendees'):
            # Check if any of these names are actually mentioned in context
            for name in potential_names:
                print(f"🔍 Checking name: {name}")
                if name.lower() in user_message.lower() and len(name) > 2:  # Avoid short words
                    mentioned_name = name
                    print(f"✅ Found mentioned name: {mentioned_name}")
                    break
        
        print(f"🎯 Final mentioned name: {mentioned_name}")
        
        # If we have all required information, create the event
        if not missing_fields:
            # Calculate end time if duration is provided
            if event_details.get('duration') and not event_details.get('end_time'):
                start_time = datetime.strptime(event_details['start_time'], '%H:%M')
                duration_text = event_details['duration'].lower()
                
                if 'hour' in duration_text:
                    hours = int(duration_text.split()[0])
                    end_time = start_time + timedelta(hours=hours)
                elif 'minute' in duration_text:
                    minutes = int(duration_text.split()[0])
                    end_time = start_time + timedelta(minutes=minutes)
                else:
                    # Default to 1 hour
                    end_time = start_time + timedelta(hours=1)
                
                event_details['end_time'] = end_time.strftime('%H:%M')
            
            # If a name was mentioned but no email provided, ask for email
            if mentioned_name:
                conversation_state[user_key] = {
                    'building_event': True,
                    'partial_event': event_details,
                    'missing_fields': ['attendee_email'],
                    'mentioned_name': mentioned_name
                }
                return ChatResponse(
                    response=f"I can schedule the meeting with {mentioned_name}. What's their email address?",
                    success=True
                )
            
            print("✅ Creating calendar event...")
            result = create_calender_event(access_token, event_details)
            print(f"✅ Event created: {result}")
            
            # Clear conversation state
            if user_key in conversation_state:
                del conversation_state[user_key]
            
            return ChatResponse(
                response=f"Perfect! {result}",
                success=True
            )
        else:
            # Store partial event details and ask for missing information
            conversation_state[user_key] = {
                'building_event': True,
                'partial_event': event_details,
                'missing_fields': missing_fields
            }
            
            # Generate appropriate follow-up question
            follow_up_question = generate_follow_up_question(missing_fields, event_details)
            
            return ChatResponse(
                response=follow_up_question,
                success=True
            )
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return ChatResponse(
            response=f"I'm having trouble understanding that. Could you try rephrasing your scheduling request?",
            success=True
        )

async def handle_scheduling_followup(access_token, user_message, user_key):
    """Handle follow-up messages when building an event."""
    try:
        current_state = conversation_state[user_key]
        partial_event = current_state['partial_event']
        missing_fields = current_state['missing_fields']
        
        print(f"🔄 Processing follow-up: {user_message}")
        print(f"📋 Current partial event: {partial_event}")
        print(f"❓ Missing fields: {missing_fields}")
        
        # Parse the user's response to extract the missing information
        from datetime import datetime, timedelta
        current_date = datetime.now()
        current_year = current_date.year
        
        # Create a specific prompt for the missing field
        missing_field = missing_fields[0]  # Focus on the first missing field
        
        if missing_field == 'event_title':
            parse_prompt = f"""
            The user is providing a title for their meeting/event.
            User response: "{user_message}"
            
            Extract the event title. Return ONLY a JSON object:
            {{"event_title": "extracted title"}}
            
            Examples:
            - "networking session" → {{"event_title": "networking session"}}
            - "team meeting" → {{"event_title": "team meeting"}}
            - "call it project review" → {{"event_title": "project review"}}
            """
        elif missing_field == 'date':
            parse_prompt = f"""
            The user is providing a date for their meeting/event.
            User response: "{user_message}"
            
            TODAY'S DATE: {current_date.strftime('%Y-%m-%d')} ({current_date.strftime('%A')})
            CURRENT YEAR: {current_year}
            
            Convert to YYYY-MM-DD format. Return ONLY a JSON object:
            {{"date": "YYYY-MM-DD"}}
            
            IMPORTANT CONVERSION RULES:
            - "tomorrow" → {(current_date + timedelta(days=1)).strftime('%Y-%m-%d')}
            - "this thursday" → next Thursday from {current_date.strftime('%Y-%m-%d')}
            - "next monday" → Monday of next week
            - "8/23" → {current_year}-08-23
            - "today" → {current_date.strftime('%Y-%m-%d')}
            """
        elif missing_field == 'start_time':
            parse_prompt = f"""
            The user is providing a start time for their meeting/event.
            User response: "{user_message}"
            
            Convert to HH:MM format (24-hour time). Return ONLY a JSON object:
            {{"start_time": "HH:MM"}}
            
            Examples:
            - "3pm" → {{"start_time": "15:00"}}
            - "2:30 PM" → {{"start_time": "14:30"}}
            - "9am" → {{"start_time": "09:00"}}
            """
        elif missing_field == 'end_time':
            parse_prompt = f"""
            The user is providing an end time or duration for their meeting/event.
            User response: "{user_message}"
            
            If they provide a specific time, convert to HH:MM format.
            If they provide duration (e.g., "1 hour", "30 minutes"), extract the duration.
            
            Return ONLY a JSON object:
            {{"end_time": "HH:MM"}} OR {{"duration": "duration text"}}
            
            Examples:
            - "4pm" → {{"end_time": "16:00"}}
            - "1 hour" → {{"duration": "1 hour"}}
            - "30 minutes" → {{"duration": "30 minutes"}}
            """
        elif missing_field == 'attendee_email':
            # Handle email address input
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if re.match(email_pattern, user_message.strip()):
                # Valid email provided
                mentioned_name = current_state.get('mentioned_name', 'them')
                partial_event['attendees'] = [user_message.strip()]
                
                # Clear conversation state
                del conversation_state[user_key]
                
                print("✅ Creating calendar event with attendee...")
                result = create_calender_event(access_token, partial_event)
                print(f"✅ Event created: {result}")
                
                return ChatResponse(
                    response=f"Perfect! I've scheduled the meeting with {mentioned_name} and added {user_message.strip()} as an attendee. {result}",
                    success=True
                )
            else:
                # Invalid email format
                return ChatResponse(
                    response="That doesn't look like a valid email address. Could you please provide a proper email address?",
                    success=True
                )
        
        print(f"🤖 Parsing {missing_field}...")
        parse_response = model.generate_content(parse_prompt)
        print(f"🤖 AI Response: {parse_response.text}")
        
        import json
        import re
        
        # Clean the response
        response_text = parse_response.text.strip()
        if response_text.startswith('```'):
            response_text = re.sub(r'^```json\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
        
        parsed_info = json.loads(response_text)
        print(f"📝 Parsed {missing_field}: {parsed_info}")
        
        # Update the partial event with the new information
        partial_event.update(parsed_info)
        
        # Remove the field from missing_fields
        missing_fields.pop(0)
        
        # Check if we now have all required information
        if not missing_fields:
            # Calculate end time if duration is provided
            if partial_event.get('duration') and not partial_event.get('end_time'):
                start_time = datetime.strptime(partial_event['start_time'], '%H:%M')
                duration_text = partial_event['duration'].lower()
                
                if 'hour' in duration_text:
                    hours = int(duration_text.split()[0])
                    end_time = start_time + timedelta(hours=hours)
                elif 'minute' in duration_text:
                    minutes = int(duration_text.split()[0])
                    end_time = start_time + timedelta(minutes=minutes)
                else:
                    # Default to 1 hour
                    end_time = start_time + timedelta(hours=1)
                
                partial_event['end_time'] = end_time.strftime('%H:%M')
            
            print("✅ Creating calendar event...")
            result = create_calender_event(access_token, partial_event)
            print(f"✅ Event created: {result}")
            
            # Clear conversation state
            del conversation_state[user_key]
            
            return ChatResponse(
                response=f"Perfect! {result}",
                success=True
            )
        else:
            # Ask for the next missing field
            follow_up_question = generate_follow_up_question(missing_fields, partial_event)
            
            return ChatResponse(
                response=follow_up_question,
                success=True
            )
            
    except Exception as e:
        print(f"❌ Follow-up error: {e}")
        # Clear conversation state on error
        if user_key in conversation_state:
            del conversation_state[user_key]
        
        return ChatResponse(
            response="I'm having trouble understanding that. Let's start over with your scheduling request.",
            success=True
        )

def generate_follow_up_question(missing_fields, partial_event):
    """Generate a natural follow-up question for missing information."""
    missing_field = missing_fields[0]
    
    if missing_field == 'event_title':
        return "What would you like to call this meeting or event?"
    elif missing_field == 'date':
        return "What date should I schedule this for?"
    elif missing_field == 'start_time':
        return "What time should it start?"
    elif missing_field == 'end_time':
        return "What time should it end, or how long should it last?"
    elif missing_field == 'attendee_email':
        return "What's their email address?"
    else:
        return "I need a bit more information to schedule this. Could you provide more details?"

def create_calender_event(access_token, event_details):
    try:
        service = get_calendar_service(access_token)

        # Parse date and times properly
        date = datetime.strptime(event_details['date'], '%Y-%m-%d').date()
        start_time = datetime.strptime(event_details['start_time'], '%H:%M').time()
        end_time = datetime.strptime(event_details['end_time'], '%H:%M').time()
        
        # Combine date with start and end times
        start_datetime = datetime.combine(date, start_time)
        end_datetime = datetime.combine(date, end_time)

        event = {
            'summary': event_details.get('event_title', 'Meeting'),
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'America/Los_Angeles'
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'America/Los_Angeles'
            },
            'reminders': {
                'useDefault': True
            }
        }

        # Add attendees only if they exist
        if event_details.get('attendees'):
            event['attendees'] = [{'email': attendee} for attendee in event_details['attendees']]

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Event created: {created_event.get('htmlLink')}"
        
    except Exception as e:
        raise Exception(f"Error creating event: {e}")

async def handle_calendar_query(access_token, user_message):
    """Handle calendar reading and analysis requests."""
    try:
        print("🔍 Analyzing calendar query...")
        
        # Use AI to understand what the user wants to know
        query_prompt = f"""
        Analyze this calendar query: "{user_message}"
        
        Extract what the user wants to know:
        - Time period (today, tomorrow, next week, etc.)
        - Type of information (meetings, free time, busy periods, etc.)
        - Specific details they're looking for
        
        Return ONLY a JSON object with:
        - time_period: string (today, tomorrow, next_week, etc.)
        - query_type: string (meetings, free_time, busy_periods, summary)
        - specific_date: string (YYYY-MM-DD if mentioned, null otherwise)
        """
        
        query_response = model.generate_content(query_prompt)
        print(f"🤖 Query analysis: {query_response.text}")
        
        import json
        import re
        
        # Clean response
        response_text = query_response.text.strip()
        if response_text.startswith('```'):
            response_text = re.sub(r'^```json\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
        
        query_details = json.loads(response_text)
        print(f"📋 Query details: {query_details}")
        
        # Get calendar events
        service = get_calendar_service(access_token)
        
        # Calculate time range based on query
        now = datetime.now()
        if query_details.get('time_period') == 'next_week':
            start_date = now + timedelta(days=7)
            end_date = start_date + timedelta(days=7)
        elif query_details.get('time_period') == 'tomorrow':
            start_date = now + timedelta(days=1)
            end_date = start_date + timedelta(days=1)
        else:  # default to next 7 days
            start_date = now
            end_date = now + timedelta(days=7)
        
        # Get events from Google Calendar
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_date.isoformat() + 'Z',
            timeMax=end_date.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"📅 Found {len(events)} events")
        
        if not events:
            return ChatResponse(
                response=f"You're free for the next week! No meetings scheduled.",
                success=True
            )
        
        # Format events for response
        event_summaries = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            if 'T' in start:  # Has time
                start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                event_summaries.append(f"• {event['summary']} at {start_time.strftime('%A, %B %d at %I:%M %p')}")
            else:  # All day event
                start_date = datetime.fromisoformat(start)
                event_summaries.append(f"• {event['summary']} (all day) on {start_date.strftime('%A, %B %d')}")
        
        response = f"Here's your schedule for the next week:\n\n" + "\n".join(event_summaries)
        
        return ChatResponse(
            response=response,
            success=True
        )
        
    except Exception as e:
        print(f"❌ Calendar query error: {e}")
        return ChatResponse(
            response=f"Sorry, I couldn't check your calendar right now. Error: {str(e)}",
            success=True
        )

def get_calendar_service(access_token):
    """Creates a Google Calendar service using the user's access token."""
    try:
        creds = Credentials(access_token)
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        raise Exception(f"Error getting calendar service: {e}")
    
    
    
async def handle_delete_request(access_token, user_message):
    try:
        print("🗑️ Handling delete request...")
        service = get_calendar_service(access_token)
        parse_prompt = f"""
        Parse this delete request: "{user_message}"

        Return ONLY a JSON object with:
        - event_title: string
        - date: string (YYYY-MM-DD if mentioned, null otherwise)
        - time: string (HH:MM if mentioned, null otherwise)
        """
        
        # TODO: Complete the delete logic here
        # For now, just return a placeholder response
        print("Asking AI to parse the delete request")
        parse_response = model.generate_content(parse_prompt)
        print(f"🤖 AI Response: {parse_response.text}")

        import json 
        import re

        # Clean the response - remove markdown code blocks
        response_text = parse_response.text.strip()
        if response_text.startswith('```'):
            response_text = re.sub(r'^```json\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)

        print(f"🧹 Cleaned response: {response_text}")

        delete_details = json.loads(response_text)
        print(f"📋 Delete details: {delete_details}")

        # Search for the event in the calendar
        now = datetime.now()
        start_date = now - timedelta(days=30)
        end_date = now + timedelta(days=30)

        # Get events from the calendar
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_date.isoformat() + 'Z',
            timeMax=end_date.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"📅 Found {len(events)} events")

        # Find the event to delete
        matching_event = None
        event_title = delete_details.get('event_title', '').lower()

        for event in events: 
            event_summary = event.get('summary', '').lower()
            if event_title in event_summary or event_summary in event_title:
                if delete_details.get('date'):
                    event_start = event['start'].get('dateTime', event['start'].get('date'))
                    event_date = event_start.split('T')[0]
                    if event_date == delete_details.get('date'):
                        matching_event = event
                        break
                else:
                    matching_event = event
                    break
        print(f"📅 Matching event: {matching_event}")

        # Delete the event if found
        if matching_event:
            event_id = matching_event['id']
            event_title = matching_event['summary']

            print(f"🗑️ Deleting event: {event_title} on {delete_details.get('date')}")
            
            # Delete the event
            service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()

            return ChatResponse(
                response=f"Event '{event_title}' on {delete_details.get('date')} deleted successfully.",
                success=True
            )

        else:
            return ChatResponse(
                response=f"Event '{event_title}' not found in the calendar.",
                success=True
            )

    except Exception as e:
        print(f"❌ Delete request error: {e}")
        return ChatResponse(
            response=f"Sorry, I couldn't delete the event. Error: {str(e)}",
            success=True
        )

        # TODO: Add a function to delete the event from the calendar



