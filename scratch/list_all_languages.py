import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("CARTESIA_API_KEY")
url = "https://api.cartesia.ai/voices"
headers = {
    "X-API-Key": api_key,
    "Cartesia-Version": "2024-06-10"
}

try:
    response = requests.get(url, headers=headers).json()
    langs = set(v.get("language") for v in response if v.get("language"))
    print("=== UNIQUE LANGUAGES IN CARTESIA ===")
    print(sorted(list(langs)))
    
    print("\n=== MARATHI (mr) VOICES ===")
    for voice in response:
        if voice.get("language") == "mr":
            print(f"Name: {voice.get('name')} | ID: {voice.get('id')} | Gender: {voice.get('gender')}")
            
    print("\n=== ENGLISH (en) VOICES (Feminine) ===")
    for voice in response:
        if voice.get("language") == "en" and voice.get("gender") == "feminine":
            print(f"Name: {voice.get('name')} | ID: {voice.get('id')}")
            
except Exception as e:
    print("Error:", e)
