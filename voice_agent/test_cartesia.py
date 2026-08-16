import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("CARTESIA_API_KEY", "sk_car_vQJtABBJ2eao6hJZa7NioG")

print("=" * 50)
print(f"Checking Cartesia API Key: {key[:10]}... (length={len(key) if key else 0})")
print("=" * 50)

url = "https://api.cartesia.ai/tts/bytes"
headers = {
    "X-API-Key": key,
    "Cartesia-Version": "2024-06-10",
    "Content-Type": "application/json"
}

payload = {
    "model_id": "sonic-multilingual",
    "transcript": "Namaste",
    "voice": {
        "mode": "id",
        "id": "72656902-fb4b-4c31-af52-c3b68e2cae26" # Esha
    },
    "output_format": {
        "container": "raw",
        "encoding": "pcm_f32le",
        "sample_rate": 24000
    }
}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    print(f"Response Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ Success! Cartesia key is active and has credits.")
        print(f"Received {len(response.content)} bytes of audio data.")
    else:
        print("❌ Cartesia API Error!")
        print(f"Response Body: {response.text}")
except Exception as e:
    print(f"❌ Connection error: {e}")

print("=" * 50)
