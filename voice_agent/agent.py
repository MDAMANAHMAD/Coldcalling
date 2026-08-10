"""
LiveKit Voice AI Cold Calling Agent Worker (Sub-800ms Pre-Warmed Pipeline & Jitter-Free Audio)
=============================================================================================
Architecture:
- STT: Deepgram Nova-2 (Hindi / Hinglish, 180ms endpointing cutoff)
- LLM: Google Gemini Flash (gemini-flash-latest, Pre-warmed TLS socket)
- TTS: Cartesia Sonic with Kavita Hindi Voice (56e35e2d-6eb6-4226-ab8b-9776515a7094, 24kHz Native Rate)
- VAD: Local Silero VAD (200ms silence detection)
- Pre-Warming: Pre-establishes API sockets on startup to eliminate cold-start lag

Role: Kavita Sharma - Senior Real Estate Property Advisor (Skyline Luxury Realty)
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
    llm
)
from livekit.plugins import deepgram, google, cartesia, silero
from livekit import rtc

# Load environment variables
load_dotenv()

# Configure structured logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("kavita_real_estate_agent")


# ==============================================================================
# 1. KAVITA SHARMA HINDI VOICE PERSONA & KNOWLEDGE BASE
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """
You are Kavita Sharma (कविता शर्मा), a polite, friendly, and expert Property Advisor at Skyline Luxury Realty.
You are on a live phone call with a prospective client.

CRITICAL VOICE & SPEED RULES (MANDATORY):
1. MICRO-RESPONSES (8-10 WORDS MAXIMUM): Always answer in 1 short, crisp sentence (strictly under 10 words). Short answers guarantee sub-second instant response with zero jitter or voice break.
2. NATURAL HINDI/HINGLISH: Speak in warm, polite, conversational Hindi. Use friendly words like "Ji bilkul", "Haanji Aman ji".
3. NEVER EXPLAIN LENGTHILY: State the fact directly, then ask a quick follow-up question.

==================================================
PROJECT KNOWLEDGE BASE (INSTANT FAST-ANSWER DATA):
==================================================
1. PRICING:
   - 1BHK: "1BHK 45 Lakhs se shuru hai. Carpet area 650 square feet."
   - 2BHK: "2BHK 85 Lakhs se shuru hai. Carpet area 1100 square feet."
   - 3BHK: "3BHK 1.25 Crore se shuru hai. Carpet area 1550 square feet."

2. PAYMENT & LOANS:
   - Down Payment: "Sirf 10% down payment hai, baaki bank loan ho jayega."
   - Bank Loans: "HDFC, SBI aur ICICI bank se pre-approved home loan hai."
   - Offers: "Abhi booking par zero stamp duty aur modular kitchen free hai."

3. LOCATION & CONNECTIVITY:
   - Metro: "Project metro station se sirf do minute ki walking distance par hai."
   - Airport/Highway: "Highway se 5 minute aur airport se sirf 25 minute door hai."
   - Schools/Hospitals: "Top international schools aur hospitals 2 kilometer ke andar hain."

4. AMENITIES:
   - Facilities: "Clubhouse, swimming pool, gym, badminton court aur play area hai."
   - Parking: "Har flat ke sath dedicated covered car parking milti hai."
   - Security: "24/7 CCTV surveillance aur gated 3-tier security hai."

5. POSSESSION & RERA:
   - Possession Date: "Possession December 2026 tak mil jayegi, RERA approved project hai."

6. SITE VISIT BOOKING:
   - Site Visit: "Free VIP cab pickup ke sath site visit available hai. Kya kal book kar doon?"

7. NEGATIVE / BUSY CUSTOMER:
   - Not Interested: "Koi baat nahi sir, kya main WhatsApp par brochure bhej doon?"
   - Call Later: "Ji bilkul, main aapko shaam ko 6 baje call karti hoon."

TOOL USAGE:
As soon as the client agrees for a site visit or gives a preferred day/time, immediately trigger `schedule_site_visit`.
"""


# ==============================================================================
# 2. AGENT CLASS & FUNCTION TOOLS
# ==============================================================================
class KavitaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji"):
        instructions = f"{HINDI_REAL_ESTATE_PROMPT}\n\nAap abhi {customer_name} se call par baat kar rahi hain."
        super().__init__(instructions=instructions)

    @function_tool(description="Schedule a free VIP property site visit for the client.")
    async def schedule_site_visit(
        self,
        customer_name: str,
        preferred_day: str,
        flat_type: str = "2BHK / 3BHK",
        notes: str = ""
    ) -> str:
        logger.info("=" * 60)
        logger.info("🏠 [HINDI REAL ESTATE SITE VISIT BOOKED]")
        logger.info(f"👤 Client Name     : {customer_name}")
        logger.info(f"📅 Preferred Day   : {preferred_day}")
        logger.info(f"🏢 Flat Type       : {flat_type}")
        logger.info(f"📝 Notes           : {notes}")
        logger.info("=" * 60)

        visit_record = {
            "customer_name": customer_name,
            "preferred_day": preferred_day,
            "flat_type": flat_type,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "site_visit_confirmed"
        }

        try:
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/property_visits.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(visit_record) + "\n")
        except Exception as e:
            logger.error(f"Failed to save visit record: {e}")

        return f"Maine {preferred_day} ko VIP visit confirm kar diya hai."


# ==============================================================================
# 3. AGENT ENTRYPOINT (Pre-Warmed High-Speed Pipeline)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] High-Speed Kavita Voice Agent for Room: {ctx.room.name}")
    await ctx.connect()

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    # 1. Deepgram Nova-2 STT with 180ms endpointing (fast turn-around)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    stt = deepgram.STT(
        language="hi",
        model="nova-2",
        endpointing_ms=180,
        smart_format=True,
        api_key=deepgram_key
    )

    # 2. Google Gemini Flash LLM (gemini-flash-latest, deterministic temperature)
    google_key = os.getenv("GOOGLE_API_KEY")
    gemini_llm = google.LLM(
        model="gemini-flash-latest",
        api_key=google_key,
        temperature=0.1
    )

    # Pre-warm LLM socket in background task to eliminate first-token delay
    async def warm_llm():
        try:
            w_ctx = llm.ChatContext()
            w_ctx.messages().append(llm.ChatMessage(role="user", content=["warmup"]))
            w_stream = gemini_llm.chat(chat_ctx=w_ctx)
            async for _ in w_stream:
                break
            logger.info("⚡ [GEMINI LLM SOCKET PRE-WARMED SUCCESSFULLY]")
        except Exception as e:
            logger.debug(f"Warmup notice: {e}")

    asyncio.create_task(warm_llm())

    # 3. Cartesia Sonic 24kHz Native Streaming TTS (Kavita Voice ID)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    tts = cartesia.TTS(
        api_key=cartesia_key,
        voice="56e35e2d-6eb6-4226-ab8b-9776515a7094",  # Dedicated Kavita Hindi Voice
        language="hi",
        sample_rate=24000  # 24kHz WebRTC native rate
    )

    # 4. Local Silero Voice Activity Detector (200ms silence cutoff)
    vad = silero.VAD.load(
        min_silence_duration=0.20,
        min_speech_duration=0.08
    )

    session = AgentSession(
        stt=stt,
        llm=gemini_llm,
        tts=tts,
        vad=vad,
        min_consecutive_speech_delay=0.10,
    )
    agent = KavitaRealEstateAgent(customer_name=customer_name)

    await session.start(agent=agent, room=ctx.room)

    # Wait 0.8s for audio track to be fully established and active
    await asyncio.sleep(0.8)

    # Speak comprehensive opening greeting with Kavita persona
    logger.info("🎙️ [SPEAKING GREETING WITH KAVITA PERSONA]")
    try:
        session.say(
            f"Namaste {customer_name}! Main Kavita baat kar rahi hoon Skyline Realty se. Hamara naya luxury 2BHK aur 3BHK project metro ke paas launch hua hai, sirf 85 Lakhs se shuru. Kya aap iski details ya pricing jaan-na chahenge?",
            allow_interruptions=True
        )
    except Exception as e:
        logger.warning(f"Greeting error: {e}")


# ==============================================================================
# 4. CLI RUNNER
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
