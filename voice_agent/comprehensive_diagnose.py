import os
import sys
import asyncio
import requests
from dotenv import load_dotenv

# Load env from voice_agent/.env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print("=" * 70)
print("🔍 COMPLETE TELEPHONY & AGENT PIPELINE DIAGNOSIS")
print("=" * 70)

# 1. Check Credentials in .env
livekit_url = os.getenv("LIVEKIT_URL")
api_key = os.getenv("LIVEKIT_API_KEY")
api_secret = os.getenv("LIVEKIT_API_SECRET")
sip_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID") or os.getenv("LIVEKIT_SIP_TRUNK_ID")

groq_key = os.getenv("GROQ_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")
cartesia_key = os.getenv("CARTESIA_API_KEY")
deepgram_key = os.getenv("DEEPGRAM_API_KEY")
eleven_key = os.getenv("ELEVENLABS_API_KEY")

print(f"📡 LiveKit URL        : {livekit_url or '❌ Missing'}")
print(f"🔑 LiveKit API Key    : {api_key[:6] + '...' if api_key else '❌ Missing'}")
print(f"🔒 LiveKit Secret     : {'Present' if api_secret else '❌ Missing'}")
print(f"📞 SIP Trunk ID       : {sip_trunk_id or '❌ Missing'}")
print(f"⚡ Groq Key           : {'Present' if groq_key else '❌ Missing'}")
print(f"🧠 Google Key         : {'Present' if google_key else '❌ Missing'}")
print(f"🎙️ Cartesia Key       : {'Present' if cartesia_key else '❌ Missing'}")
print(f"🎤 Deepgram Key       : {'Present' if deepgram_key else '❌ Missing'}")
print(f"🗣️ ElevenLabs Key     : {'Present' if eleven_key else '❌ Missing'}")
print("-" * 70)

# 2. LiveKit Cloud & SIP Telephony Inspection
async def check_livekit():
    print("\n--- [1] Checking LiveKit Cloud & SIP Infrastructure ---")
    if not all([livekit_url, api_key, api_secret]):
        print("❌ Cannot test LiveKit: Missing credentials.")
        return

    from livekit import api
    from livekit.protocol.sip import (
        ListSIPInboundTrunkRequest,
        ListSIPOutboundTrunkRequest,
        ListSIPDispatchRuleRequest
    )

    lk = api.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
    try:
        # A. Check rooms
        rooms_res = await lk.room.list_rooms(api.ListRoomsRequest())
        rooms = getattr(rooms_res, "rooms", [])
        print(f"✅ LiveKit Cloud Connection: Connected successfully!")
        print(f"🏠 Active Rooms Count: {len(rooms)}")
        for r in rooms:
            print(f"   • Room '{r.name}': {r.num_participants} participants, metadata: {r.metadata[:60] if r.metadata else 'none'}")

        # B. Check Outbound Trunks
        try:
            out_trunks_res = await lk.sip.list_sip_outbound_trunk(ListSIPOutboundTrunkRequest())
            out_trunks = getattr(out_trunks_res, "items", [])
            print(f"\n📤 Outbound SIP Trunks Count: {len(out_trunks)}")
            found_target = False
            for t in out_trunks:
                is_match = (t.sip_trunk_id == sip_trunk_id)
                if is_match:
                    found_target = True
                match_str = " (MATCHES .env SIP_OUTBOUND_TRUNK_ID)" if is_match else ""
                print(f"   • Trunk ID: {t.sip_trunk_id}{match_str} | Name: '{t.name}' | Address: {t.address} | Numbers: {list(t.numbers)}")
            if not found_target and sip_trunk_id:
                print(f"   ⚠️ WARNING: Target trunk {sip_trunk_id} was NOT found in the outbound trunks list!")
        except Exception as e:
            print(f"   ⚠️ Could not list outbound trunks: {e}")

        # C. Check Inbound Trunks
        try:
            in_trunks_res = await lk.sip.list_sip_inbound_trunk(ListSIPInboundTrunkRequest())
            in_trunks = getattr(in_trunks_res, "items", [])
            print(f"\n📥 Inbound SIP Trunks Count: {len(in_trunks)}")
            for t in in_trunks:
                print(f"   • Trunk ID: {t.sip_trunk_id} | Name: '{t.name}' | Numbers: {list(t.numbers)}")
        except Exception as e:
            print(f"   ⚠️ Could not list inbound trunks: {e}")

        # D. Check Dispatch Rules (How inbound calls get routed to agents)
        try:
            rules_res = await lk.sip.list_sip_dispatch_rule(ListSIPDispatchRuleRequest())
            rules = getattr(rules_res, "items", [])
            print(f"\n🔀 SIP Dispatch Rules Count: {len(rules)}")
            for r in rules:
                rule_detail = getattr(r, "rule", None)
                print(f"   • Rule ID: {r.sip_dispatch_rule_id} | Name: '{r.name}' | Trunks: {list(r.trunk_ids)} | Rule: {rule_detail}")
        except Exception as e:
            print(f"   ⚠️ Could not list dispatch rules: {e}")

    except Exception as e:
        print(f"❌ LiveKit Cloud Connection Failed: {e}")
    finally:
        await lk.aclose()

# 3. Check AI Provider APIs
def check_providers():
    print("\n--- [2] Checking AI Service Providers ---")
    
    # A. Groq
    if groq_key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                timeout=6
            )
            if r.status_code == 200:
                print(f"✅ Groq (LPU LLM): Active & Working (HTTP 200)")
            else:
                print(f"❌ Groq Error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"❌ Groq Connection Error: {e}")
    else:
        print("⚠️ Groq: No key in .env")

    # B. Google Gemini
    if google_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={google_key}"
            r = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "hi"}]}]},
                timeout=6
            )
            if r.status_code == 200:
                print(f"✅ Google Gemini (Fallback LLM): Active & Working (HTTP 200)")
            else:
                print(f"❌ Google Gemini Error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"❌ Google Gemini Connection Error: {e}")
    else:
        print("⚠️ Google Gemini: No key in .env")

    # C. Deepgram
    if deepgram_key:
        try:
            r = requests.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {deepgram_key}"},
                timeout=6
            )
            if r.status_code == 200:
                print(f"✅ Deepgram (STT): Active & Working (HTTP 200)")
                # Check balance
                projects = r.json().get("projects", [])
                for p in projects:
                    p_id = p.get("project_id")
                    r_bal = requests.get(
                        f"https://api.deepgram.com/v1/projects/{p_id}/balances",
                        headers={"Authorization": f"Token {deepgram_key}"},
                        timeout=6
                    )
                    if r_bal.status_code == 200:
                        bals = r_bal.json().get("balances", [])
                        for b in bals:
                            print(f"   • Deepgram Project '{p.get('name')}' Balance: ${float(b.get('amount', 0)):.2f}")
            else:
                print(f"❌ Deepgram Error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"❌ Deepgram Connection Error: {e}")
    else:
        print("⚠️ Deepgram: No key in .env")

    # D. Cartesia
    if cartesia_key:
        try:
            r = requests.get(
                "https://api.cartesia.ai/voices",
                headers={"X-API-Key": cartesia_key, "Cartesia-Version": "2024-06-10"},
                timeout=6
            )
            if r.status_code == 200:
                print(f"✅ Cartesia (TTS): Active & Working (HTTP 200)")
                # Check if custom voice exists
                v_id = "0e3194d6-f1c8-490b-bf6f-149a45437d26"
                has_voice = any(v.get("id") == v_id for v in r.json())
                print(f"   • Cloned Voice ({v_id}): {'✅ Found' if has_voice else '❌ NOT Found'}")
            else:
                print(f"❌ Cartesia Error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"❌ Cartesia Connection Error: {e}")
    else:
        print("⚠️ Cartesia: No key in .env")

async def main():
    await check_livekit()
    check_providers()
    print("\n" + "=" * 70)
    print("🏁 DIAGNOSIS COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
