import os
import requests
from dotenv import load_dotenv

load_dotenv("voice_agent/.env")

cartesia_key = os.getenv("CARTESIA_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")
deepgram_key = os.getenv("DEEPGRAM_API_KEY")

print("--- Checking Cartesia Voice Specifically ---")
voice_id = "0e3194d6-f1c8-490b-bf6f-149a45437d26"
try:
    r = requests.get(
        f"https://api.cartesia.ai/voices/{voice_id}",
        headers={"X-API-Key": cartesia_key, "Cartesia-Version": "2024-06-10"},
        timeout=15
    )
    print(f"Status Code: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n--- Checking Groq with 15s timeout ---")
try:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 5},
        timeout=15
    )
    print(f"Groq Status: {r.status_code}")
    if r.status_code == 200:
        print(f"Groq Response: {r.json()['choices'][0]['message']['content']}")
    else:
        print(f"Groq Text: {r.text}")
except Exception as e:
    print(f"Groq Error: {e}")

print("\n--- Checking Deepgram with 15s timeout ---")
try:
    r = requests.get(
        "https://api.deepgram.com/v1/projects",
        headers={"Authorization": f"Token {deepgram_key}"},
        timeout=15
    )
    print(f"Deepgram Status: {r.status_code}")
    if r.status_code == 200:
        print(f"Deepgram Projects: {r.json()}")
    else:
        print(f"Deepgram Text: {r.text}")
except Exception as e:
    print(f"Deepgram Error: {e}")
