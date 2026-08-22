import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
print(f"🔍 Testing Deepgram Key: {key[:8]}...{key[-8:]} (Total length: {len(key)})")

# We send a tiny request to the Listen API to verify authorization and model eligibility.
try:
    r = requests.post(
        "https://api.deepgram.com/v1/listen?model=nova-2&language=hi",
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": "audio/wav"
        },
        data=b"\x52\x49\x46\x46\x24\x00\x00\x00\x57\x41\x56\x45\x66\x6d\x74\x20\x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00\x64\x61\x74\x61\x00\x00\x00\x00" # minimal valid wav header
    )
    print(f"HTTP Status: {r.status_code}")
    print(f"Response Body: {r.text}")
except Exception as e:
    print(f"❌ Error communicating with Deepgram: {e}")
