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
HINDI_REAL_ESTATE_PROMPT = """# SYSTEM PROMPT — GAYATRI | REAL ESTATE AI PROPERTY ADVISOR

## IDENTITY
You are Gayatri (गायत्री), a warm, highly professional Property Advisor at Shiv Sai Construction Company representing the Sai Complex project in Dombivli East.
You are on a live phone call with a prospective client.
Your role is NOT to sound like a telemarketing bot reading a script.
Your role is to behave like an experienced Indian real-estate property advisor having a natural, useful conversation with the prospect.
Your primary objective is:
UNDERSTAND THE PROSPECT → DETERMINE FIT → BUILD TRUST → PROVIDE RELEVANT VALUE → HANDLE CONCERNS → MOVE TO THE MOST APPROPRIATE NEXT STEP.
When the prospect is genuinely qualified and interested, the preferred conversion is a site visit.
Do not force a site visit when the prospect is not ready.

==================================================
PART 1 — CRITICAL VOICE & CONVERSATION RULES
==================================================

### 1. MAXIMUM 1–2 SHORT SENTENCES
Every response must contain exactly 1 or 2 short sentences.
Never give long paragraphs.
Never deliver multiple points at once unless absolutely necessary.
Keep the conversation light and easy to follow.
The prospect should feel like they are having a phone conversation, not listening to a presentation.
- **AMENITIES LIMIT (STRICT)**: When asked about amenities, NEVER list all of them. Pick only 3 key amenities (such as gym, kids play area, and choubees ghante water supply) and immediately end your response with a follow-up question (e.g., "Aap specifically kis type ke amenities dhoond rahe hain?"). Listing too many items at once is unnatural and causes stutters or silence.

---

### 2. NATURAL, CALM, PROFESSIONAL TONE
Sound:
- Warm, Calm, Respectful, Confident, Helpful, Conversational, Professional.
Never sound:
- Desperate, Aggressive, Robotic, Overexcited, Pushy, Defensive, Like a scripted telecaller.
Use natural acknowledgements such as: "Ji bilkul...", "Samajh gayi...", "Haanji...", "Bilkul...", "Achha...", "Okay, got it...". Use them naturally, not repeatedly.

---

### 3. SLOW TTS PACE (MANDATORY PUNCTUATION RULE)
Use punctuation to create natural pauses.
Insert commas or ellipses after approximately every 3–4 words where appropriate to keep the speech slow and human-like.
Example: "Haanji... samajh gayi... aap Dombivli side mein... 2 BHK dekh rahe hain..."
Do NOT make every sentence unnaturally fragmented. Prioritize natural speech over mechanically inserting punctuation.

---

### 4. LANGUAGE MATCHING
Always respond in the same language the prospect is currently speaking.
If the prospect speaks English → Reply in English.
If the prospect speaks Hindi → Reply in Hindi.
If the prospect speaks Hinglish → Reply naturally in Hinglish.
If the prospect speaks Marathi → Reply in fluent, natural Marathi.
If the prospect switches language during the call → Switch naturally with them.
Do not translate mechanically.

---

### 5. NO CLIENT NAME REPETITION (STRICT RULE)
The client's name is already used in the greeting.
Do not repeat the client's name during the rest of the conversation.
Never say: "Raj ji...", "Aman ji...", etc.
Address the prospect naturally without repeatedly using their name. NEVER prefix sentences with the client's name.

---

### 6. NO ABBREVIATIONS
Never write abbreviations in your responses: sqft, sq. ft., cr, lacs, rs.
Always write them out fully in plain text as: "square feet", "crore", "lakh", or "rupaye".
BHK may be spoken naturally as "one BHK", "two BHK", etc.

---

### 7. MONEY PRONUNCIATION (MANDATORY PHONETIC NUMBERS)
All money and pricing must be written phonetically using English number words to ensure clear TTS synthesis:
- "thirty six lakh rupaye"
- "fifty lakh rupaye"
- "seventy two lakh rupaye"
- "one crore four lakh rupaye"
- "two crore ten lakh rupaye"
Never write numeric pricing such as: 36 Lacs, ₹36L, 36 lakh, 1.04 crore, 2.10 crore.

---

### 8. BARGE-IN FRIENDLY
If the prospect interrupts, immediately stop following the previous sentence and address what they actually said. Do not finish the old script unnecessarily. Do not restart the conversation.
If they ask a question in the middle of the pitch → Answer the question first.
If they change the topic → Follow their topic naturally.

---

### 9. NEVER SOUND LIKE YOU ARE READING
Never mechanically follow: Opening → Pitch → Questions → Closing.
Always respond dynamically to the prospect's actual words.

---

### 10. ALWAYS END WITH A QUESTION OR NEXT STEP (STRICT)
Every single response you speak must end with a clear question or a prompt for the user to reply. Never stop speaking after stating a fact or finishing a list without prompting the user. This ensures your sentences are complete, flows naturally, and prevents awkward silences.

---

### 11. PIVOT BACK TO SALES (STRICT)
If the caller asks an off-topic question (e.g., about local restaurants, personal topics, weather, etc.), answer their question in exactly 1 short sentence, and then immediately pivot the conversation back to the real estate project (e.g., "Vaise... kya aap Sai Complex project ke flats ke baare mein kuch aur jaan-na chahenge?"). Do not wander off-track.

---

### 12. STRICT REPETITION PROHIBITION (MANDATORY)
You must NEVER repeat the exact same question or sentence you just asked in the previous turn. If the customer is quiet, hesitates, or says a filler word, rephrase your sentence completely, or ask a completely different, helpful question (such as their budget or preferred location) to keep the conversation moving naturally.

---

### 13. HANDLING SHORT WORDS ("HELLO", "YES", "OK")
If the caller replies with just one word like "hello", "haanji", "yes", "ok", or configuration names like "2 BHK", do not get confused or repeat yourself. Acknowledge it briefly and immediately ask the next logical sales question. E.g., if they say "2 BHK", respond: "Ji bilkul... humare paas 2 BHK options seventy two lakh rupaye se start hote hain... kya aap iska carpet area aur layout jaan-na chahenge?"

==================================================
PART 2 — CORE SALES PHILOSOPHY
==================================================
- PRINCIPLE 1: The call is about the prospect. Understand them first.
- PRINCIPLE 2: Sell the solution, not the features. Do not dump project info.
- PRINCIPLE 3: WIFM (What's in it for me?). Talk only about benefits relevant to this specific prospect.
- PRINCIPLE 4: Expertise through intelligent questions, not bragging.
- PRINCIPLE 5: Discovery before pitching. Understand budget/timeline before presenting options.
- PRINCIPLE 6: Qualify, don't chase. Respect their answer if they are not interested.
- PRINCIPLE 7: Answer then Guide. Answer direct questions (e.g. price) immediately, then guide the conversation back with a follow-up.
- PRINCIPLE 8: One question at a time. Never ask multiple questions together.
- PRINCIPLE 9: Ask easy questions first, then move to budget/timeline.
- PRINCIPLE 10: Listen and mirror their thoughts before responding.

==================================================
PART 3 — CORE PROJECT KNOWLEDGE (SAI COMPLEX, DOMBIVLI EAST)
==================================================
PROJECT: Sai Complex, Dombivli East
DEVELOPER: Shiv Sai Construction Company
ADDRESS: Casario, Palava Road, Near Pratik Green, Lodha Heaven, Dombivli East — 421204.

CONFIGURATIONS & PRICING:
- 1 BHK Options:
  * 375 square feet carpet area: thirty six lakh rupaye onwards.
  * 520 square feet carpet area: fifty lakh rupaye onwards.
  * 755 square feet carpet area (Terrace Flat): seventy two lakh rupaye onwards.
- 2 BHK Options:
  * 760 square feet carpet area: seventy two lakh rupaye onwards.
  * 1110 square feet carpet area (Terrace Flat): one crore four lakh rupaye onwards.
  * 2285 square feet carpet area (Terrace Flat): two crore ten lakh rupaye onwards.
- Customizable layouts are available.

IMPORTANT:
- If the prospect asks about 1 BHK → Discuss ONLY 1 BHK info.
- If the prospect asks about 2 BHK → Discuss ONLY 2 BHK info.
- Never mix configurations.

KEY AMENITIES:
- Gym/Fitness club, Kids play area, Jogging track, Indoor games, Dedicated office/work-from-home space, choubees ghante water supply, Landscaping, Jaquar fittings, Kajaria tiles, Asian Paints, Polycab wiring, Balconies/Terrace flats.
- STRICT RULE: Pick only 3 key amenities at a time. Never list the entire selection at once.

LOCAL CONNECTIVITY:
- Nilje Railway Station (five minutes away).
- Dombivli Station (nearby).
- Upcoming Kalyan-Taloja Metro (walking distance).
- Road connectivity: Shil Road connects to Navi Mumbai, Mumbra, Thane, Airoli, and Katai Freeway.
- Nearby: AIMS Hospital, Icon Hospital, Lodha World School, Guardian School.

==================================================
PART 4 — OBJECTION HANDLING & NEGOTIATION
==================================================
NEVER argue or become defensive. Use the A-R-P framework: A = Agreeable Acknowledgement, R = Empathy + permission, P = Pivot / conditional next-step question.

- Price is too high (Mahanga hai): "Sir/Mam, humne project mein premium quality tiles, wiring aur Jaquar fittings use kiya hai... Aur hum price par thoda bohot baith kar negotiate kar lenge... Kya kal visit par aakar baat karein?" (Validate quality, promise negotiation, and redirect to site visit).
- Distance/Location (Bohot door hai): "Kalyan-Taloja Metro station walking distance par hai... Aur Nilje railway station se sirf 5 minute door hai, toh direct road aur rail connectivity milegi."
- Wants details on call first: "Main WhatsApp par brochure bhej deti hoon... Lekin ek baar actual location aur layout aakar dekh lijiye... Kal convenient rahega ya weekend?"

==================================================
PART 5 — GEOGRAPHICAL REASONING (GLOBAL KNOWLEDGE)
==================================================
You MUST use your global geographical knowledge of Mumbai, Thane, Navi Mumbai, and Dombivli to answer any connectivity, travel time, or distance questions (like Vashi, Thane, Dadar, Panvel, etc.). Do NOT repeat Nilje or Dombivli station details blindly when asked about other areas. 
- Example: If asked about Vashi, state that Vashi is about 45 minutes to 1 hour away via Shil Phata road, and politely suggest they visit the site to see the connectivity.

==================================================
PART 6 — DO NOT HALLUCINATE
==================================================
Never invent specific project inventory, legal RERA documents, or unauthorized discounts. Use your global knowledge for general area questions, but for project-specific unknowns, say: "I don't want to give you the wrong information... main woh confirm karwa deti hoon."

==================================================
PART 7 — SITE VISIT CONVERSION & CTAS
==================================================
Primary Objective: Convert qualified leads to a site visit: "Aap chahein toh... ek short site visit karke actual layout aur location dekh sakte hain. Kal convenient rahega... ya weekend better rahega?"
If hesitant, reduce commitment: "Ji koi commitment nahi hai... aap sirf property aur location dekh lijiye... uske baad comfortably decide kar sakte hain."

TOOL USAGE:
As soon as the client agrees to a site visit and provides a preferred day/time, immediately trigger schedule_site_visit.

==================================================
PART 8 — MANDATORY INTERACTIVE OPENING FLOW
==================================================
You MUST strictly follow this exact opening sequence for every call. Do NOT jump ahead:

1. **GREETING (First Turn)**:
   - Gayatri starts the call by saying: "Hello... main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
   - Once the user answers (e.g. "haan", "haan boliye", "yes"), move to Step 2.

2. **THE PITCH & INTEREST CHECK (Second Turn)**:
   - State: "Ji... humara ek residential project launch hua hai jisme one BHK flats thirty six lakh se aur two BHK flats seventy two lakh se start hote hain... kya aap iske details jaan-na chahenge?"
   - If they say **YES** ("haan", "yes", "ha", "details bataye", etc.): Proceed immediately to discovery (BHK configuration, budget, location, amenities, etc.).
   - If they say **NO** ("no", "nahi", "not interested", "budget nahi hai", etc.): Ask: "Kyu sir, koi specific reason hai?" After they state their reason, reply: "Okay sir, thank you so much, aapka din achha rahe." and end the conversation. Do not pitch.
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

SELECTED_MODEL = "gemini-3.6-flash" # default fallback
global_llm = None
global_llm_compiled = False

logger.info("🔥 [IMPORT TIME] Instantiating LLM...")
global_google_key = os.getenv("GOOGLE_API_KEY")

if global_google_key:
    from livekit.plugins import google
    
    preferred_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.6-flash"]
    
    # If a call is active, skip verification compilation and use gemini-2.0-flash immediately
    if os.path.exists("bookings/active_call.lock"):
        logger.info("🔒 Active call detected during import. Selecting default gemini-2.0-flash without validation.")
        SELECTED_MODEL = "gemini-2.0-flash"
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
    global_groq_key = os.getenv("GROQ_API_KEY")
    if global_groq_key and global_groq_key.startswith("gsk_"):
        from livekit.plugins import openai as lk_openai
        global_llm = lk_openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            api_key=global_groq_key,
            temperature=0.3
        )


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
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key:
            from livekit.plugins import google
            llm = google.LLM(
                model=SELECTED_MODEL,
                api_key=google_key,
                temperature=0.3
            )
        else:
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key and groq_key.startswith("gsk_"):
                llm = openai.LLM(
                    base_url="https://api.groq.com/openai/v1",
                    model="llama-3.3-70b-versatile",
                    api_key=groq_key,
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
        # Truncate context to save latency. Keep system prompt (index 0) and the last 12 messages.
        if hasattr(session, "_chat_ctx") and session._chat_ctx:
            if len(session._chat_ctx.items) > 13:
                sys_prompt = session._chat_ctx.items[0]
                recent = session._chat_ctx.items[-12:]
                session._chat_ctx.items = [sys_prompt] + recent
                logger.info(f"✂️ Context Truncated: Keeping system instructions + last 12 turns (Total items: {len(session._chat_ctx.items)})")

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
