import os
from dotenv import load_dotenv
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

load_dotenv() 

def test_gemini():
    """Test Gemini API"""
    try: 
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Hello! Can you help me schedule a meeting?")
        print("Gemini API Working");
        print(f"Response: {response.text}")
        return True
    except Exception as e:
        print("Gemini API Error: ", e)
        return False

def test_google_auth(): 
    """Test Google OAuth Credentials"""
    try:
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

        if client_id and client_secret:
            print("Google OAuth Credentials loaded successfully")
            return True
        else:
            print("Google OAuth Credentials not found")
            return False
    except Exception as e:
        print("Google OAuth Credentials Error: ", e)
        return False
    
if __name__ == "__main__":
    print("Testing APIs...")
    print("-" * 30)

    gemini_works = test_gemini()
    google_auth_works = test_google_auth()

    print("-" *30)
    if gemini_works and google_auth_works:
        print("All APIs are working!")
    else:
        print("Some APIs are not working!")




