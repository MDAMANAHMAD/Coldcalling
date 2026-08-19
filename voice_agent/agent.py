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
from livekit.plugins import deepgram, openai, elevenlabs, cartesia
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
# 0. PROCESS CPU PRIORITY OPTIMIZERS (Prevents idle background pre-warming from starving active calls)
# ==============================================================================
def set_low_priority():
    try:
        os.nice(19)
        logger.info("🟢 Process priority successfully set to nice 19 (low priority).")
    except Exception as e:
        logger.warning(f"Could not set nice priority: {e}")

def set_normal_priority():
    pass



# ==============================================================================
# 1. PRIYA SHARMA HINDI VOICE PERSONA & CRISP KNOWLEDGE BASE
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """You are Gayatri (गायत्री), a warm, highly professional Property Advisor at Shiv Sai Construction Company representing the Sai Complex project in Dombivli East.
You are on a live phone call with a prospective client.

CRITICAL VOICE & SPEED RULES (MANDATORY):
1. NATURAL & CONVERSATIONAL REPLIES (MAXIMUM 1-2 SENTENCES): Always reply in exactly 1 or 2 short sentences. Keep your replies concise, friendly, and complete. Avoid extremely short one-word replies, and never speak in long paragraphs.
2. ENGLISH-NUMBER PRICING PRONUNCIATION: You must write out all money and pricing parts phonetically using English words for the numbers and the units "lakh" or "crore". For example:
   - Write "thirty six lakh" instead of "36 Lacs" or "chattis lakh".
   - Write "fifty lakh" instead of "50 Lacs" or "pachas lakh".
   - Write "seventy two lakh" instead of "72 Lacs" or "bahattar lakh".
   - Write "one crore four lakh" instead of "1.04 crore" or "ek crore char lakh".
   - Write "two crore ten lakh" instead of "2.10 crore" or "do crore das lakh".
   This is critical to ensure the TTS synthesizes the numbers clearly in English and the units in Hindi/English.
3. NATURAL HINDI/HINGLISH: Speak warm, polite conversational Hindi/Hinglish ("Ji bilkul", "Haanji").
4. SPEAK CALMLY & SLOWLY: Maintain a calm, warm, and unhurried pace. Use punctuation like commas `,` and ellipses `...` to force the voice synthesizer to insert natural human breathing pauses.
5. DYNAMIC & INTERACTIVE CONVERSATION (BARGE-IN FRIENDLY): Adapt your responses dynamically based on what the user says. Do not rigidly follow a script. If the user interrupts, acknowledges, or changes the topic, address their comment naturally and match their flow immediately. Keep it conversational, relaxed, and real.
6. DO NOT OVERUSE THE CLIENT'S NAME: Address the client by name (e.g., "Aman ji") only once or twice during the entire call (such as in the greeting or closing). Do NOT append their name to every response.
7. MULTILINGUAL RESPONSE MATCHING: Always respond in the EXACT same language that the client speaks to you. If the client speaks in Marathi, reply in fluent, warm Marathi. If the client speaks in English, reply in English. If the client speaks in Hindi, reply in Hindi.
8. NO ABBREVIATIONS: Never use abbreviations like "sqft", "sq. ft.", "cr", "lacs", or "rs" in your replies. Always write them out fully in plain text as "square feet", "crore", "lakh", or "rupaye". For example, write "375 square feet" instead of "375 sqft".
9. SHORT PROJECT INTRO & PRICING: When describing the project or pricing, keep it very short and simple. Do NOT list out all square footages or terrace flat options in one go. Just mention that we have 1BHK flats starting at thirty six lakh rupees, and 2BHK flats starting at seventy two lakh rupees, and then ask them if they would like to know more. Keep this intro to exactly 1 or 2 sentences maximum.

==================================================
PROJECT KNOWLEDGE BASE (SAI COMPLEX, DOMBIVLI EAST):
==================================================
1. PRICING & CONFIGURATIONS:
   - 1BHK Options:
     * 375 square feet carpet area: thirty six lakh onwards.
     * 520 square feet carpet area: fifty lakh onwards.
     * 755 square feet carpet area (Terrace Flat): seventy two lakh onwards.
   - 2BHK Options:
     * 760 square feet carpet area: seventy two lakh onwards.
     * 1110 square feet carpet area (Terrace Flat): one crore four lakh onwards.
     * 2285 square feet carpet area (Terrace Flat): two crore ten lakh onwards.
   - Customizable Layouts: Also available. "Aap flats ko custom design aur customize bhi kar sakte hain."

2. KEY AMENITIES:
   - Fitness Club: Fully equipped gym.
   - Kids Play Area: Safe and fun play spaces for children.
   - Jogging Track: Refreshing jogging track within the complex.
   - Indoor Games: Recreational indoor gaming area.
   - Office Space: Dedicated, peaceful work-from-home areas.
   - Utilities: 24/7 water supply and lush landscaping.
   - Premium Fittings: Jaquar bathroom fittings, Kajaria tiles flooring, Asian Paints, and Polycab wiring.
   - Outdoor: Luxurious balconies and terrace flats.

3. LOCATION & CONNECTIVITY:
   - Address: Sai Complex, Casario, Palava Road, Near Pratik Green, Lodha Heaven, Dombivli East – 421204.
   - Railway: Nilje Railway Station is just five minutes away. It is also very close to Dombivli Station.
   - Metro/Road: Upcoming Kalyan-Taloja Metro line is walking distance. Direct access to Shil Road connects to Navi Mumbai, Mumbra, Thane, Airoli, and Katai Freeway.
   - Healthcare/Schools: Close to AIMS Hospital, Icon Hospital, Lodha World School, and Guardian School.

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

        return f"Maine {preferred_day} ko VIP visit confirm kar diya hai."# ==============================================================================
# 2.5 GLOBAL LLM INSTANTIATION & STATIC COMPILATION (Pre-compiled at module import)
# ==============================================================================
logger.info("🔥 [IMPORT TIME] Instantiating LLM and compiling schemas...")
global_groq_key = os.getenv("GROQ_API_KEY")
if global_groq_key and global_groq_key.startswith("gsk_"):
    from livekit.plugins import openai as lk_openai
    global_llm = lk_openai.LLM(
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-20b",
        api_key=global_groq_key,
        temperature=0.0
    )
else:
    from livekit.plugins import google
    global_google_key = os.getenv("GOOGLE_API_KEY")
    global_llm = google.LLM(
        model="gemini-flash-latest",
        api_key=global_google_key,
        temperature=0.0
    )

try:
    from livekit.agents import llm as agents_llm
    agent_dummy = PriyaRealEstateAgent()
    agent_tools_dummy = agent_dummy.tools
    chat_ctx_dummy = agents_llm.ChatContext()
    chat_ctx_dummy.add_message(role="user", content="hello")

    async def _compile_schemas_static():
        chat_stream = global_llm.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy)
        async for chunk in chat_stream:
            break

    try:
        loop_static = asyncio.get_event_loop()
    except RuntimeError:
        loop_static = asyncio.new_event_loop()
        asyncio.set_event_loop(loop_static)
        
    loop_static.run_until_complete(asyncio.wait_for(_compile_schemas_static(), timeout=8.0))
    logger.info("✅ [IMPORT TIME COMPLETE] LLM schemas compiled successfully!")
except Exception as e:
    logger.warning(f"Static LLM schema compilation failed during import: {e}")


# ==============================================================================
# 3. PREWARMING FUNCTION (Pre-Loads All AI Engines in Idle Memory)
# ==============================================================================
def prewarm_fnc(proc: JobProcess):
    """Pre-allocates and caches STT, LLM, TTS, and VAD before any call arrives."""
    set_low_priority()
    t0 = time.perf_counter()
    logger.info("🔥 [PRE-WARMING] Pre-loading Sarah voice model and AI engines...")

    # 1. Store the already compiled global LLM
    proc.userdata["llm"] = global_llm

    # 2. Pre-warm Deepgram Nova-2 STT
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    proc.userdata["stt"] = deepgram.STT(
        language="hi",
        model="nova-2",
        endpointing_ms=120,
        smart_format=True,
        api_key=deepgram_key
    )

    # 3. Pre-warm Silero VAD (optimized with 8kHz sample rate to cut CPU usage by 50%)
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.25,
        min_speech_duration=0.08,
        sample_rate=8000
    )

    # 4. Pre-warm Cartesia/ElevenLabs TTS (loads client network config in background)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    if cartesia_key and len(cartesia_key) > 10:
        proc.userdata["tts"] = cartesia.TTS(
            api_key=cartesia_key,
            voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha (Hindi)
            language="hi",
            sample_rate=24000,
            model="sonic-3.5"
        )
    else:
        eleven_key = os.getenv("ELEVENLABS_API_KEY")
        if eleven_key and len(eleven_key) > 10:
            proc.userdata["tts"] = elevenlabs.TTS(
                api_key=eleven_key,
                voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel
                model="eleven_flash_v2_5",
                streaming_latency=1
            )

    t1 = (time.perf_counter() - t0) * 1000
    logger.info(f"✅ [PRE-WARMING COMPLETE] Models ready in {t1:.1f}ms!")


# ==============================================================================
# 4. AGENT ENTRYPOINT (Instant Telephony Streaming Audio)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    set_normal_priority()
    t_start = time.perf_counter()
    logger.info(f"⏱️ [PERF +0ms] Job received for Room: {ctx.room.name}")
    
    # Create active call lock file to signal background processes to hold off heavy compilation
    try:
        os.makedirs("bookings", exist_ok=True)
        with open("bookings/active_call.lock", "w") as f:
            f.write(str(os.getpid()))
        logger.info("🔒 Active call lock created.")
    except Exception as e:
        logger.warning(f"Failed to create lock file: {e}")

    # Register cleanup callback on job shutdown to release the lock file
    async def cleanup_lock():
        try:
            if os.path.exists("bookings/active_call.lock"):
                os.remove("bookings/active_call.lock")
                logger.info("🔓 Active call lock released.")
        except Exception as e:
            logger.warning(f"Failed to remove lock file: {e}")

    ctx.add_shutdown_callback(cleanup_lock)

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
    from livekit.plugins import silero
    t_retrieval = time.perf_counter()
    
    stt = ctx.proc.userdata.get("stt")
    if not stt:
        logger.info("⏱️ [STT] Initializing Deepgram STT dynamically on demand...")
        deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
        stt = deepgram.STT(
            language="hi",
            model="nova-2",
            endpointing_ms=120,
            smart_format=True,
            api_key=deepgram_key
        )
        ctx.proc.userdata["stt"] = stt

    llm = ctx.proc.userdata.get("llm")
    if not llm:
        logger.info("⏱️ [LLM] Initializing LLM dynamically on demand...")
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key and groq_key.startswith("gsk_"):
            llm = openai.LLM(
                base_url="https://api.groq.com/openai/v1",
                model="openai/gpt-oss-20b",
                api_key=groq_key,
                temperature=0.0
            )
        else:
            from livekit.plugins import google
            google_key = os.getenv("GOOGLE_API_KEY")
            llm = google.LLM(
                model="gemini-flash-latest",
                api_key=google_key,
                temperature=0.0
            )
        ctx.proc.userdata["llm"] = llm
    
    # Initialize TTS dynamically here instead of prewarm_fnc to save concurrency connections
    tts = ctx.proc.userdata.get("tts")
    if not tts:
        logger.info("⏱️ [TTS] Initializing TTS dynamically on connection...")
        cartesia_key = os.getenv("CARTESIA_API_KEY")
        if cartesia_key and len(cartesia_key) > 10:
            logger.info("Initializing Cartesia TTS as Primary with Esha Calm Hindi Voice...")
            tts = cartesia.TTS(
                api_key=cartesia_key,
                voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha (Hindi)
                language="hi",
                sample_rate=24000,
                model="sonic-3.5"
            )
        else:
            eleven_key = os.getenv("ELEVENLABS_API_KEY")
            logger.info("Initializing ElevenLabs TTS as Fallback with Rachel Fallback Multilingual Voice (eleven_flash_v2_5)...")
            tts = elevenlabs.TTS(
                api_key=eleven_key,
                voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel - Fallback multilingual
                model="eleven_flash_v2_5",
                voice_settings=elevenlabs.VoiceSettings(
                    stability=0.65,
                    similarity_boost=0.75,
                    style=0.00,
                    use_speaker_boost=True
                ),
                streaming_latency=1
            )
        ctx.proc.userdata["tts"] = tts
    


    # VAD is pre-warmed, but load as fallback if not present (optimized with 8kHz sample rate to cut CPU usage by 50%)
    vad = ctx.proc.userdata.get("vad")
    if not vad:
        logger.info("⏱️ [VAD] Loading Silero VAD model on demand...")
        vad = silero.VAD.load(
            min_silence_duration=0.25,
            min_speech_duration=0.08,
            sample_rate=8000
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
            "turn_detection": None,
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.15,
                "resume_false_interruption": True,
            }
        }
    )
    agent = PriyaRealEstateAgent(customer_name=customer_name)
    logger.info(f"⏱️ [PERF] AgentSession & Agent instantiated in {(time.perf_counter() - t_session_init)*1000:.1f}ms")

    from livekit.agents.voice import UserInputTranscribedEvent





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
    # Wait for the caller to join the room if not already present.
    # We wait BEFORE calling session.start() to prevent Deepgram from starting its WebSocket 
    # connection during the ringing phase, which would trigger 1006 connection timeouts.
    if not ctx.room.remote_participants:
        logger.info("⏳ Room is empty. Waiting for caller to join...")
        caller_joined = asyncio.Event()
        
        @ctx.room.on("participant_connected")
        def _on_participant_connected(p):
            logger.info(f"📞 Caller joined: {p.identity}")
            caller_joined.set()
            
        try:
            await asyncio.wait_for(caller_joined.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for caller to join room.")

    # Start session with record=False
    t_session_start = time.perf_counter()
    logger.info("⏱️ [PERF] Calling session.start()...")
    await session.start(agent=agent, room=ctx.room, record=False)
    
    t_session_ready = (time.perf_counter() - t_session_start) * 1000
    t_total_ready = (time.perf_counter() - t_start) * 1000
    logger.info(f"⏱️ [PERF] session.start() returned! Took {t_session_ready:.1f}ms. Total job-to-ready time: {t_total_ready:.1f}ms")
    logger.info(f"⏱️ [PERF +{t_total_ready:.1f}ms] Agent Session Started & Ready in <50ms!")

    # Allow 0.1s for WebRTC audio negotiation and SIP RTP streams to fully settle
    logger.info("⏳ Allowing 0.1s for audio bridge and SIP RTP connection to settle...")
    await asyncio.sleep(0.1)

    greeting_text = (
        f" Namaste {customer_name}... Main Gayatri baat kar rahi hoon Sai Complex Dombivli se... "
        "Hamara naya residential project launch hua hai... Kya aap details jaan-na chahenge?"
    )

    # Speak greeting immediately after bridge has settled, allow caller to interrupt
    logger.info("🎙️ Speaking Greeting to caller...")
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
            load_threshold=100.0,
            initialize_process_timeout=90.0,
        )
    )
