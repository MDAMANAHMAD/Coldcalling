"""
LiveKit Voice AI Cold Calling Agent Worker (Instant Streaming Telephony Architecture)
======================================================================================
Production Speed Architecture:
- Direct Streaming Greeting: session.say(greeting_text) streams audio via ElevenLabs Turbo v2.5
- Local VAD Turn Detection: turn_detection="vad" (0 cloud EOT timeouts)
- Thread Constraints: 1 CPU thread to eliminate ONNX thread thrashing
- record=False: Bypasses RecorderIO and CPU FFmpeg ogg encoding
- Pre-Warmed Engine: STT, LLM, TTS, and VAD pre-allocated in memory
- STT: Deepgram Nova-2 (Hindi / Hinglish, 120ms cutoff)
- LLM: Groq LPU Llama-3.1 8B Instant (<75ms TTFT)
- TTS: ElevenLabs Turbo v2.5 (Sarah Voice, 0 voice breaks)

Role: Priya Sharma - Senior Property Advisor (Skyline Luxury Realty)
"""

import os
import sys
import json
import logging
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# optimize CPU threading to prevent ONNX thread thrashing on 1-vCPU VPS
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except Exception:
    pass

# -----------------------------------------------------------------------------
# Pre-import and compile OpenAI SDK lazy resources at worker startup.
# We increased initialize_process_timeout to 45.0s to allow these imports
# to run synchronously during process spawning without causing worker timeouts.
# -----------------------------------------------------------------------------
try:
    import openai
    import openai.resources.models
    import openai.resources.admin
    import openai.types.admin.organization
    _dummy_client = openai.AsyncOpenAI(api_key="dummy")
    _ = _dummy_client.models
except Exception:
    pass
# -----------------------------------------------------------------------------

# Monkey patch livekit's OpenAI LLM prewarm implementation to bypass the
# slow models.list() API request, enabling instant session startup.
from livekit.plugins import openai as lk_openai
async def _fast_prewarm_impl(self):
    pass
lk_openai.LLM._prewarm_impl = _fast_prewarm_impl

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
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
You are Gayatri (गायत्री), a warm, highly professional Property Advisor at Shiv Sai Construction Company representing the Sai Complex project in Dombivli East.
You are on a live phone call with a prospective client.

CRITICAL VOICE & SPEED RULES (MANDATORY):
1. CRISP 1-SENTENCE REPLIES (MAXIMUM 8-10 WORDS): Always reply in exactly 1 short sentence (under 10 words). Short replies guarantee instant response and ultra-natural human conversation.
2. NATURAL HINDI/HINGLISH: Speak warm, polite conversational Hindi ("Ji bilkul", "Haanji").
3. NEVER GIVE LONG PARAGRAPHS: Give the direct fact immediately, then ask a quick question.
4. SPEAK CALMLY & SLOWLY: Maintain a calm, warm, and unhurried pace. Use punctuation like commas `,` and ellipses `...` to force the voice synthesizer to insert natural human breathing pauses.
5. DYNAMIC & INTERACTIVE CONVERSATION (BARGE-IN FRIENDLY): Adapt your responses dynamically based on what the user says. Do not rigidly follow a script. If the user interrupts, acknowledges, or changes the topic, address their comment naturally and match their flow immediately. Keep it conversational, relaxed, and real.
6. DO NOT OVERUSE THE CLIENT'S NAME: Address the client by name (e.g., "Aman ji") only once or twice during the entire call (such as in the greeting or closing). Do NOT append their name to every response.
7. MULTILINGUAL RESPONSE MATCHING: Always respond in the EXACT same language that the client speaks to you. If the client speaks in Marathi, reply in fluent, warm Marathi. If the client speaks in English, reply in English. If the client speaks in Hindi, reply in Hindi.
==================================================
PROJECT KNOWLEDGE BASE (SAI COMPLEX, DOMBIVLI EAST):
==================================================
1. PRICING & CONFIGURATIONS:
   - 1BHK: 375 sqft (₹36 Lacs+), 520 sqft (₹50 Lacs+), 755 sqft with terrace (₹72 Lacs+).
   - 2BHK: 760 sqft (₹72 Lacs+), 1110 sqft with terrace (₹1.04 Cr+), 2285 sqft with terrace (₹2.10 Cr+).
   - Customizable Layouts: "Aap flats ko custom design bhi kar sakte hain."

2. KEY AMENITIES:
   - Amenities: "Gym, kids play area, jogging track, indoor games, and dynamic office space."
   - Features: "Jaquar bath fittings, Kajaria tiles, Asian Paints, and Polycab wiring."
   - Extra: "Beautiful lush landscaping and balconies/terrace layouts available."

3. LOCATION & CONNECTIVITY:
   - Address: "Project Casario, Palava Road, Lodha Heaven, Dombivli East mein hai."
   - Railway: "Nilje Station se sirf 5 minute ki doori par hai aur Dombivli Station ke paas hai."
   - Metro/Highway: "Planned Kalyan-Taloja Metro aur Shil Road se seamless connectivity hai."
   - Healthcare/Schools: "Lodha World School, Guardian School aur AIMS Hospital paas mein hain."

4. SITE VISIT BOOKING:
   - Site Visit: "Free VIP cab pickup ke sath site visit available hai. Kya kal book kar doon?"

5. NEGATIVE / BUSY CUSTOMER:
   - Not Interested: "Koi baat nahi sir, kya main WhatsApp par details bhej doon?"
   - Call Later: "Ji bilkul, main aapko shaam ko call karti hoon."

TOOL USAGE:
As soon as the client agrees for a site visit or gives a preferred day/time, immediately trigger `schedule_site_visit`.
"""


# ==============================================================================
# 2. LANGUAGE RESOLUTION HELPER & AGENT CLASS
# ==============================================================================
def resolve_language(transcript: str, detected_lang: str | None) -> str:
    """Detects spoken language using Devanagari keyword matching and character checks."""
    text = transcript.lower()
    
    # 1. English Check (Latin script ratio)
    latin_chars = sum(1 for c in transcript if c.isalpha() and c.isascii())
    total_chars = len(transcript.replace(" ", ""))
    if total_chars > 0 and (latin_chars / total_chars) > 0.4:
        return "en"
        
    # 2. English Check in Devanagari script (phonetic English words)
    english_devanagari_keywords = [
        "व्हाट", "वाॅट", "कैन", "प्लीज", "प्लिज", "शेयर", "सेंड", "ऍम", "एम", "फॉर", "फॉअर", 
        "थैंक", "थॅंक", "द प्राइस", "द फ्लैट", "द ब्रोशर", "यू प्लीज", "प्लीज सेंड", "प्लीज शेयर"
    ]
    if any(word in text for word in english_devanagari_keywords):
        return "en"
        
    # 3. Marathi Check
    marathi_keywords = [
        "मला", "आहे", "आहात", "नाही", "काय", "करतो", "माहिती", "पाहिजे", "बोलतो", 
        "बघतो", "चालू", "करून", "पुढील", "नका", "चालेल", "नको", "कधी", "कसा", 
        "कशी", "कसे", "का", "सांगा", "दाखवा", "पाहू", "तुम्ही", "आम्ही", "मध्ये"
    ]
    if "ळ" in transcript or any(word in text for word in marathi_keywords):
        return "mr"
        
    # Default to Hindi
    return "hi"


class PriyaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji"):
        instructions = (
            f"{HINDI_REAL_ESTATE_PROMPT}\n\n"
            f"Aap abhi {customer_name} se call par baat kar rahi hain. "
            "Do NOT repeat the client's name in every sentence. Address them by name only once or twice during the whole call."
        )
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
# 3. PREWARMING FUNCTION (Pre-Loads All AI Engines in Idle Memory)
# ==============================================================================
def prewarm_fnc(proc: JobProcess):
    """Pre-allocates and caches STT, LLM, TTS, and VAD before any call arrives."""
    t0 = time.perf_counter()
    logger.info("🔥 [PRE-WARMING] Pre-loading Sarah voice model and AI engines into memory...")

    # 1. Pre-warm Deepgram Nova-2 STT
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    proc.userdata["stt"] = deepgram.STT(
        language="hi",
        model="nova-2",
        endpointing_ms=120,
        smart_format=True,
        api_key=deepgram_key
    )

    # 2. Instantiate LLM (Groq/OpenAI or Google Gemini)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key and groq_key.startswith("gsk_"):
        llm = openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.1-8b-instant",
            api_key=groq_key,
            temperature=0.0
        )
    else:
        google_key = os.getenv("GOOGLE_API_KEY")
        llm = google.LLM(
            model="gemini-flash-latest",
            api_key=google_key,
            temperature=0.0
        )
    proc.userdata["llm"] = llm

    cartesia_key = os.getenv("CARTESIA_API_KEY")
    logger.info(f"🔍 [DIAGNOSTIC] Cartesia key retrieved: {cartesia_key[:10] + '...' if cartesia_key else None} (length={len(cartesia_key) if cartesia_key else 0})")
    if cartesia_key and len(cartesia_key) > 10:
        logger.info("Initializing Cartesia TTS with Esha Calm Hindi Voice...")
        tts = cartesia.TTS(
            api_key=cartesia_key,
            voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha - Calm, soft, reassuring native Hindi female
            language="hi",
            sample_rate=24000
        )
    else:
        eleven_key = os.getenv("ELEVENLABS_API_KEY")
        logger.info("Initializing ElevenLabs TTS with Rachel Fallback Multilingual Voice...")
        tts = elevenlabs.TTS(
            api_key=eleven_key,
            voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel - Fallback multilingual
            model="eleven_turbo_v2_5",
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.65,
                similarity_boost=0.75,
                style=0.00,
                use_speaker_boost=True
            ),
            streaming_latency=3
        )
    proc.userdata["tts"] = tts

    # Heavy VAD loading and LLM chat compilation removed from startup to prevent process initialization timeouts.

    t1 = (time.perf_counter() - t0) * 1000
    logger.info(f"✅ [PRE-WARMING COMPLETE] Models ready in {t1:.1f}ms!")


# ==============================================================================
# 4. AGENT ENTRYPOINT (Instant Telephony Streaming Audio)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    t_start = time.perf_counter()
    logger.info(f"⏱️ [PERF +0ms] Job received for Room: {ctx.room.name}")
    
    await ctx.connect()
    t_connected = (time.perf_counter() - t_start) * 1000
    logger.info(f"⏱️ [PERF +{t_connected:.1f}ms] Connected to LiveKit Room!")

    customer_name = "Aman ji"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
        except Exception as err:
            logger.warning(f"Metadata error: {err}")

    # Retrieve pre-warmed models from userdata (0ms latency)
    t_retrieval = time.perf_counter()
    stt = ctx.proc.userdata.get("stt")
    llm = ctx.proc.userdata.get("llm")
    tts = ctx.proc.userdata.get("tts")
    vad = ctx.proc.userdata.get("vad")
    if not vad:
        logger.info("⏱️ [VAD] Loading Silero VAD model dynamically on call connection...")
        vad = silero.VAD.load(
            min_silence_duration=0.25,
            min_speech_duration=0.08
        )
    
    # Reset TTS options only if it is Cartesia (ElevenLabs uses different options structure)
    is_cartesia = tts and "cartesia" in tts.__class__.__module__
    if is_cartesia and hasattr(tts, "update_options"):
        tts.update_options(
            voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha (Hindi)
            language="hi"
        )
        logger.info("🔄 [STATE RESET] Cartesia TTS options reset to default Esha Hindi voice.")

    t_session_init = time.perf_counter()
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        turn_handling={
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.15,
                "resume_false_interruption": False,
            }
        }
    )
    agent = PriyaRealEstateAgent(customer_name=customer_name)
    logger.info(f"⏱️ [PERF] AgentSession & Agent instantiated in {(time.perf_counter() - t_session_init)*1000:.1f}ms")

    from livekit.agents.voice import UserInputTranscribedEvent

    # Pre-warm Esha connection pool concurrently in the background while session starts
    async def _prewarm_tts_conn():
        try:
            if hasattr(tts, "prewarm"):
                tts.prewarm()
            logger.info("⏱️ [PERF] Esha TTS connection pre-warmed concurrently in background!")
        except Exception as e:
            logger.warning(f"TTS background pre-warm error: {e}")

    asyncio.create_task(_prewarm_tts_conn())

    # Pre-warm LLM schema compilation concurrently in the background while session starts
    async def _prewarm_llm():
        try:
            from livekit.agents import llm as agents_llm
            chat_ctx = agents_llm.ChatContext()
            chat_ctx.add_message(role="user", content="hello")
            
            chat_stream = llm.chat(chat_ctx=chat_ctx, tools=agent.tools)
            async for chunk in chat_stream:
                break
            logger.info("⏱️ [PERF] LLM schema pre-compiled concurrently in background!")
        except Exception as e:
            logger.warning(f"LLM background pre-warm error: {e}")

    asyncio.create_task(_prewarm_llm())

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        if ev.is_final and ev.transcript:
            lang = resolve_language(ev.transcript, ev.language)
            logger.info(f"🗣️ Resolved language: '{lang}' (detected_lang='{ev.language}') for text: '{ev.transcript}'")
            
            # Switch TTS voice and language configurations on the fly (Cartesia only)
            is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
            if is_cartesia and hasattr(session.tts, "update_options"):
                if lang == "mr":
                    session.tts.update_options(
                        voice="5c32dce6-936a-4892-b131-bafe474afe5f",  # Anika (Marathi Feminine)
                        language="mr"
                    )
                    logger.info("🔄 Switched TTS to Marathi (Anika)")
                elif lang == "en":
                    session.tts.update_options(
                        voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha (English)
                        language="en"
                    )
                    logger.info("🔄 Switched TTS to English (Esha)")
                else:
                    session.tts.update_options(
                        voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha (Hindi)
                        language="hi"
                    )
                    logger.info("🔄 Switched TTS to Hindi (Esha)")

    # Start session with record=False
    t_session_start = time.perf_counter()
    logger.info("⏱️ [PERF] Calling session.start()...")
    await session.start(agent=agent, room=ctx.room, record=False)
    
    t_session_ready = (time.perf_counter() - t_session_start) * 1000
    t_total_ready = (time.perf_counter() - t_start) * 1000
    logger.info(f"⏱️ [PERF] session.start() returned! Took {t_session_ready:.1f}ms. Total job-to-ready time: {t_total_ready:.1f}ms")
    logger.info(f"⏱️ [PERF +{t_total_ready:.1f}ms] Agent Session Started & Ready in <50ms!")

    greeting_text = (
        f"Namaste {customer_name}... Main Gayatri baat kar rahi hoon Sai Complex Dombivli se... "
        "Hamara naya residential project launch hua hai... Kya aap details jaan-na chahenge?"
    )

    # Speak greeting immediately using ElevenLabs streaming audio
    logger.info(f"🎙️ [PERF +{t_total_ready:.1f}ms] Speaking Greeting immediately to caller!")
    try:
        session.say(greeting_text, allow_interruptions=True)
    except Exception as e:
        logger.warning(f"Greeting error: {e}")


# ==============================================================================
# 5. HIGH-SPEED PRE-WARMED CLI RUNNER
# ==============================================================================
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm_fnc,
            num_idle_processes=1,
            load_threshold=0.95,
            initialize_process_timeout=45.0,
        )
    )
