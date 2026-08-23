import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
samba_key = os.getenv("SAMBANOVA_API_KEY")

print("=== LLM Provider Speed & Latency Comparison ===")

# 1. Test Groq
if groq_key:
    print("\n⚡ [Groq] Testing 'openai/gpt-oss-20b'...")
    t0 = time.perf_counter()
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "openai/gpt-oss-20b",
                "messages": [{"role": "user", "content": "Hello! Reply with exactly one word: 'Success'."}]
            },
            timeout=8
        )
        dt = time.perf_counter() - t0
        print(f"  Status Code: {r.status_code}")
        print(f"  Roundtrip Time: {dt:.3f} seconds")
        if r.status_code == 200:
            print(f"  Output: '{r.json()['choices'][0]['message']['content'].strip()}'")
        else:
            print(f"  Error: {r.text}")
    except Exception as e:
        print(f"  ❌ Connection Error: {e}")
else:
    print("\n[Groq] Key not set in .env")

# 2. Test SambaNova
if samba_key:
    models_to_test = ["gpt-oss-120b", "Meta-Llama-3.3-70B-Instruct"]
    for model in models_to_test:
        print(f"\n⚡ [SambaNova] Testing '{model}'...")
        t0 = time.perf_counter()
        try:
            r = requests.post(
                "https://api.sambanova.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {samba_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hello! Reply with exactly one word: 'Success'."}]
                },
                timeout=8
            )
            dt = time.perf_counter() - t0
            print(f"  Status Code: {r.status_code}")
            print(f"  Roundtrip Time: {dt:.3f} seconds")
            if r.status_code == 200:
                print(f"  Output: '{r.json()['choices'][0]['message']['content'].strip()}'")
            else:
                print(f"  Response Body: {r.text}")
        except Exception as e:
            print(f"  ❌ Connection Error: {e}")
else:
    print("\n[SambaNova] Key not set in .env")
