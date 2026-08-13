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
        print("=" * 60)
        print(f"AVAILABLE CARTESIA HINDI VOICES:")
        print("=" * 60)
        for voice in voices:
            language = voice.get("language", "")
            supported_languages = voice.get("supported_languages", [])
            # Check if voice supports Hindi
            if "hi" in supported_languages or language == "hi" or "Hindi" in str(voice):
                print(f"Name: {voice.get('name')} | ID: {voice.get('id')}")
                print(f"  Gender: {voice.get('gender')} | Tier: {voice.get('tier')}")
                print(f"  Description: {voice.get('description', 'No description')}")
                print("-" * 60)
    else:
        print(f"Failed to fetch voices: {response.status_code} - {response.text}")
except Exception as e:
    print("Error:", e)
