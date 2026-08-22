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

# Test 2: Benchmarking all active models
models_to_test = [
    "openai/gpt-oss-20b",
    "groq/compound-mini",
    "groq/compound",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b"
]

print("\n=== Benchmarking Latency for all Groq Models ===")
for model in models_to_test:
    print(f"\nModel: {model}")
    t0 = time.perf_counter()
    try:
        r_comp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
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
        print(f"  HTTP Status: {r_comp.status_code}")
        print(f"  Time Taken: {duration:.3f} seconds")
        if r_comp.status_code == 200:
            res = r_comp.json()
            text = res['choices'][0]['message']['content'].strip()
            print(f"  Response: {text[:150]}...")
            
            # Print token stats if available
            usage = res.get("usage", {})
            if usage:
                prompt_tok = usage.get("prompt_tokens", 0)
                comp_tok = usage.get("completion_tokens", 0)
                total_tok = usage.get("total_tokens", 0)
                print(f"  Tokens: Prompt={prompt_tok}, Completion={comp_tok}, Total={total_tok}")
        else:
            print(f"  Error Body: {r_comp.text}")
    except Exception as e:
        print(f"  ❌ Error calling completions for {model}: {e}")


