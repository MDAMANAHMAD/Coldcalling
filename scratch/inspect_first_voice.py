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

response = requests.get(url, headers=headers).json()
for voice in response:
    if "Esha" in voice.get("name", ""):
        print("Esha fields:")
        for k, v in voice.items():
            print(f"  {k}: {v}")
        break
