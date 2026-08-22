import os
import requests
import json
import time
from dotenv import load_dotenv

# Load .env file
load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
if not groq_key:
    print("❌ GROQ_API_KEY is not set in your environment or .env file!")
    exit(1)

print(f"🔍 Found Groq key: {groq_key[:10]}...{groq_key[-10:]} (Total length: {len(groq_key)})")

HINDI_REAL_ESTATE_PROMPT = """# IDENTITY & GREETING FLOW
- **Name/Identity**: Gayatri (गायत्री), warm & professional Property Advisor at Shiv Sai Construction, representing the Sai Complex project in Dombivli East.
- **Greeting (Turn 1)**: "Hello... main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
- **Pitch & Interest Check (Turn 2)**: Once prospect answers (e.g. "haan", "boliye"), state: "Ji... humara ek residential project launch hua hai jisme one BHK flats thirty six lakh se aur two BHK flats seventy two lakh se start hote hote hain... kya aap iske details jaan-na chahenge?"
"""

# Test 1: Fetching Models
print("\n--- Test 1: Fetching Models list ---")
r_models = requests.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {groq_key}"}
)
print(f"Status Code: {r_models.status_code}")

# Test 2: Real Chat Completion with openai/gpt-oss-20b
print("\n--- Test 2: Actual Chat Completion (openai/gpt-oss-20b) ---")
t0 = time.perf_counter()
try:
    r_comp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        json={
            "model": "openai/gpt-oss-20b",
            "messages": [
                {"role": "system", "content": HINDI_REAL_ESTATE_PROMPT},
                {"role": "user", "content": "haan boliye kya project hai?"}
            ],
            "temperature": 0.3
        }
    )
    duration = time.perf_counter() - t0
    print(f"HTTP Status: {r_comp.status_code} | Time Taken: {duration:.2f}s")
    try:
        res = r_comp.json()
        print(f"Response Text: {res['choices'][0]['message']['content']}")
    except Exception:
        print(r_comp.text)
except Exception as e:
    print(f"Error calling completions API: {e}")

