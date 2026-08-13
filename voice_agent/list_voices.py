import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ELEVENLABS_API_KEY")
if not api_key:
    print("No ElevenLabs API key found!")
    exit(1)

url = "https://api.elevenlabs.io/v1/voices"
headers = {
    "xi-api-key": api_key
}

try:
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        voices = response.json().get("voices", [])
        print("=" * 60)
        print(f"AVAILABLE ELEVENLABS VOICES ({len(voices)}):")
        print("=" * 60)
        for voice in voices:
            category = voice.get("category", "unknown")
            labels = voice.get("labels", {})
            accent = labels.get("accent", "unknown")
            language = labels.get("language", "unknown")
            description = voice.get("description", "No description")
            print(f"Name: {voice['name']} | ID: {voice['voice_id']}")
            print(f"  Category: {category} | Accent: {accent} | Language: {language}")
            print(f"  Description: {description}")
            print("-" * 60)
    else:
        print(f"Failed to fetch voices: {response.status_code} - {response.text}")
except Exception as e:
    print("Error:", e)
