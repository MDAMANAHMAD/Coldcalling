import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

print("="*60)
print("             🔑 API KEY & BALANCE STATUS REPORT")
print("="*60)

# 1. Check Deepgram
dg_key = os.getenv("DEEPGRAM_API_KEY")
if dg_key:
    print("\n🎤 [Deepgram STT]")
    try:
        r = requests.get("https://api.deepgram.com/v1/projects", headers={"Authorization": f"Token {dg_key}"})
        if r.status_code == 200:
            projects = r.json().get("projects", [])
            for p in projects:
                p_id = p.get("project_id")
                p_name = p.get("name")
                print(f"  Project: {p_name} ({p_id})")
                # Fetch balance
                r_bal = requests.get(f"https://api.deepgram.com/v1/projects/{p_id}/balances", headers={"Authorization": f"Token {dg_key}"})
                if r_bal.status_code == 200:
                    balances = r_bal.json().get("balances", [])
                    for bal in balances:
                        print(f"    - Balance: ${float(bal.get('amount', 0)):.2f} {bal.get('units', 'USD')}")
                else:
                    print(f"    - Could not retrieve balance (Code: {r_bal.status_code})")
        else:
            print(f"  ❌ Invalid Key or Error: {r.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
else:
    print("\n🎤 [Deepgram STT] key not found in .env")

# 2. Check ElevenLabs
el_key = os.getenv("ELEVENLABS_API_KEY")
if el_key:
    print("\n🗣️ [ElevenLabs TTS]")
    try:
        r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": el_key})
        if r.status_code == 200:
            sub = r.json()
            used = sub.get("character_count", 0)
            limit = sub.get("character_limit", 0)
            tier = sub.get("tier", "Free")
            print(f"  Subscription Tier : {tier}")
            print(f"  Characters Used   : {used:,} / {limit:,}")
            print(f"  Remaining Chars   : {limit - used:,}")
        else:
            print(f"  ❌ Invalid Key or Error: {r.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
else:
    print("\n🗣️ [ElevenLabs TTS] key not found in .env")

# 3. Check Groq
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print("\n⚡ [Groq LPU LLM]")
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "openai/gpt-oss-20b",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            }
        )
        if r.status_code == 200:
            headers = r.headers
            print(f"  Key Status: ✅ Valid & Active")
            print(f"  Remaining Tokens (This Min)   : {headers.get('x-ratelimit-remaining-tokens', 'N/A')}")
            print(f"  Remaining Requests (This Min) : {headers.get('x-ratelimit-remaining-requests', 'N/A')}")
        else:
            print(f"  ❌ Invalid Key or Error: {r.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
else:
    print("\n⚡ [Groq LPU LLM] key not found in .env")

# 4. Check SambaNova
samba_key = os.getenv("SAMBANOVA_API_KEY")
if samba_key:
    print("\n🚀 [SambaNova Cloud LLM]")
    try:
        # Check model list as a key test
        r = requests.get("https://api.sambanova.ai/v1/models", headers={"Authorization": f"Bearer {samba_key}"})
        if r.status_code == 200:
            print(f"  Key Status: ✅ Valid & Active (Developer Tier)")
            print(f"  Note: Balance must be viewed in your SambaNova Dashboard.")
        else:
            print(f"  ❌ Key is invalid or unpaid: {r.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
else:
    print("\n🚀 [SambaNova Cloud LLM] key not found in .env")

# 5. Check Google Gemini
google_key = os.getenv("GOOGLE_API_KEY")
if google_key:
    print("\n🧠 [Google Gemini LLM]")
    try:
        # Test request
        r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={google_key}")
        if r.status_code == 200:
            print(f"  Key Status: ✅ Valid & Active (Paid Tier)")
            print(f"  Note: Your ₹1,000 credit balance must be viewed in the Google Cloud Console.")
        else:
            print(f"  ❌ Invalid Key: {r.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
else:
    print("\n🧠 [Google Gemini LLM] key not found in .env")

print("\n" + "="*60)
