"""
LiveKit Voice AI Cold Calling Agent Worker (High-Speed Google Streaming Pipeline)
================================================================================
Engineered with:
- LiveKit Agent Framework (VoicePipelineAgent)
- Google Cloud Speech-to-Text (Hindi 'hi-IN' + Hinglish)
- Google Gemini 2.5 Flash (Streaming LLM via Google API Key)
- Google Cloud Neural2 Text-to-Speech (Indian Female 'hi-IN-Neural2-A')
- Silero VAD for sub-second turn-taking and instant interruption handling

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
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import google, silero
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

CONVERSATION INSTRUCTIONS:
1. GREETING:
   When the call connects, greet the client warmly in Hindi:
   "Namaste Aman ji! Main Priya baat kar rahi hoon Skyline Luxury Realty se. Kya main aapko hamare naye 2BHK aur 3BHK luxury flats ke baare mein poori details bata doon?"
2. COMPREHENSIVE OVERVIEW:
   When the client says "Yes", "Haan", "Batao", or asks any question, give an attractive 2-sentence overview:
   "Skyline Royal Palms metro station aur highway se sirf 2 minute ki doori par hai. Yahan 2 BHK ₹85 Lakhs se aur 3 BHK ₹1.25 Crore se shuru hai with rooftop pool, zero brokerage aur 10% discount! Kya aap weekend par sample flat dekhne ke liye free VIP site visit karna chahenge?"
3. CRISP REPLIES:
   Answer any question directly in short, crisp 1-2 sentence Hindi bursts (under 20 words).
"""


# ==============================================================================
# 2. AGENT ENTRYPOINT (Google High-Speed Pipeline)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] High-Speed Real Estate Voice Agent for Room: {ctx.room.name}")
    await ctx.connect()

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    google_api_key = os.getenv("GOOGLE_API_KEY")

    # Fast Indian Hindi / Hinglish Speech-to-Text
    stt = google.STT(
        languages=["hi-IN", "en-IN"],
        api_key=google_api_key
    )

    # Ultra-Fast Gemini 2.5 Flash Streaming LLM
    gemini_llm = google.LLM(
        model="gemini-2.5-flash",
        api_key=google_api_key,
        temperature=0.6
    )

    # Google Neural2 Indian Hindi Female Text-to-Speech
    tts = google.TTS(
        language="hi-IN",
        gender="female",
        voice_name="hi-IN-Neural2-A",
        api_key=google_api_key
    )

    # Silero Voice Activity Detector for instant turn-taking (<0.3s)
    vad = silero.VAD.load(
        min_silence_duration=0.3,
        min_speech_duration=0.1
    )

    initial_prompt = f"{HINDI_REAL_ESTATE_PROMPT}\n\nAap abhi {customer_name} se live phone call par baat kar rahi hain."

    # Build Voice Pipeline Agent
    pipeline_agent = VoicePipelineAgent(
        vad=vad,
        stt=stt,
        llm=gemini_llm,
        tts=tts,
        chat_ctx=llm.ChatContext().append(
            role="system",
            text=initial_prompt
        ),
        allow_interruptions=True,
        interrupt_min_words=1,
        min_endpointing_delay=0.3
    )

    pipeline_agent.start(ctx.room)

    # Spoken greeting trigger
    greeting_text = (
        f"Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Luxury Realty se. "
        f"Kya main aapko hamare naye 2BHK aur 3BHK luxury flats ke baare mein poori details bata doon?"
    )

    await asyncio.sleep(1.0)
    logger.info("🎙️ [SPEAKING GREETING VIA GOOGLE NEURAL2 TTS]")
    try:
        await pipeline_agent.say(greeting_text, allow_interruptions=True)
    except Exception as e:
        logger.warning(f"Greeting dispatch error: {e}")


# ==============================================================================
# 3. CLI RUNNER
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
