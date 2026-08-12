"""
LiveKit Voice AI Cold Calling Agent Worker (Sub-1s Instant Telephony Pipeline)
=============================================================================
Speed Architecture:
- Immediate Greeting: Fires instant greeting on room session activation
- STT: Deepgram Nova-2 (Hindi / Hinglish, 80ms fast cutoff)
- LLM: Groq LPU Llama-3.1 8B Instant (<80ms response) with Google Gemini Flash fallback
- TTS: ElevenLabs Turbo v2.5 with Fast Chunk Schedule [30, 60, 100] & Bella Voice
- VAD: Silero VAD (0.25s TurnDetector compliance)
- Worker Options: num_idle_processes=0, load_threshold=0.95

Role: Priya Sharma - Senior Property Advisor (Skyline Luxury Realty)
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
)
from livekit.plugins import deepgram, openai, elevenlabs, cartesia, google, silero
from livekit import rtc

# Load environment variables
load_dotenv()

# Configure structured logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("enterprise_voice_agent")


# ==============================================================================
# 1. PRIYA SHARMA HINDI VOICE PERSONA & CRISP KNOWLEDGE BASE
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """
You are Priya Sharma (प्रिया शर्मा), a polite, professional Senior Property Advisor at Skyline Luxury Realty.
You are on a live phone call with a prospective client.

CRITICAL VOICE & SPEED RULES (MANDATORY):
1. INSTANT 1-SENTENCE REPLIES (MAXIMUM 6-8 WORDS): Always reply in exactly 1 short sentence (under 8 words). Short replies guarantee instant <1 second replies.
2. NATURAL HINDI/HINGLISH: Speak warm, polite conversational Hindi ("Ji bilkul", "Haanji Aman ji").
3. NEVER GIVE LONG PARAGRAPHS: Give the direct fact immediately, then ask a quick question.

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
   - Metro: "Project metro station se sirf do minute walking distance par hai."
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
class PriyaRealEstateAgent(Agent):
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
# 3. AGENT ENTRYPOINT (Sub-1s Instant Response Architecture)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] Enterprise Voice Agent for Room: {ctx.room.name}")
    await ctx.connect()

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    # 1. Deepgram Nova-2 STT (80ms Ultra-Fast Cutoff)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    stt = deepgram.STT(
        language="hi",
        model="nova-2",
        endpointing_ms=80,
        smart_format=True,
        api_key=deepgram_key
    )

    # 2. LLM Engine: Groq LPU Llama-3.1 8B Instant (<75ms First Token)
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if openai_key and openai_key.startswith("sk-"):
        logger.info("⚡ [LLM ENGINE] Using Ultra-Reliable OpenAI GPT-4o-mini")
        llm = openai.LLM(
            model="gpt-4o-mini",
            api_key=openai_key,
            temperature=0.0
        )
    elif groq_key and groq_key.startswith("gsk_"):
        logger.info("⚡ [LLM ENGINE] Using Ultra-Fast Groq LPU (Llama-3.1 8B Instant)")
        llm = openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.1-8b-instant",
            api_key=groq_key,
            temperature=0.0
        )
    else:
        logger.info("🧠 [LLM ENGINE] Using Google Gemini Flash")
        google_key = os.getenv("GOOGLE_API_KEY")
        llm = google.LLM(
            model="gemini-flash-latest",
            api_key=google_key,
            temperature=0.0
        )

    # 3. TTS Engine: ElevenLabs Turbo v2.5 with Fast Chunk Schedule [30, 60, 100]
    eleven_key = os.getenv("ELEVENLABS_API_KEY")
    if eleven_key and len(eleven_key) > 10:
        logger.info("🎙️ [TTS ENGINE] Using ElevenLabs Turbo v2.5 (Bella)")
        tts = elevenlabs.TTS(
            api_key=eleven_key,
            voice_id="hpp4J3VqNfWAUOO0d1Us",  # Bella - Studio conversational voice
            model="eleven_turbo_v2_5",
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.35,
                similarity_boost=0.80,
                style=0.15,
                use_speaker_boost=True
            ),
            chunk_length_schedule=[30, 60, 100],  # Begins speech output on first 2 words
            streaming_latency=3
        )
    else:
        logger.info("🎙️ [TTS ENGINE] Using Cartesia Sonic Native 24kHz")
        cartesia_key = os.getenv("CARTESIA_API_KEY")
        tts = cartesia.TTS(
            api_key=cartesia_key,
            voice="56e35e2d-6eb6-4226-ab8b-9776515a7094",
            language="hi",
            sample_rate=24000
        )

    # 4. Local Silero Voice Activity Detector (0.25s TurnDetector compliance)
    vad = silero.VAD.load(
        min_silence_duration=0.25,
        min_speech_duration=0.06
    )

    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
    )
    agent = PriyaRealEstateAgent(customer_name=customer_name)

    await session.start(agent=agent, room=ctx.room)

    # Speak greeting immediately when session connects
    greeting_text = (
        f"Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Realty se. "
        "Hamara naya luxury 2BHK project launch hua hai sirf 85 Lakhs se shuru. "
        "Kya aap details jaan-na chahenge?"
    )

    logger.info("🎙️ [TRIGGERING INSTANT GREETING]")
    try:
        session.say(greeting_text, allow_interruptions=True)
    except Exception as e:
        logger.warning(f"Greeting error: {e}")


# ==============================================================================
# 4. CLI RUNNER (Optimized for High-Capacity Cloud VPS)
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            num_idle_processes=0,     # Low memory footprint
            load_threshold=0.95,      # High availability
        )
    )
