import os
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("SAMBANOVA_API_KEY")
if not key:
    print("❌ SAMBANOVA_API_KEY is not set in your environment or .env file!")
    exit(1)

print(f"🔍 Found SambaNova key: {key[:8]}...{key[-8:]} (Total length: {len(key)})")

HINDI_REAL_ESTATE_PROMPT = """# IDENTITY & GREETING FLOW
- **Name/Identity**: Gayatri, warm & professional Property Advisor at Shiv Sai Construction, representing the Sai Complex project in Dombivli East.
- **Greeting (Turn 1)**: "Hello... main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
"""

# Test 1: Fetching Models
print("\n--- Test 1: Fetching Models list ---")
try:
    r_models = requests.get(
        "https://api.sambanova.ai/v1/models",
        headers={"Authorization": f"Bearer {key}"}
    )
    print(f"Status Code: {r_models.status_code}")
    if r_models.status_code == 200:
        data = r_models.json().get("data", [])
        print("Available models:")
        for m in data:
            print(f"  - {m.get('id')}")
    else:
        print(r_models.text)
except Exception as e:
    print(f"Error fetching models: {e}")

# Test 2: Benchmarking typical models
models_to_test = [
    "Meta-Llama-3.3-70B-Instruct",
    "gpt-oss-120b",
    "gemma-4-31b-it",
    "Meta-Llama-3.1-8B-Instruct"
]

print("\n--- Test 2: Benchmarking Model Latency ---")
for model in models_to_test:
    print(f"\nModel: {model}")
    t0 = time.perf_counter()
    try:
        r_comp = requests.post(
            "https://api.sambanova.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": HINDI_REAL_ESTATE_PROMPT},
                    {"role": "user", "content": "haan boliye kya project hai?"}
                ],
                "temperature": 0.3
            },
            timeout=10
        )
        duration = time.perf_counter() - t0
        print(f"  HTTP Status: {r_comp.status_code} | Time Taken: {duration:.3f}s")
        if r_comp.status_code == 200:
            res = r_comp.json()
            text = res['choices'][0]['message']['content'].strip()
            print(f"  Response: {text[:100]}...")
        else:
            print(f"  Error Body: {r_comp.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
