"""
LiveKit Voice AI Cold Calling Agent Worker (Ultra-Natural Human Voice with Breathing Pauses)
=============================================================================================
Architecture:
- STT: Deepgram Nova-2 (Hindi / Hinglish, 250ms endpointing cutoff)
- LLM: Google Gemini Flash (gemini-flash-latest, streaming reasoning engine)
- TTS: Cartesia Sonic with Sneha Empathetic Voice ID (6b02ffe5-e3cb-48c0-a023-c72f85953375)
- VAD: Local Silero VAD (250ms silence detection)

Role: Priya Sharma - Senior Real Estate Property Advisor (Skyline Luxury Realty)
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
from livekit.plugins import deepgram, google, cartesia, silero
from livekit import rtc

# Load environment variables
load_dotenv()

# Configure structured logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hindi_real_estate_agent")


# ==============================================================================
# 1. 100% NATURAL HUMAN HINDI VOICE PERSONA
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """
You are Priya Sharma (प्रिया शर्मा), a polite, friendly, and natural female Property Advisor at Skyline Luxury Realty.
You are talking directly to a client on a mobile phone call.

CRITICAL VOICE & HUMAN MODULATION RULES:
1. NATURAL HUMAN PAUSES: Use commas (,) and natural pauses so you sound completely human with realistic breathing and warm vocal modulation. Never sound robotic or flat.
2. WARM & CONVERSATIONAL: Speak in a relaxed, friendly Indian conversational tone. Use natural phrases like "Ji bilkul...", "Arey haanji Aman ji...", "Aap bataiye...".
3. SHORT HUMAN BURSTS: Keep every response strictly between 8 to 12 words (1 short natural sentence).
4. NEVER SOUND LIKE AN IVR / MACHINE: Talk like a real person having a quick, friendly conversation over the phone.

CONVERSATION FLOW:
- When they agree / say Haan: "Ji bilkul... hamara naya project metro ke paas hai. 2BHK 85 Lakhs se shuru hai."
- Pricing: "Sirf 10% down payment hai, Aman ji. Kya main sample flat dikha doon?"
- Location: "Project metro station se sirf do minute ki doori par hai."
- 1BHK: "1BHK ka area lagbhag 650 square feet hai... 45 Lakhs se shuru hai."
- 2BHK: "2BHK lagbhag 1100 square feet ka spacious flat hai, 85 Lakhs mein."

TOOL USAGE:
As soon as the client agrees for a site visit or asks for location/brochure, immediately trigger the `schedule_site_visit` tool.
"""


# ==============================================================================
# 2. AGENT CLASS & FUNCTION TOOLS
# ==============================================================================
class HindiRealEstateAgent(Agent):
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
# 3. AGENT ENTRYPOINT (Clean Initialization)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] ~400ms Natural Human Voice Agent for Room: {ctx.room.name}")
    await ctx.connect()

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    # 1. Deepgram Nova-2 STT with 250ms endpointing
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    stt = deepgram.STT(
        language="hi",
        model="nova-2",
        endpointing_ms=250,
        smart_format=True,
        api_key=deepgram_key
    )

    # 2. Google Gemini Flash LLM (gemini-flash-latest)
    google_key = os.getenv("GOOGLE_API_KEY")
    gemini_llm = google.LLM(
        model="gemini-flash-latest",
        api_key=google_key,
        temperature=0.4
    )

    # 3. Cartesia Sonic Streaming TTS (Sneha - Empathetic Natural Human Voice)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    tts = cartesia.TTS(
        api_key=cartesia_key,
        voice="6b02ffe5-e3cb-48c0-a023-c72f85953375",  # Sneha: Warm, natural female modulation
        language="hi"
    )

    # 4. Local Silero Voice Activity Detector (250ms silence detection)
    vad = silero.VAD.load(
        min_silence_duration=0.25,
        min_speech_duration=0.1
    )

    session = AgentSession(
        stt=stt,
        llm=gemini_llm,
        tts=tts,
        vad=vad,
    )
    agent = HindiRealEstateAgent(customer_name=customer_name)

    await session.start(agent=agent, room=ctx.room)

    # Wait 1.0s for audio track to be fully established and active
    await asyncio.sleep(1.0)

    # Speak greeting
    logger.info("🎙️ [SPEAKING NATURAL HUMAN GREETING OVER ACTIVE AUDIO TRACK]")
    try:
        session.say(
            f"Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Realty se... Hamare naye luxury flats ke baare mein bata doon?",
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
