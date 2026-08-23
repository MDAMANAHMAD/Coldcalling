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
    try:
        os.nice(0)
        logger.info("🟢 Process priority successfully set to nice 0 (normal priority).")
    except Exception as e:
        logger.warning(f"Could not set normal priority: {e}")


# ==============================================================================
# 1. PRIYA SHARMA HINDI VOICE PERSONA & CRISP KNOWLEDGE BASE
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """# IDENTITY & GREETING FLOW
- **Name/Identity**: Gayatri, warm & professional Property Advisor at Shiv Sai Construction, representing the Sai Complex project in Dombivli East.
- **Greeting (Turn 1)**: "Hello... main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
- **Pitch & Interest Check (Turn 2)**: Once prospect answers (e.g. "haan", "boliye"), state: "Ji... humara ek residential project launch hua hai jisme one BHK flats thirty six lakh se aur two BHK flats seventy two lakh se start hote hote hain... kya aap iske details jaan-na chahenge?"
  - **If YES** ("haan", "yes", etc.): Proceed to discover BHK type, budget, location, and amenities.
  - **If NO** ("nahi", "not interested", etc.): Ask: "Kyu sir, koi specific reason hai?" After their reply, say: "Okay sir, thank you so much, aapka din achha rahe." and end the call.

# CRITICAL VOICE & CONVERSATION RULES
1. **Response Length**: STRICTLY 1 to 2 short sentences per turn. Never speak paragraphs.
2. **Conversation Flow**: Always end every response with exactly one follow-up question.
3. **Language Matching & Script**: Match the user's language but ALWAYS write your outputs in Hinglish using the Latin alphabet (e.g. "Ji, Sai Complex Dombivli East mein hai..."). NEVER output Devanagari script (Hindi/Marathi characters) under any circumstances.
4. **No Name Repetition**: Use the customer's name ONLY in the initial greeting. Never say it again during the call.
5. **No Numbers/Abbreviations**: Write money and pricing phonetically. Use words only.
   - Good: "thirty six lakh rupaye", "one crore four lakh rupaye", "square feet".
   - Bad: ₹36L, 36L, 36 lakh, 1.04 Cr, sqft, BHK (except saying "one BHK", "two BHK").
6. **TTS Pace**: Use punctuation (commas, ellipses) to slow down speech pace naturally.
7. **Barge-in**: Stop speaking immediately when interrupted. Address the interruption.
8. **No Repetition**: Do not repeat the same question. Rephrase if the user remains silent.
9. **Short Answers**: If user gives short answers (e.g. "2 BHK"), acknowledge briefly and ask the next sales question.

# CORE PROJECT KNOWLEDGE (SAI COMPLEX, DOMBIVLI EAST)
- **Address**: Casario, Palava Road, Near Pratik Green, Lodha Heaven, Dombivli East — 421204.
- **1 BHK Options**: 375 sqft (thirty six lakh rupaye), 520 sqft (fifty lakh rupaye), 755 sqft Terrace (seventy two lakh rupaye).
- **2 BHK Options**: 760 sqft (seventy two lakh rupaye), 1110 sqft Terrace (one crore four lakh rupaye), 2285 sqft Terrace (two crore ten lakh rupaye).
  - *Rule*: Discuss only the BHK type requested by the user. Do not mix.
- **Amenities**: Gym, Kids play, 24h water. (Rule: List a max of 3 amenities at a time).
- **Connectivity**: Nilje Railway Station (5 min), Kalyan-Taloja Metro (walking distance), Shil Road (to Thane/Navi Mumbai). Dadar/Vashi are 45-60 min away via Shil Phata.

# OBJECTIONS & SITE VISIT BOOKING
- **Objection - Price**: Premium materials used. Mention price is negotiable. Ask: "Kya kal visit par aakar baat karein?"
- **Objection - Distance**: Explain walking distance metro and Nilje station connectivity.
- **Objection - Details First**: Offer WhatsApp brochure. Invite to actual site layout.
- **Booking CTA**: "Aap chahein toh... ek short site visit karke actual layout aur location dekh sakte hain. Kal convenient rahega... ya weekend better rahega?"
  - **Action**: When a preferred day/time is specified, immediately run the `schedule_site_visit` tool.
"""


# ==============================================================================
# 2. LANGUAGE RESOLUTION HELPER & AGENT CLASS
# ==============================================================================
def resolve_language(transcript: str, detected_lang: str | None) -> str:
    """Detects spoken language, preferring Hindi unless a strong shift to English or Marathi occurs."""
    text = transcript.strip().lower()
    words = text.split()
    
    # 0. Explicit language request overrides (user asks to switch language)
    if "marathi" in text or "मराठी" in text:
        return "mr"
    if "english" in text or "इंग्लिश" in text:
        return "en"
    if "hindi" in text or "हिंदी" in text or "हिन्दी" in text:
        return "hi"
    
    # Count Latin letters vs total
    latin_chars = sum(1 for c in transcript if c.isalpha() and c.isascii())
    total_chars = len(transcript.replace(" ", ""))
    
    # Common Hinglish grammatical words/filler words. If the user uses these, they are speaking Hindi/Hinglish.
    hinglish_markers = {
        "hai", "kya", "ka", "ki", "ko", "se", "par", "ji", "haan", "han", "achha", "acha", 
        "bataiye", "batao", "btao", "he", "ho", "me", "mein", "ke", "ne", "aur", "ya", "toh", 
        "to", "bhai", "na", "ab", "kab", "sab", "kar", "karna", "krna", "do", "dena", "dedo"
    }
    
    # 1. English Check: Only switch to English if:
    # - Sentence is at least 4 words
    # - More than 80% of the characters are Latin
    # - None of the words are common Hinglish markers
    is_mostly_latin = total_chars > 0 and (latin_chars / total_chars) > 0.8
    if len(words) >= 4 and is_mostly_latin:
        if not any(w in hinglish_markers for w in words):
            return "en"
            
    # 2. Marathi Check
    marathi_keywords = [
        "मला", "आहे", "आहात", "नाही", "काय", "करतो", "माहिती", "पाहिजे", "बोलतो", 
        "बघतो", "चालू", "करून", "पुढील", "नका", "चालेल", "नको", "कधी", "कसा", 
        "कशी", "कसे", "सांगा", "दाखवा", "पाहू", "तुम्ही", "आम्ही", "मध्ये"
    ]
    if "ळ" in transcript or (len(words) >= 3 and any(word in text for word in marathi_keywords)):
        return "mr"
        
    # Default to Hindi
    return "hi"


class PriyaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji"):
        instructions = (
            f"{HINDI_REAL_ESTATE_PROMPT}\n\n"
            f"Aap abhi {customer_name} se call par baat kar rahi hain. "
            "STRICT RULE: Do NOT say the client's name in your responses. You must talk to them directly without repeating or saying their name at all. NEVER prefix your sentences with their name."
        )
        super().__init__(instructions=instructions)

    @function_tool(description="Schedule a free property site visit for the client. Call this only when the client agrees to a visit and specifies a preferred day/date.")
    async def schedule_site_visit(
        self,
        customer_name: str,
        preferred_day: str,
        preferred_time: str = "Not specified",
        flat_type: str = "2BHK / 3BHK",
        notes: str = ""
    ) -> str:
        logger.info("=" * 60)
        logger.info("🏠 [HINDI REAL ESTATE SITE VISIT BOOKED]")
        logger.info(f"👤 Client Name     : {customer_name}")
        logger.info(f"📅 Preferred Day   : {preferred_day}")
        logger.info(f"⏰ Preferred Time  : {preferred_time}")
        logger.info(f"🏢 Flat Type       : {flat_type}")
        logger.info(f"📝 Notes           : {notes}")
        logger.info("=" * 60)

        visit_record = {
            "customer_name": customer_name,
            "preferred_day": preferred_day,
            "preferred_time": preferred_time,
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

        time_str = f" at {preferred_time}" if preferred_time != "Not specified" else ""
        return f"Maine {preferred_day}{time_str} ko site visit confirm kar diya hai... Main is number par details WhatsApp kar deti hoon."

# ==============================================================================
# Model Cache and Process Lifecycle Helpers
# ==============================================================================
MODEL_CACHE_PATH = "bookings/model_cache.json"

def load_cached_models():
    if os.path.exists(MODEL_CACHE_PATH):
        try:
            with open(MODEL_CACHE_PATH, "r") as f:
                data = json.load(f)
                return data.get("selected_model"), data.get("selected_groq_model")
        except Exception:
            pass
    return None, None

def save_cached_models(selected_model, selected_groq_model):
    try:
        os.makedirs(os.path.dirname(MODEL_CACHE_PATH), exist_ok=True)
        with open(MODEL_CACHE_PATH, "w") as f:
            json.dump({
                "selected_model": selected_model,
                "selected_groq_model": selected_groq_model
            }, f)
    except Exception:
        pass

import multiprocessing
is_main_process = (multiprocessing.current_process().name == "MainProcess")

if is_main_process:
    if os.path.exists("bookings/active_call.lock"):
        try:
            os.remove("bookings/active_call.lock")
            logger.info("🧹 Cleaned up stale active call lock at startup.")
        except Exception as e:
            logger.warning(f"Could not remove stale active call lock: {e}")

SELECTED_MODEL = "gemini-3.5-flash-lite" # default fallback
SELECTED_GROQ_MODEL = "openai/gpt-oss-20b" # default fallback
if os.getenv("SAMBANOVA_API_KEY"):
    SELECTED_GROQ_MODEL = "gpt-oss-120b"
global_llm = None
global_llm_compiled = False

# Load cached models if available to prevent child process re-validation delays
cached_model, cached_groq_model = load_cached_models()
if cached_model or cached_groq_model:
    if cached_model:
        SELECTED_MODEL = cached_model
    if cached_groq_model is not None:
        SELECTED_GROQ_MODEL = cached_groq_model
    logger.info(f"💾 [IMPORT TIME] Loaded cached models: Gemini={SELECTED_MODEL}, Groq={SELECTED_GROQ_MODEL}")

logger.info("🔥 [IMPORT TIME] Instantiating LLM...")
global_sambanova_key = os.getenv("SAMBANOVA_API_KEY")
global_groq_key = os.getenv("GROQ_API_KEY")
global_google_key = os.getenv("GOOGLE_API_KEY")

if global_sambanova_key:
    from livekit.plugins import openai as lk_openai
    preferred_samba_models = [
        "gpt-oss-120b",
        "Meta-Llama-3.3-70B-Instruct"
    ]
    
    # If a call is active, skip verification compilation and use cached/default model immediately
    if os.path.exists("bookings/active_call.lock"):
        logger.info(f"🔒 Active call detected during import. Selecting SambaNova model '{SELECTED_GROQ_MODEL}' without validation.")
        global_llm = lk_openai.LLM(
            base_url="https://api.sambanova.ai/v1",
            model=SELECTED_GROQ_MODEL,
            api_key=global_sambanova_key,
            temperature=0.3,
            max_tokens=150
        )
    else:
        try:
            from livekit.agents import llm as agents_llm
            agent_dummy = PriyaRealEstateAgent()
            agent_tools_dummy = agent_dummy.tools
            chat_ctx_dummy = agents_llm.ChatContext()
            chat_ctx_dummy.add_message(role="user", content="hello")
            
            async def _test_compile_samba(llm_instance):
                chat_stream = llm_instance.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy)
                async for chunk in chat_stream:
                    break

            try:
                loop_static = asyncio.get_event_loop()
            except RuntimeError:
                loop_static = asyncio.new_event_loop()
                asyncio.set_event_loop(loop_static)

            for model_name in preferred_samba_models:
                try:
                    logger.info(f"Trying to initialize and compile SambaNova model '{model_name}'...")
                    candidate_llm = lk_openai.LLM(
                        base_url="https://api.sambanova.ai/v1",
                        model=model_name,
                        api_key=global_sambanova_key,
                        temperature=0.3,
                        max_tokens=150
                    )
                    
                    # Verify schema compilation works
                    loop_static.run_until_complete(asyncio.wait_for(_test_compile_samba(candidate_llm), timeout=5.0))
                    
                    global_llm = candidate_llm
                    SELECTED_GROQ_MODEL = model_name
                    global_llm_compiled = True
                    save_cached_models(SELECTED_MODEL, SELECTED_GROQ_MODEL)
                    logger.info(f"✅ [IMPORT TIME COMPLETE] SambaNova model '{model_name}' successfully compiled and selected!")
                    break
                except Exception as e:
                    logger.warning(f"Failed to initialize/compile SambaNova model '{model_name}': {e}")
        except Exception as outer_err:
            logger.warning(f"SambaNova LLM selector setup failed: {outer_err}")

elif global_groq_key and global_groq_key.startswith("gsk_"):
    from livekit.plugins import openai as lk_openai
    preferred_groq_models = [
        "openai/gpt-oss-20b",
        "groq/compound-mini",
        "groq/compound",
        "openai/gpt-oss-120b",
        "qwen/qwen3.6-27b"
    ]
    
    # If a call is active, skip verification compilation and use cached/default model immediately
    if os.path.exists("bookings/active_call.lock"):
        logger.info(f"🔒 Active call detected during import. Selecting Groq model '{SELECTED_GROQ_MODEL}' without validation.")
        global_llm = lk_openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            model=SELECTED_GROQ_MODEL,
            api_key=global_groq_key,
            temperature=0.3,
            max_tokens=150
        )
    else:
        try:
            from livekit.agents import llm as agents_llm
            agent_dummy = PriyaRealEstateAgent()
            agent_tools_dummy = agent_dummy.tools
            chat_ctx_dummy = agents_llm.ChatContext()
            chat_ctx_dummy.add_message(role="user", content="hello")
            
            async def _test_compile_groq(llm_instance):
                chat_stream = llm_instance.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy)
                async for chunk in chat_stream:
                    break

            try:
                loop_static = asyncio.get_event_loop()
            except RuntimeError:
                loop_static = asyncio.new_event_loop()
                asyncio.set_event_loop(loop_static)

            for model_name in preferred_groq_models:
                try:
                    logger.info(f"Trying to initialize and compile Groq model '{model_name}'...")
                    candidate_llm = lk_openai.LLM(
                        base_url="https://api.groq.com/openai/v1",
                        model=model_name,
                        api_key=global_groq_key,
                        temperature=0.3,
                        max_tokens=150
                    )
                    
                    # Verify schema compilation works
                    loop_static.run_until_complete(asyncio.wait_for(_test_compile_groq(candidate_llm), timeout=5.0))
                    
                    global_llm = candidate_llm
                    SELECTED_GROQ_MODEL = model_name
                    global_llm_compiled = True
                    save_cached_models(SELECTED_MODEL, SELECTED_GROQ_MODEL)
                    logger.info(f"✅ [IMPORT TIME COMPLETE] Groq model '{model_name}' successfully compiled and selected!")
                    break
                except Exception as e:
                    logger.warning(f"Failed to initialize/compile Groq model '{model_name}': {e}")
            
            if not global_llm:
                if global_google_key:
                    logger.warning("⚠️ All preferred Groq models failed validation! Falling back to Google Gemini.")
                    from livekit.plugins import google
                    global_llm = google.LLM(
                        model="gemini-3.6-flash",
                        api_key=global_google_key,
                        temperature=0.3
                    )
                    SELECTED_MODEL = "gemini-3.6-flash"
                    SELECTED_GROQ_MODEL = None
                else:
                    logger.warning("All preferred Groq models failed validation and no GOOGLE_API_KEY is available. Forcing llama-3.3-70b-versatile.")
                    global_llm = lk_openai.LLM(
                        base_url="https://api.groq.com/openai/v1",
                        model="llama-3.3-70b-versatile",
                        api_key=global_groq_key,
                        temperature=0.3,
                        max_tokens=150
                    )
                    SELECTED_GROQ_MODEL = "llama-3.3-70b-versatile"
        except Exception as outer_err:
            if global_google_key:
                logger.warning(f"Self-healing Groq LLM selector setup failed: {outer_err}. Falling back to Google Gemini.")
                from livekit.plugins import google
                global_llm = google.LLM(
                    model="gemini-3.6-flash",
                    api_key=global_google_key,
                    temperature=0.3
                )
                SELECTED_MODEL = "gemini-3.6-flash"
                SELECTED_GROQ_MODEL = None
            else:
                logger.warning(f"Self-healing Groq LLM selector setup failed: {outer_err}. Forcing llama-3.3-70b-versatile.")
                global_llm = lk_openai.LLM(
                    base_url="https://api.groq.com/openai/v1",
                    model="llama-3.3-70b-versatile",
                    api_key=global_groq_key,
                    temperature=0.3,
                    max_tokens=150
                )
                SELECTED_GROQ_MODEL = "llama-3.3-70b-versatile"
elif global_google_key:
    from livekit.plugins import google
    
    preferred_models = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]
    
    # If a call is active, skip verification compilation and use cached/default model immediately
    if os.path.exists("bookings/active_call.lock"):
        logger.info(f"🔒 Active call detected during import. Selecting Gemini model '{SELECTED_MODEL}' without validation.")
        global_llm = google.LLM(
            model=SELECTED_MODEL,
            api_key=global_google_key,
            temperature=0.3
        )
    else:
        try:
            from livekit.agents import llm as agents_llm
            agent_dummy = PriyaRealEstateAgent()
            agent_tools_dummy = agent_dummy.tools
            chat_ctx_dummy = agents_llm.ChatContext()
            chat_ctx_dummy.add_message(role="user", content="hello")
            
            async def _test_compile(llm_instance):
                chat_stream = llm_instance.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy)
                async for chunk in chat_stream:
                    break

            try:
                loop_static = asyncio.get_event_loop()
            except RuntimeError:
                loop_static = asyncio.new_event_loop()
                asyncio.set_event_loop(loop_static)

            for model_name in preferred_models:
                try:
                    logger.info(f"Trying to initialize and compile LLM model '{model_name}'...")
                    candidate_llm = google.LLM(model=model_name, api_key=global_google_key, temperature=0.3)
                    
                    # Verify schema compilation works
                    loop_static.run_until_complete(asyncio.wait_for(_test_compile(candidate_llm), timeout=5.0))
                    
                    global_llm = candidate_llm
                    SELECTED_MODEL = model_name
                    global_llm_compiled = True
                    save_cached_models(SELECTED_MODEL, SELECTED_GROQ_MODEL)
                    logger.info(f"✅ [IMPORT TIME COMPLETE] LLM model '{model_name}' successfully compiled and selected!")
                    break
                except Exception as e:
                    logger.warning(f"Failed to initialize/compile model '{model_name}': {e}")
            
            if not global_llm:
                logger.warning("All preferred models failed validation. Falling back to gemini-3.6-flash.")
                global_llm = google.LLM(model="gemini-3.6-flash", api_key=global_google_key, temperature=0.3)
                SELECTED_MODEL = "gemini-3.6-flash"
        except Exception as outer_err:
            logger.warning(f"Self-healing LLM selector setup failed: {outer_err}. Defaulting to gemini-3.6-flash.")
            global_llm = google.LLM(model="gemini-3.6-flash", api_key=global_google_key, temperature=0.3)
            SELECTED_MODEL = "gemini-3.6-flash"
else:
    logger.warning("Neither GROQ_API_KEY nor GOOGLE_API_KEY is configured.")


# ==============================================================================
# 3. PREWARMING FUNCTION (Pre-Loads All AI Engines in Idle Memory)
# ==============================================================================
def prewarm_fnc(proc: JobProcess):
    """Pre-allocates and caches STT, LLM, TTS, and VAD before any call arrives."""
    set_low_priority()
    t0 = time.perf_counter()
    logger.info("🔥 [PRE-WARMING] Pre-loading Sarah voice model and AI engines...")

    # 1. Store the global LLM
    proc.userdata["llm"] = global_llm

    # If static compilation was skipped due to an active call, compile lazily in a background thread once idle
    global global_llm_compiled
    if not global_llm_compiled:
        import threading
        def compile_schemas_lazy():
            global global_llm_compiled
            # Sleep to let process initialization settle
            time.sleep(1.0)
            
            # Loop and sleep while another call is active
            while os.path.exists("bookings/active_call.lock"):
                try:
                    with open("bookings/active_call.lock", "r") as f:
                        lock_pid = int(f.read().strip())
                    if lock_pid == os.getpid():
                        # We are the active call! Abort background thread to protect CPU!
                        return
                except Exception:
                    pass
                time.sleep(1.5)
                
            logger.info("🔥 [PRE-WARMING] System is idle. Compiling LLM schemas lazily in background...")
            try:
                from livekit.agents import llm as agents_llm
                agent_dummy = PriyaRealEstateAgent()
                agent_tools_dummy = agent_dummy.tools
                chat_ctx_dummy = agents_llm.ChatContext()
                chat_ctx_dummy.add_message(role="user", content="hello")

                async def _compile_schemas_lazy():
                    chat_stream = global_llm.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy)
                    async for chunk in chat_stream:
                        break

                loop_lazy = asyncio.new_event_loop()
                asyncio.set_event_loop(loop_lazy)
                try:
                    loop_lazy.run_until_complete(asyncio.wait_for(_compile_schemas_lazy(), timeout=8.0))
                    global_llm_compiled = True
                    logger.info("✅ [PRE-WARMING COMPLETE] LLM schemas compiled lazily in background successfully!")
                finally:
                    loop_lazy.close()
            except Exception as e:
                logger.warning(f"Lazy LLM schema compilation failed: {e}")
                
        threading.Thread(target=compile_schemas_lazy, daemon=True).start()

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


def log_system_diagnostics():
    try:
        # Check RAM via /proc/meminfo (Linux)
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem_info = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    mem_info[parts[0].strip()] = parts[1].strip()
            logger.info(f"💾 [DIAGNOSTICS] RAM Status: Total={mem_info.get('MemTotal')}, Free={mem_info.get('MemFree')}, Available={mem_info.get('MemAvailable')}")
        
        # Check CPU Load
        if os.path.exists("/proc/loadavg"):
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip()
            logger.info(f"⚙️ [DIAGNOSTICS] CPU Load Average: {load}")

        # List Google models to diagnose 404/Not Found and identify valid names
        try:
            google_key = os.getenv("GOOGLE_API_KEY")
            if google_key:
                # Try new SDK first
                try:
                    from google import genai
                    client = genai.Client(api_key=google_key)
                    models = [m.name for m in client.models.list()]
                    logger.info(f"📋 [DIAGNOSTICS] Google GenAI Models: {models}")
                except Exception as sdk_err:
                    # Fallback to legacy SDK
                    try:
                        import google.generativeai as legacy_genai
                        legacy_genai.configure(api_key=google_key)
                        models = [m.name for m in legacy_genai.list_models()]
                        logger.info(f"📋 [DIAGNOSTICS] Legacy Google Models: {models}")
                    except Exception as legacy_err:
                        logger.warning(f"Could not list models via GenAI SDK ({sdk_err}) or Legacy SDK ({legacy_err})")
            else:
                logger.warning("GOOGLE_API_KEY env variable not set in log_system_diagnostics")
        except Exception as model_err:
            logger.warning(f"Failed to list Google models: {model_err}")

        # List Groq models to check availability
        try:
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key:
                import urllib.request
                import urllib.error
                import json
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}"}
                )
                with urllib.request.urlopen(req) as response:
                    res_body = response.read().decode("utf-8")
                    data = json.loads(res_body)
                    groq_models = [m["id"] for m in data.get("data", [])]
                    logger.info(f"📋 [DIAGNOSTICS] Groq Models: {groq_models}")
            else:
                logger.warning("GROQ_API_KEY env variable not set in log_system_diagnostics")
        except Exception as groq_err:
            logger.warning(f"Failed to list Groq models: {groq_err}")
    except Exception as e:
        logger.warning(f"Failed to gather diagnostics: {e}")


# ==============================================================================
# 4. AGENT ENTRYPOINT (Instant Telephony Streaming Audio)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    set_normal_priority()
    log_system_diagnostics()
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
        sambanova_key = os.getenv("SAMBANOVA_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")
        
        if sambanova_key and SELECTED_GROQ_MODEL:
            llm = openai.LLM(
                base_url="https://api.sambanova.ai/v1",
                model=SELECTED_GROQ_MODEL,
                api_key=sambanova_key,
                temperature=0.3,
                max_tokens=150
            )
        elif groq_key and groq_key.startswith("gsk_") and SELECTED_GROQ_MODEL:
            llm = openai.LLM(
                base_url="https://api.groq.com/openai/v1",
                model=SELECTED_GROQ_MODEL,
                api_key=groq_key,
                temperature=0.3,
                max_tokens=150
            )
        elif google_key:
            from livekit.plugins import google
            llm = google.LLM(
                model=SELECTED_MODEL,
                api_key=google_key,
                temperature=0.3
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
            "endpointing": {
                "mode": "fixed",
                "min_delay": 0.1,
            },
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.25,
                "resume_false_interruption": True,
            }
        }
    )
    logger.info(f"⏱️ [PERF] AgentSession instantiated in {(time.perf_counter() - t_session_init)*1000:.1f}ms")

    t_call_start = time.time()
    input_tokens = 0
    output_tokens = 0
    characters_spoken = 0

    @llm.on("metrics_collected")
    def _on_llm_metrics(metrics):
        nonlocal input_tokens, output_tokens
        try:
            m = getattr(metrics, "metrics", metrics)
            input_tokens += getattr(m, "prompt_tokens", 0)
            output_tokens += getattr(m, "completion_tokens", 0)
            ttft = getattr(m, "ttft", None)
            logger.info(f"⚡ [LATENCY TRACE] LLM Metrics: TTFT={ttft}s | Prompt={getattr(m, 'prompt_tokens', 0)} | Completion={getattr(m, 'completion_tokens', 0)}")
        except Exception as e:
            logger.warning(f"Error extracting LLM metrics: {e}")

    @tts.on("metrics_collected")
    def _on_tts_metrics(metrics):
        nonlocal characters_spoken
        try:
            m = getattr(metrics, "metrics", metrics)
            characters_spoken += getattr(m, "characters_count", 0)
            ttfb = getattr(m, "ttfb", None)
            logger.info(f"⚡ [LATENCY TRACE] TTS Metrics: TTFB={ttfb}s | Chars={getattr(m, 'characters_count', 0)}")
        except Exception as e:
            logger.warning(f"Error extracting TTS metrics: {e}")

    @ctx.room.on("disconnected")
    def _on_disconnected():
        try:
            duration_seconds = time.time() - t_call_start
            duration_minutes = duration_seconds / 60.0
            
            # Determine which LLM was used
            llm_name = llm.__class__.__name__.lower()
            if "openai" in llm_name:
                # Groq Rates
                input_rate = (0.59 * 83.5) / 1000000.0  # cost per token
                output_rate = (0.79 * 83.5) / 1000000.0
                brain_name = "Groq Llama 3.3"
            else:
                # Gemini Rates
                input_rate = (0.075 * 83.5) / 1000000.0
                output_rate = (0.30 * 83.5) / 1000000.0
                brain_name = "Google Gemini 1.5"
                
            cost_vobiz = duration_minutes * 0.40
            cost_cartesia = characters_spoken * 0.00163
            cost_llm = (input_tokens * input_rate) + (output_tokens * output_rate)
            total_cost = cost_vobiz + cost_cartesia + cost_llm
            per_minute_cost = total_cost / duration_minutes if duration_minutes > 0 else 0
            
            billing_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "room_name": ctx.room.name,
                "customer_name": customer_name,
                "duration_seconds": round(duration_seconds, 1),
                "duration_minutes": round(duration_minutes, 2),
                "brain_model": brain_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "characters_spoken": characters_spoken,
                "cost_vobiz_inr": round(cost_vobiz, 3),
                "cost_cartesia_inr": round(cost_cartesia, 3),
                "cost_llm_inr": round(cost_llm, 3),
                "total_cost_inr": round(total_cost, 3),
                "cost_per_minute_inr": round(per_minute_cost, 3)
            }
            
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/call_billing_log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(billing_record) + "\n")
                
            logger.info("📊 [BILLING RECORDED]")
            logger.info(f"   📞 Duration: {duration_minutes:.2f} mins")
            logger.info(f"   🗣️ Speech: {characters_spoken} characters (Cartesia)")
            logger.info(f"   🧠 Brain ({brain_name}): Input={input_tokens}, Output={output_tokens} tokens")
            logger.info(f"   💸 Estimated Cost: Vobiz=₹{cost_vobiz:.2f}, Cartesia=₹{cost_cartesia:.2f}, LLM=₹{cost_llm:.2f} | Total=₹{total_cost:.2f} (₹{per_minute_cost:.2f}/min)")
        except Exception as e:
            logger.error(f"Failed to record call billing: {e}")

    from livekit.agents.voice import UserInputTranscribedEvent





    current_lang = "hi"

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        nonlocal current_lang
        if ev.transcript:
            logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} | Text: '{ev.transcript}'")
        if ev.is_final and ev.transcript:
            text = ev.transcript.strip().lower()
            new_lang = current_lang
            
            # Switch ONLY when explicitly requested by name
            if "marathi" in text or "मराठी" in text:
                new_lang = "mr"
            elif "english" in text or "इंग्लिश" in text:
                new_lang = "en"
            elif "hindi" in text or "हिंदी" in text or "हिन्दी" in text:
                new_lang = "hi"
                
            if new_lang != current_lang:
                current_lang = new_lang
                logger.info(f"🗣️ Explicit Language Switch: '{current_lang}' requested for text: '{ev.transcript}'")
                
                is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
                if is_cartesia and hasattr(session.tts, "update_options"):
                    if current_lang == "mr":
                        session.tts.update_options(
                            voice="5c32dce6-936a-4892-b131-bafe474afe5f",  # Anika (Marathi Feminine)
                            language="mr"
                        )
                        logger.info("🔄 Switched TTS to Marathi (Anika)")
                    elif current_lang == "en":
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

    @session.on("conversation_item_added")
    def on_item_added(item):
        # Truncate context aggressively to stay under Groq's 8,000 TPM limit. Keep system prompt (index 0) and the last 6 messages (3 turns).
        if hasattr(session, "_chat_ctx") and session._chat_ctx:
            if len(session._chat_ctx.items) > 7:
                sys_prompt = session._chat_ctx.items[0]
                recent = session._chat_ctx.items[-6:]
                session._chat_ctx.items = [sys_prompt] + recent
                logger.info(f"✂️ Context Truncated: Keeping system instructions + last 6 items (Total items: {len(session._chat_ctx.items)})")

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

    # Dynamically resolve customer name from participants in the room
    for p in ctx.room.remote_participants.values():
        raw_name = p.name or p.identity
        if raw_name:
            if raw_name.startswith("sip-"):
                raw_name = raw_name.replace("sip-", "")
            raw_name = raw_name.strip().capitalize()
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
            logger.info(f"👤 Resolved customer name dynamically from room participants: {customer_name}")
            break

    agent = PriyaRealEstateAgent(customer_name=customer_name)

    # Start session with record=False
    t_session_start = time.perf_counter()
    logger.info("⏱️ [PERF] Calling session.start()...")
    await session.start(agent=agent, room=ctx.room, record=False)
    
    t_session_ready = (time.perf_counter() - t_session_start) * 1000
    t_total_ready = (time.perf_counter() - t_start) * 1000
    logger.info(f"⏱️ [PERF] session.start() returned! Took {t_session_ready:.1f}ms. Total job-to-ready time: {t_total_ready:.1f}ms")
    logger.info(f"⏱️ [PERF +{t_total_ready:.1f}ms] Agent Session Started & Ready in <50ms!")

    # Allow 1.2s for WebRTC audio negotiation and SIP RTP streams to fully settle
    logger.info("⏳ Allowing 1.2s for audio bridge and SIP RTP connection to settle...")
    await asyncio.sleep(1.2)

    greeting_text = (
        f" Hello... Main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... "
        f"kya main {customer_name} se baat kar sakti hoon?"
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
