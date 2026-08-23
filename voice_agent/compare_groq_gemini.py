import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")

HINDI_REAL_ESTATE_PROMPT = """# IDENTITY & GREETING FLOW
- **Name/Identity**: Gayatri, warm & professional Property Advisor at Shiv Sai Construction, representing the Sai Complex project in Dombivli East.
- **Greeting (Turn 1)**: "Hello... main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
"""

print("=== LLM Response Latency Benchmark: Groq vs Google Gemini ===")
print("Prompt size: ~200 tokens (System instructions + user question)")

results = {}

# 1. Benchmark Groq
if groq_key:
    model_name = "openai/gpt-oss-20b"
    print(f"\n⚡ [Groq] Testing '{model_name}'...")
    t0 = time.perf_counter()
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": HINDI_REAL_ESTATE_PROMPT},
                    {"role": "user", "content": "Haan boliye, kya project hai?"}
                ],
                "temperature": 0.3,
                "max_tokens": 150
            },
            timeout=8
        )
        dt = time.perf_counter() - t0
        if r.status_code == 200:
            res_data = r.json()
            completion_text = res_data['choices'][0]['message']['content'].strip()
            print(f"  Status: {r.status_code} | Time: {dt:.3f} seconds")
            print(f"  Response: '{completion_text[:80]}...'")
            results["Groq"] = dt
        else:
            print(f"  ❌ Error {r.status_code}: {r.text}")
            results["Groq"] = f"Error {r.status_code}"
    except Exception as e:
        print(f"  ❌ Connection Error: {e}")
        results["Groq"] = "Connection Error"
else:
    print("\n[Groq] Key not set in .env")
    results["Groq"] = "Key not set"

# 2. Benchmark Google Gemini
if google_key:
    # We test gemini-1.5-flash as it's the standard production model
    model_name = "gemini-1.5-flash"
    print(f"\n⚡ [Google Gemini] Testing '{model_name}'...")
    t0 = time.perf_counter()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={google_key}"
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"System Instructions:\n{HINDI_REAL_ESTATE_PROMPT}\n\nUser Question: Haan boliye, kya project hai?"}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 150
                }
            },
            timeout=8
        )
        dt = time.perf_counter() - t0
        if r.status_code == 200:
            res_data = r.json()
            completion_text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            print(f"  Status: {r.status_code} | Time: {dt:.3f} seconds")
            print(f"  Response: '{completion_text[:80]}...'")
            results["Gemini"] = dt
        else:
            print(f"  ❌ Error {r.status_code}: {r.text}")
            results["Gemini"] = f"Error {r.status_code}"
    except Exception as e:
        print(f"  ❌ Connection Error: {e}")
        results["Gemini"] = "Connection Error"
else:
    print("\n[Google Gemini] Key not set in .env")
    results["Gemini"] = "Key not set"

# Print side-by-side table
print("\n" + "="*50)
print(f"{'Provider':<20} | {'Latency (seconds)':<20}")
print("="*50)
for provider, score in results.items():
    if isinstance(score, float):
        print(f"{provider:<20} | {score:.3f} seconds")
    else:
        print(f"{provider:<20} | {score}")
print("="*50)
