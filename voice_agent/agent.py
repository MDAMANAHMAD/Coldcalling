"""
LiveKit Voice AI Cold Calling Agent Worker (Instant-Start Hindi Real Estate Specialist)
=======================================================================================
Engineered with:
- LiveKit Agent Framework v1.6+ (Agent & AgentSession)
- Google Gemini Live (gemini-2.5-flash-native-audio-latest Realtime Speech)
- Female Voice ("Aoede") with Two-Stage Presentation & Crisp Q&A

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
from livekit.plugins.google import realtime
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
# 1. HINDI FEMALE REAL ESTATE ADVISOR PERSONA
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """
You are Priya Sharma (प्रिया शर्मा), a polite, charming, and energetic female Senior Property Advisor at Skyline Luxury Realty.
You are on a live outbound phone call with a client in India.

CRITICAL VOICE & SPEED GUIDELINES:
1. ULTRA-CRISP BURSTS: Speak in short, snappy, conversational bursts (1 to 2 sentences only, under 15 words).
2. LANGUAGE: Natural, polite Hindi/Hinglish (e.g. "Namaste Aman ji!", "Main Priya baat kar rahi hoon Skyline Realty se").
3. PERMISSION FIRST: In the beginning, ask if you can share details of the new luxury 2BHK/3BHK flats.
4. ON PERMISSION: Give a quick, attractive 2-sentence highlight:
   - "Skyline Royal Palms metro ke paas hai. 2 BHK ₹85 Lakhs aur 3 BHK ₹1.25 Cr se shuru hai with rooftop pool, zero brokerage aur 10% discount! Kya aap sample flat dekhna chahenge?"
5. Q&A: Answer any question directly in 1 short sentence and invite for a free VIP site visit.

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

        return f"Bahut badiya! Maine {customer_name} ke liye {preferred_day} ko VIP site visit confirm kar diya hai. Hamari team location aur brochure WhatsApp kar degi."


# ==============================================================================
# 3. AGENT ENTRYPOINT (Instant Voice Connection)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] Hindi Real Estate Voice Agent for Room: {ctx.room.name}")
    await ctx.connect()

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    # Google Gemini Live Realtime Model (Tier-1 Paid)
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.error("GOOGLE_API_KEY environment variable is not set!")

    model = realtime.RealtimeModel(
        model="gemini-2.5-flash-native-audio-latest",
        voice="Aoede",
        temperature=0.6,
        api_key=google_api_key
    )

    session = AgentSession(
        llm=model,
    )
    agent = HindiRealEstateAgent(customer_name=customer_name)

    await session.start(room=ctx.room, agent=agent)

    # Initial spoken greeting
    initial_instructions = (
        f"Immediately greet {customer_name} in Hindi: 'Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Luxury Realty se. "
        f"Kya main aapko hamare naye 2BHK aur 3BHK luxury flats ke baare mein details bata doon?'"
    )

    # Trigger spoken greeting
    async def speak_greeting():
        await asyncio.sleep(0.5)
        try:
            logger.info("🎙️ [DISPATCHING SPOKEN GREETING]")
            session.generate_reply(instructions=initial_instructions)
        except Exception as e:
            logger.warning(f"Greeting error: {e}")

    # 1. Listen for new audio track subscriptions
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"🎙️ [AUDIO STREAM DETECTED FOR {participant.identity}]")
            asyncio.create_task(speak_greeting())

    ctx.room.on("track_subscribed", on_track_subscribed)

    # 2. Trigger greeting immediately
    asyncio.create_task(speak_greeting())


# ==============================================================================
# 4. CLI RUNNER
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
