"""
LiveKit Voice AI Cold Calling Agent Worker (Ultra-Low Latency ~400ms Streaming Pipeline)
========================================================================================
Architecture:
- STT: Deepgram Nova-2 (Hindi / Hinglish, ~100ms latency)
- LLM: Google Gemini Flash (gemini-flash-latest, streaming reasoning engine)
- TTS: Cartesia Sonic (Ultra-Realistic Natural Hindi Voice, streaming audio)
- VAD: Silero VAD (250ms silence cutoff for instant interruption and turn-taking)

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
# 1. NATURAL HUMAN HINDI VOICE PERSONA
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """
You are Priya Sharma (प्रिया शर्मा), a polite and friendly female Property Advisor at Skyline Luxury Realty.
You are on a live mobile phone call with a customer.

CRITICAL VOICE & SPEED RULES:
1. NATURAL HUMAN TALKING PACE: Speak in a relaxed, warm, and natural conversational pace like a real person talking on the phone. Never rush.
2. SHORT CONVERSATIONAL BURSTS: Keep every response strictly between 8 to 12 words (1 short sentence only). This guarantees sub-500ms voice response time.
3. CONVERSATIONAL TONE: Use polite, friendly words like "Ji bilkul", "Achha suniye", "Haanji Aman ji".

CONVERSATION FLOW:
- When they agree / say Haan: "Hamara naya project metro ke paas hai. 2BHK 85 Lakhs se shuru hai."
- Pricing: "Sirf 10% down payment hai. Kya main sample flat dikha doon?"
- Location: "Project metro station se sirf do minute door hai."

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
# 3. AGENT ENTRYPOINT (Ultra-Low Latency ~400ms Pipeline)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] ~400ms Low-Latency Voice Agent for Room: {ctx.room.name}")
    await ctx.connect()

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    # 1. Deepgram Nova-2 STT (~100ms)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    stt = deepgram.STT(
        language="hi",
        api_key=deepgram_key
    )

    # 2. Google Gemini Flash LLM (gemini-flash-latest)
    google_key = os.getenv("GOOGLE_API_KEY")
    gemini_llm = google.LLM(
        model="gemini-flash-latest",
        api_key=google_key,
        temperature=0.3
    )

    # 3. Cartesia Sonic Streaming TTS (~120ms audio latency)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    tts = cartesia.TTS(
        api_key=cartesia_key,
        language="hi"
    )

    # 4. Silero Voice Activity Detector (250ms silence detection)
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

    greeting_dispatched = False

    def trigger_greeting():
        nonlocal greeting_dispatched
        if greeting_dispatched:
            return
        greeting_dispatched = True
        logger.info("🎙️ [CALL PICKED UP -> SPEAKING INSTANT GREETING VIA TTS]")
        try:
            session.say(
                f"Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Realty se. Hamare naye luxury flats ke baare mein bata doon?",
                allow_interruptions=True
            )
        except Exception as e:
            logger.warning(f"Greeting error: {e}")

    # 1. If phone participant is already connected
    if len(ctx.room.remote_participants) > 0:
        trigger_greeting()

    # 2. When phone answers
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logger.info(f"📞 [CALL ANSWERED BY {participant.identity}]")
        trigger_greeting()

    # 3. When audio track starts streaming
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"🎙️ [AUDIO STREAM ACTIVE FOR {participant.identity}]")
            trigger_greeting()


# ==============================================================================
# 4. CLI RUNNER
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
