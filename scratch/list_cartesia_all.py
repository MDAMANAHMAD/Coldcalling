import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("CARTESIA_API_KEY")
if not api_key:
    print("No Cartesia API key found!")
    exit(1)

url = "https://api.cartesia.ai/voices"
headers = {
    "X-API-Key": api_key,
    "Cartesia-Version": "2024-06-10"
}

try:
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        voices = response.json()
        print("=== MARATHI SUPPORTING VOICES ===")
        for voice in voices:
            langs = voice.get("supported_languages", [])
            if "mr" in langs:
                print(f"Name: {voice.get('name')} | ID: {voice.get('id')} | Languages: {langs}")
        
        print("\n=== ESHA / SAMAR VOICES ===")
        for voice in voices:
            if "Esha" in voice.get("name", "") or "Samar" in voice.get("name", ""):
                print(f"Name: {voice.get('name')} | ID: {voice.get('id')} | Languages: {voice.get('supported_languages')}")
    else:
        print(f"Failed: {response.status_code} - {response.text}")
except Exception as e:
    print("Error:", e)
