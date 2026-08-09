"""
LiveKit Voice AI Cold Calling Agent Worker (Zero-Buffer Micro-Burst Hindi Specialist)
====================================================================================
Engineered with:
- LiveKit Agent Framework v1.6+ (Agent & AgentSession)
- Google Gemini Live Native Speech (gemini-2.5-flash-native-audio-latest)
- Strict Micro-Burst Rule (Under 10 words per response) to eliminate telephony buffer lag
- Warm Natural Female Voice ("Aoede")

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
# 1. ZERO-BUFFER MICRO-BURST HINDI VOICE PERSONA
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """
You are Priya Sharma (प्रिया शर्मा), a polite and friendly female Property Advisor at Skyline Luxury Realty.
You are on a live mobile phone call.

CRITICAL VOICE & SPEED RULE (ZERO TELEPHONY LAG):
1. MICRO-BURSTS ONLY: Never speak more than 8 to 10 words in a single reply (1 short sentence only). Long sentences cause telephone audio lag.
2. NATURAL & WARM: Speak naturally in polite Hindi with gentle female tone.
3. CONVERSATIONAL TURNS: Answer briefly, then let the customer speak.

EXACT CONVERSATIONAL RESPONSES (Under 10 words):
- Greeting: "Namaste Aman ji! Main Priya baat kar rahi hoon Skyline Realty se."
- When they say Haan / Hello: "Hamara naya project metro ke paas hai. 2BHK 85 Lakhs se shuru hai."
- Pricing question: "Sirf 10% down payment hai. Kya main sample flat dikha doon?"
- Location question: "Project metro station se sirf do minute door hai."
- Booking confirmation: "Bahut badiya! Main aapka VIP visit schedule kar deti hoon."

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
# 3. AGENT ENTRYPOINT (Instant Voice Connection)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] Micro-Burst Real Estate Voice Agent for Room: {ctx.room.name}")
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
        temperature=0.3,
        api_key=google_api_key
    )

    session = AgentSession(
        llm=model,
    )
    agent = HindiRealEstateAgent(customer_name=customer_name)

    await session.start(room=ctx.room, agent=agent)

    # Initial short greeting (Under 10 words)
    async def delayed_greeting():
        await asyncio.sleep(0.8)
        logger.info("🎙️ [DISPATCHING SHORT GREETING]")
        try:
            session.generate_reply(
                user_input=f"Speak in under 8 words in Hindi: 'Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Realty se.'"
            )
        except Exception as e:
            logger.warning(f"Greeting error: {e}")

    asyncio.create_task(delayed_greeting())


# ==============================================================================
# 4. CLI RUNNER
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
