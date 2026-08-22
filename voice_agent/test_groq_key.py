import os
import requests
import json
from dotenv import load_dotenv

# Load .env file
load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
if not groq_key:
    print("❌ GROQ_API_KEY is not set in your environment or .env file!")
    exit(1)

print(f"🔍 Found Groq key: {groq_key[:10]}...{groq_key[-10:]} (Total length: {len(groq_key)})")

# Test 1: List Models
print("\n--- Test 1: Fetching Models list from Groq ---")
try:
    r_models = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {groq_key}"}
    )
    print(f"Status Code: {r_models.status_code}")
    try:
        print(json.dumps(r_models.json(), indent=2))
    except Exception:
        print(r_models.text)
except Exception as e:
    print(f"Error calling models API: {e}")

# Test 2: Simple Chat Completion with llama-3.3-70b-versatile
print("\n--- Test 2: Simple Chat Completion (llama-3.3-70b-versatile) ---")
try:
    r_comp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": "hello"}]
        }
    )
    print(f"Status Code: {r_comp.status_code}")
    try:
        print(json.dumps(r_comp.json(), indent=2))
    except Exception:
        print(r_comp.text)
except Exception as e:
    print(f"Error calling completions API: {e}")

# Test 3: Simple Chat Completion with llama-3.1-8b-instant
print("\n--- Test 3: Simple Chat Completion (llama-3.1-8b-instant) ---")
try:
    r_comp2 = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "hello"}]
        }
    )
    print(f"Status Code: {r_comp2.status_code}")
    try:
        print(json.dumps(r_comp2.json(), indent=2))
    except Exception:
        print(r_comp2.text)
except Exception as e:
    print(f"Error calling completions API: {e}")
