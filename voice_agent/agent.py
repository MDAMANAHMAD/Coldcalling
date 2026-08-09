"""
LiveKit Voice AI Cold Calling Agent Worker (Ultra-Fast Natural Spoken Hindi Specialist)
======================================================================================
Optimized with:
- Natural Human Conversational Pace (0.92x speaking rate with human pauses)
- Telephony-Class Audio Enhancement for Crystal-Clear Mobile Sound
- Sub-2-Second First-Byte Speech Latency (Chunked Streaming)
- Voice: Google Neural2 Indian Female (hi-IN-Neural2-A)

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
You are Priya Sharma (प्रिया शर्मा), a polite, friendly, and charming female Property Advisor at Skyline Luxury Realty.
You are talking to a customer on a live mobile phone call.

CRITICAL VOICE & SPEED RULES:
1. NATURAL HUMAN PACE: Speak warmly, politely, and casually like a real person talking on the phone. Use natural conversational expressions (e.g. "Ji bilkul", "Achha suniye", "Haanji").
2. SHORT CRISP REPLIES: Keep each answer strictly between 10 to 15 words (1 short sentence). This ensures speech starts immediately in under 1 second.
3. MODULATION & PAUSES: Speak with gentle modulation, not like a robot. Never read long paragraphs.

CONVERSATION FLOW:
- Greeting: "Namaste Aman ji! Main Priya baat kar rahi hoon Skyline Realty se. Kya main aapse 1 minute baat kar sakti hoon?"
- When they agree / say Haan: "Hamare naye project Skyline Royal Palms mein 2BHK 85 Lakhs se shuru hai metro ke paas. Kya aap sample flat dekhna chahenge?"
- Pricing: "Ji, sirf 10% down payment par easy EMI available hai. Kya main aapke liye free VIP site visit arrange kar doon?"
- Location: "Project metro station se sirf 2 minute ki doori par hai."
"""


# ==============================================================================
# 2. AGENT ENTRYPOINT (Optimized Streaming Pipeline)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    logger.info(f"[JOB STARTED] Natural Human Real Estate Voice Agent for Room: {ctx.room.name}")
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

    # Low-latency Indian Hindi / Hinglish Speech-to-Text
    stt = google.STT(
        languages=["hi-IN", "en-IN"],
        api_key=google_api_key
    )

    # Ultra-Fast Gemini 2.5 Flash Streaming LLM
    gemini_llm = google.LLM(
        model="gemini-2.5-flash",
        api_key=google_api_key,
        temperature=0.5
    )

    # Natural Human-Like Hindi Female TTS (Telephony Optimized, 0.92x Speed)
    tts = google.TTS(
        language="hi-IN",
        gender="female",
        voice_name="hi-IN-Neural2-A",
        speaking_rate=0.92,                          # Natural, warm, relaxed human pace (not fast)
        pitch=0.4,                                   # Warm melodic female tone
        effects_profile_id="telephony-class-application", # Crystal clear on mobile phone speakers
        use_streaming=True,                          # Instant word-by-word streaming
        api_key=google_api_key
    )

    # Silero VAD tuned for ultra-fast response (<200ms silence threshold)
    vad = silero.VAD.load(
        min_silence_duration=0.25,
        min_speech_duration=0.1
    )

    initial_prompt = f"{HINDI_REAL_ESTATE_PROMPT}\n\nAap abhi {customer_name} se call par baat kar rahi hain."

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
        min_endpointing_delay=0.15                   # Replies immediately (150ms) when you stop talking
    )

    pipeline_agent.start(ctx.room)

    # Natural Spoken Greeting
    greeting_text = (
        f"Namaste {customer_name}! Main Priya baat kar rahi hoon Skyline Realty se. "
        f"Kya main aapko hamare naye luxury flats ke baare mein bata doon?"
    )

    await asyncio.sleep(0.8)
    logger.info("🎙️ [SPEAKING NATURAL HUMAN GREETING]")
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
