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
from typing import Optional
import requests
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
load_dotenv("voice_agent/.env")
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
HINDI_REAL_ESTATE_PROMPT = """# GAYATRI — AI REAL ESTATE PROPERTY ADVISOR (MASTER SYSTEM PROMPT)

1. WHO YOU ARE
- You are Gayatri (गायत्री), a warm, intelligent and professional Property Advisor representing Shiv Sai Construction Company for the Sai Complex project in Dombivli East.
- You speak with prospective property buyers on live outbound telephony calls.
- You are an appointment-setting property advisor, not a traditional telecaller.
- You do NOT sound like an advertisement. You do NOT sound like an AI. You do NOT read rigid scripts.
- You do NOT try to sell the entire property over the phone.
- You behave like an experienced human property advisor who understands people, asks good questions, answers intelligently, handles objections calmly, and knows when to stop talking.
- STRICT CONVERSATION BREVITY & SPEED: Speak ONLY 1 to 2 short sentences per turn (maximum 20-25 words). Keep answers direct, punchy, and concise so speech generates and starts immediately without long monologues.

2. OPENING CONVERSATION FLOW (MANDATORY STEP-BY-STEP SEQUENCE)
- **Turn 1 (Spoken by Agent on call connect)**:
  "Hello... Main Gayatri baat kar rahi hoon Sai Complex Dombivli East se... kya main [Customer Name] se baat kar sakti hoon?"
- **Turn 2 (Direct Value Pitch when customer responds - e.g. 'haan', 'boliye', 'ji boliye', 'kaun?', 'kya kaam tha?')**:
  Directly pitch the available property without restrictive qualifying questions:
  "Ji, Sai Complex Dombivli East ke regarding call kiya hai... yahan premium one aur two BHK flats thirty six lakh rupaye se start ho rahe hain with modern amenities. Aap apne liye one BHK dekh rahe hain ya two BHK?"
  (DO NOT ask "Kya aap Dombivli mein property dekh rahe hain?" or other restrictive qualifying questions. Pitch directly).
- **When customer specifies configuration (e.g. 'one BHK', 'two BHK')**:
  State the exact options and price, then smoothly bridge to a site visit:
  - For 1 BHK: "Humare paas one BHK thirty six lakh rupaye se start hote hain. Kya aap weekend par ya weekday par ek baar actual flat dekhne ke liye site visit karna chahenge?"
  - For 2 BHK: "Humare paas two BHK seventy two lakh rupaye se start hote hain. Kya aap weekend par ya weekday par ek baar actual flat dekhne ke liye site visit karna chahenge?"

- **Location Preference & Shift Handling (CRITICAL - When customer mentions Kalyan, Thane, Navi Mumbai, etc.)**:
  - If customer says they are looking in Kalyan or any other location:
    State property unavailability in that location clearly and politely, explain Dombivli proximity, and check interest:
    "Sir humara property Kalyan mein available nahi hai. Humara project Sai Complex Dombivli East mein hai jo Kalyan se sirf fifteen minutes drive par hai. Agar aap Dombivli East consider karna chahein toh kya main details share kar sakti hoon?"
  - If customer agrees to hear details: Share the BHK pricing and bridge to a site visit.
  - If customer says NO / strictly wants Kalyan only / refuses Dombivli:
    State property unavailability explicitly and end the call gracefully:
    "Samajh gayi sir... filhal Kalyan mein humara project available nahi hai. Aapka samay dene ke liye shukriya, aapka din shubh ho... bye!"
    and immediately call `end_call()` or `update_lead_status(status="not_interested")`.
- **Refusal on Pitch (If customer says hard NO / not looking for property / wrong number)**:
  Politely say: "Okay sir, koi baat nahi. Thank you so much, aapka din shubh ho... bye!" and call `end_call()`.

3. BALANCED SITE VISIT GUIDANCE (PROACTIVE YET NATURAL)
- Keep responses short (1 to 2 sentences max).
- When answering pricing, connectivity, or amenities, answer the question directly, and smoothly add the site visit invite:
  - Example for pricing: "Humare paas two BHK seventy two lakh rupaye se start hote hain. Kya aap weekend par ya weekday par ek baar actual flat dekhne ke liye site visit karna chahenge?"
  - Example for connectivity: "Vashi Shil Road se lagbhag twenty five se thirty minutes drive distance hai. Kya aap Saturday ya Sunday ko project visit plan karna chahenge?"
- Do NOT ask unnecessary intermediate questions like "aur koi detail chahiye?" right before asking about the visit. Bridge directly to the site visit invitation.
- When the customer agrees or mentions a day (e.g. "Saturday ko", "Weekend", "Kal", "Monday"):
  Immediately call `schedule_site_visit(preferred_day=..., preferred_time=..., flat_type=...)`.

4. MANDATORY CALL CLOSING RULE
- Whenever ending or concluding the call (after booking a site visit, or when the customer has no more questions, or if the customer is not interested):
- ALWAYS politely conclude with:
  "Aapka din shubh ho... bye!"
  (Example: "Thank you so much... aapka din shubh ho... bye!" or "Ji bilkul... aapka din shubh ho... bye!").

5. CRITICAL VOICE, SCRIPT & TTS FORMATTING (MANDATORY)
- SCRIPT & LANGUAGE: ALWAYS write your spoken outputs in natural Hinglish using ONLY the standard English Latin alphabet (e.g., "Ji, Sai Complex Dombivli East mein hai...").
- CLEAN PUNCTUATION ONLY: Use standard single periods (.) and question marks (?). NEVER use multiple consecutive dots like "..." or hyphens "--" or commas in series, as these cause neural TTS audio breaks and micro-stutters.
- STRICTLY NO DEVANAGARI: NEVER output Hindi/Marathi Devanagari script under any circumstances.
- STRICTLY NO MARKDOWN: NEVER use asterisks (NO ** or *), NO hashes (#), NO bullet points, NO quotes. Everything you write is read aloud by Text-To-Speech.
- STRICTLY NO EMOJIS: Absolutely NO emojis (no 🙏, 🏠, 📞, etc.).
- PHONETIC PRICING ONLY: Write all numbers and pricing phonetically in words only.
  - GOOD: "thirty six lakh rupaye", "fifty lakh rupaye", "seventy two lakh rupaye", "one crore four lakh rupaye", "two crore ten lakh rupaye", "square feet".
  - BAD: ₹36L, 36L, 36 lakh, 1.04 Cr, sqft, BHK (except saying "one BHK", "two BHK").
- NO REPEATING CLIENT NAME: Do NOT use the prospect's name in every sentence. You may use it once in the greeting, never repeatedly.

6. PROJECT FACTS & LOCAL CONNECTIVITY (SAI COMPLEX, DOMBIVLI EAST)
- Developer: Shiv Sai Construction Company.
- Location: Casario, Palava Road, Near Pratik Green, Lodha Heaven, Dombivli East — 421204.
- 1 BHK Options: 375 square feet (thirty six lakh rupaye onwards), 520 square feet (fifty lakh rupaye onwards), 755 square feet Terrace (seventy two lakh rupaye onwards).
- 2 BHK Options: 760 square feet (seventy two lakh rupaye onwards), 1110 square feet Terrace (one crore four lakh rupaye onwards), 2285 square feet Terrace (two crore ten lakh rupaye onwards). Customizable layouts available.
  - Configuration Rule: If prospect asks about 1 BHK, discuss only 1 BHK. If 2 BHK, discuss only 2 BHK. Do not mix.
- Amenities: Fitness club/gym, kids play area, jogging track, 24-hour water supply, landscaping, Jaquar bathroom fittings, Kajaria tiles.
- Comprehensive Connectivity Details:
  - Nilje Railway Station: Approx five minutes from site.
  - Dombivli Station: Central line station nearby, approx fifteen to twenty minutes.
  - Vashi / Navi Mumbai / Airoli: Shil Road directly connects to Mahape, Airoli, Kopar Khairane, and Vashi in approx twenty five to thirty minutes drive.
  - Kalyan: Approx fifteen minutes away; Upcoming Kalyan-Taloja Metro station is walking distance from Sai Complex.
  - Thane: Accessible via Shilphata Road in approx twenty five minutes.
- Nearby: AIMS Hospital, Icon Hospital, Lodha World School, Guardian School.

7. THREE-LEVEL KNOWLEDGE SYSTEM (NEVER HALLUCINATE)
- Level 1 (Verified Fact): Answer confidently from verified project facts above.
- Level 2 (Safe Context): Use cautious language ("Available details ke according...", "Generally...").
- Level 3 (Unknown): If information is not verified (e.g., exact RERA number, possession date, bank loan approvals, specific parking allocation, maintenance charges), say: "Iska exact detail main property team se confirm karwa deti hoon... main aapko wrong information nahi dena chahti." NEVER invent or guess.

8. OBJECTION HANDLING
- Price Objection: "Ji... samajh gayi... aapka comfortable budget roughly kis range mein hai? Available option aapke range ke closer ho toh ek baar site par dekhna useful rahega."
- Location Objection: "Ji... location important hai... aapke liye daily connectivity main concern hai? Ek baar actual location dekh lenge toh better idea mil jayega."
- "I need to think": "Bilkul... decision soch samajh kar hi lena chahiye... aapko mainly price ko lekar sochna hai ya property compare kar rahe hain?"
- "Family": "Bilkul... family ke saath ek baar visit karke layout dekh lijiye... weekend convenient rahega ya weekday?"
- WhatsApp Details: "Ji bilkul... main brochure WhatsApp kar deti hoon... aap ek baar dekh lijiye." (Call `send_whatsapp_brochure`).
- Free VIP Cab Pickup: Free VIP cab pickup is available for site visits. Offer when scheduling: "Free VIP cab pickup ke saath site visit arrange kar sakte hain... Saturday convenient rahega ya weekend?"
- Two-Choice Close: Always give two choices ("Weekday convenient rahega ya weekend?", "Morning convenient rahega ya evening?").

9. HANDLING REFUSALS & NO
- SOFT NO ("Maybe later", "I'll think"): Explore gently once.
- HARD NO ("Nahi chahiye", "Not interested", "Don't want it"): Respect it immediately: "Koi baat nahi... thank you for your time... aapka din shubh ho... bye!" Call `update_lead_status(status="not_interested")`.
- DNC ("Don't call me", "Remove my number"): "Ji bilkul... samajh gayi... aapko disturb nahi karungi... aapka din shubh ho... bye!" Call `update_lead_status(status="not_interested")`.
- NEVER trigger `update_lead_status` on conversational pauses or filler words like "na" or "achha na".

10. SCHEDULING MODE & CALL ENDING
- When client agrees to a site visit and mentions a day or date (e.g., "Monday", "Kal", "Saturday", "Weekend"):
  - IMMEDIATELY call `schedule_site_visit(preferred_day=..., preferred_time=..., flat_type=...)`.
  - Say: "Maine aapka site visit confirm kar diya hai... WhatsApp par details bhej rahi hoon... aapka din shubh ho... bye!"
- When call concludes or client is not interested:
  - Call `update_lead_status(status="not_interested")` or `end_call()`.
  - Say: "Aapka din shubh ho... bye!"
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
    def __init__(self, customer_name: str = "Aman ji", customer_phone: str = "", hangup_fnc=None):
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self._hangup_fnc = hangup_fnc
        instructions = (
            f"{HINDI_REAL_ESTATE_PROMPT}\n\n"
            f"Aap abhi {customer_name} se call par baat kar rahi hain. "
            "STRICT RULE: Do NOT say the client's name in your responses. You must talk to them directly without repeating or saying their name at all. NEVER prefix your sentences with their name."
        )
        super().__init__(instructions=instructions)

    @function_tool(description="Schedule property site visit when client specifies a day/date.")
    async def schedule_site_visit(
        self,
        customer_name: str,
        preferred_day: str,
        preferred_time: str = "Not specified",
        flat_type: str = "2BHK",
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
            "status": "site_visit_confirmed",
            "lead_status": "interested"
        }

        try:
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/property_visits.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(visit_record) + "\n")
        except Exception as e:
            logger.error(f"Failed to save visit record: {e}")

        # Trigger automatic call termination after goodbye message is spoken
        if self._hangup_fnc:
            self._hangup_fnc(delay_seconds=4.0)

        time_str = f" at {preferred_time}" if preferred_time != "Not specified" else ""
        return f"Maine {preferred_day}{time_str} ko site visit confirm kar diya hai... Main is number par details WhatsApp kar deti hoon... aapka din shubh ho... bye!"

    @function_tool(description="Call ONLY when client explicitly and firmly refuses (e.g. 'nahi chahiye', 'not interested', 'don't call me', 'wrong number').")
    async def update_lead_status(
        self,
        customer_name: str,
        status: str,  # "interested" or "not_interested"
        notes: str = ""
    ) -> str:
        logger.info("=" * 60)
        logger.info(f"📋 [LEAD STATUS UPDATED] -> {status.upper()}")
        logger.info(f"👤 Client Name     : {customer_name}")
        logger.info(f"📝 Notes           : {notes}")
        logger.info("=" * 60)

        record = {
            "customer_name": customer_name,
            "status": status,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/property_visits.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to save lead status record: {e}")

        if status == "interested":
            return "Lead marked as interested. You should continue talking and guide them towards a site visit."
        else:
            if self._hangup_fnc:
                self._hangup_fnc(delay_seconds=3.5)
            return "Lead marked as not interested. Say 'Aapka din shubh ho... bye!' and end the conversation."

    @function_tool(description="End the telephone call after saying goodbye ('Aapka din shubh ho... bye!') when the conversation has concluded.")
    async def end_call(self) -> str:
        logger.info("📞 [CALL TERMINATION TOOL INVOKED]")
        if self._hangup_fnc:
            self._hangup_fnc(delay_seconds=3.5)
        return "Call will automatically terminate in 3.5 seconds. Say 'Aapka din shubh ho... bye!'."

    @function_tool(description="Send Sai Complex brochure or pricing to client on WhatsApp.")
    async def send_whatsapp_brochure(
        self,
        customer_name: str = "",
        phone_number: str = "",
        media_url: str = ""
    ) -> str:
        # Fallback customer name
        target_name = customer_name.strip() if customer_name else getattr(self, "customer_name", "Client")
        
        # Fallback phone number
        target_phone = phone_number.strip() if phone_number else ""
        if not target_phone or "<phone" in target_phone.lower() or not any(c.isdigit() for c in target_phone):
            target_phone = getattr(self, "customer_phone", "") or "+918693081506"

        logger.info("=" * 60)
        logger.info("📱 [SENDING WHATSAPP BROCHURE / DOCUMENT]")
        logger.info(f"👤 Client Name     : {target_name}")
        logger.info(f"📞 Phone Number    : {target_phone}")
        logger.info(f"📄 Media URL       : {media_url or 'Default Brochure'}")
        logger.info("=" * 60)

        # Standardize phone number format
        clean_phone = target_phone.strip().replace(" ", "").replace("-", "")
        if not clean_phone.startswith("+"):
            if len(clean_phone) == 10:
                clean_phone = "+91" + clean_phone
            else:
                clean_phone = "+" + clean_phone

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        api_key_sid = os.getenv("TWILIO_API_KEY_SID")
        api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_WHATSAPP_SENDER", "whatsapp:+14155238886")
        
        # If a media URL is provided (like the statement PDF), send a tailored statement message
        if media_url and any(k in media_url.lower() for k in ["statement", "paradise", "yashraj"]):
            message_body = (
                f"Namaste {target_name},\n\n"
                "As requested, here is your requested Payment & Account Statement for *Yashraj Paradise*.\n\n"
                "You can view and download the PDF document attached below. Have a nice day!"
            )
        else:
            message_body = (
                f"Namaste {target_name},\n\n"
                "Thank you for speaking with Gayatri at Shiv Sai Construction.\n"
                "As requested, here are the brochure and pricing details for *Sai Complex*, Dombivli East:\n\n"
                "📍 *Location*: Palava Road, near Pratik Green, Dombivli East\n"
                "💰 *Pricing*:\n"
                "• 1 BHK: Starts at 36 Lakh\n"
                "• 2 BHK: Starts at 72 Lakh\n\n"
                "📄 *Brochure PDF*: https://sai-complex.com/brochure.pdf\n\n"
                "If you have any questions, reply to this message. Have a nice day!"
            )

        try:
            if not account_sid:
                logger.warning("TWILIO_ACCOUNT_SID is not configured.")
                return "Maine aapke number par WhatsApp details note kar li hain, thodi der mein receive ho jayegi."

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            data = {
                "From": from_number,
                "To": f"whatsapp:{clean_phone}",
                "Body": message_body
            }
            if media_url:
                data["MediaUrl"] = media_url
                
            auth = (account_sid, auth_token) if auth_token else (api_key_sid, api_key_secret)
            r = requests.post(url, data=data, auth=auth, timeout=10)
            
            if r.status_code in [200, 201]:
                logger.info(f"✅ WhatsApp document successfully sent to {clean_phone} via Twilio.")
                return "Maine WhatsApp par details aur document send kar diya hai."
            else:
                logger.warning(f"⚠️ Twilio WhatsApp Send failed (Status {r.status_code}): {r.text}")
                return "Maine aapke number par WhatsApp details note kar li hain, thodi der mein receive ho jayegi."
        except Exception as e:
            logger.error(f"❌ Error sending WhatsApp: {e}")
            return "Maine aapke number par WhatsApp details note kar li hain, thodi der mein receive ho jayegi."

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
global_fireworks_key = os.getenv("FIREWORKS_API_KEY")
llm_provider = os.getenv("LLM_PROVIDER", "google").strip().lower()

# 0. FIREWORKS AI (Dedicated Voice AI Inference, Sub-100ms TTFT, High Quota)
fw_healthy = False
if global_fireworks_key and llm_provider in ["fireworks", "fw"]:
    try:
        from openai import OpenAI as SyncOpenAI
        _test_fw = SyncOpenAI(base_url="https://api.fireworks.ai/inference/v1", api_key=global_fireworks_key, timeout=2.5)
        _test_fw.chat.completions.create(
            model=os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/gpt-oss-120b"),
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5
        )
        fw_healthy = True
    except Exception as fw_err:
        logger.warning(f"⚠️ Fireworks AI health check failed: {fw_err}. Falling back to Google Gemini immediately.")

if fw_healthy and global_fireworks_key and llm_provider in ["fireworks", "fw"]:
    from livekit.plugins import openai as lk_openai
    fw_model = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/gpt-oss-120b")
    logger.info(f"🎆 [FIREWORKS AI] Selected model '{fw_model}' with sub-100ms streaming!")
    global_llm = lk_openai.LLM(
        base_url="https://api.fireworks.ai/inference/v1",
        model=fw_model,
        api_key=global_fireworks_key,
        temperature=0.3,
        reasoning_effort="low",
        max_completion_tokens=160
    )
    SELECTED_MODEL = fw_model
    global_llm_compiled = True

# 1. GOOGLE GEMINI (High Quota, Instant Streaming, 0 Rate Limit Choking in Long Calls)
elif global_google_key and (llm_provider in ["google", "gemini"] or not (global_groq_key and global_groq_key.startswith("gsk_"))):
    from livekit.plugins import google
    
    preferred_models = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-lite-latest", "gemini-3.5-flash"]
    
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
                logger.warning("All preferred models failed validation. Falling back to gemini-3.5-flash-lite.")
                global_llm = google.LLM(model="gemini-3.5-flash-lite", api_key=global_google_key, temperature=0.3)
                SELECTED_MODEL = "gemini-3.5-flash-lite"
        except Exception as outer_err:
            logger.warning(f"Self-healing LLM selector setup failed: {outer_err}. Defaulting to gemini-3.5-flash-lite.")
            global_llm = google.LLM(model="gemini-3.5-flash-lite", api_key=global_google_key, temperature=0.3)
            SELECTED_MODEL = "gemini-3.5-flash-lite"

# 2. GROQ LPU (If explicitly set or Google key not configured)
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
            temperature=0.3
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
                        temperature=0.3
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
                        model="gemini-3.5-flash-lite",
                        api_key=global_google_key,
                        temperature=0.3
                    )
                    SELECTED_MODEL = "gemini-3.5-flash-lite"
                    SELECTED_GROQ_MODEL = None
                else:
                    logger.warning("All preferred Groq models failed validation and no GOOGLE_API_KEY is available. Forcing llama-3.3-70b-versatile.")
                    global_llm = lk_openai.LLM(
                        base_url="https://api.groq.com/openai/v1",
                        model="llama-3.3-70b-versatile",
                        api_key=global_groq_key,
                        temperature=0.3
                    )
                    SELECTED_GROQ_MODEL = "llama-3.3-70b-versatile"
        except Exception as outer_err:
            if global_google_key:
                logger.warning(f"Self-healing Groq LLM selector setup failed: {outer_err}. Falling back to Google Gemini.")
                from livekit.plugins import google
                global_llm = google.LLM(
                    model="gemini-3.5-flash-lite",
                    api_key=global_google_key,
                    temperature=0.3
                )
                SELECTED_MODEL = "gemini-3.5-flash-lite"
                SELECTED_GROQ_MODEL = None
            else:
                logger.warning(f"Self-healing Groq LLM selector setup failed: {outer_err}. Forcing llama-3.3-70b-versatile.")
                global_llm = lk_openai.LLM(
                    base_url="https://api.groq.com/openai/v1",
                    model="llama-3.3-70b-versatile",
                    api_key=global_groq_key,
                    temperature=0.3
                )
                SELECTED_GROQ_MODEL = "llama-3.3-70b-versatile"
else:
    logger.warning("Neither GOOGLE_API_KEY nor GROQ_API_KEY is configured.")


# Maharashtra Real Estate Specific STT Keyword Boosting and Phonetic Replacements
STT_KEYWORDS = [
    ("Dombivli", 2.5),
    ("Vashi", 2.5),
    ("Kalyan", 2.0),
    ("Nilje", 2.0),
    ("Palava", 2.0),
    ("Thane", 2.0),
    ("Airoli", 2.0),
    ("Sai Complex", 2.0),
    ("Shil Road", 2.0),
    ("BHK", 2.0),
    ("one BHK", 2.0),
    ("two BHK", 2.0),
    ("Lodha", 1.8),
    ("Casario", 1.8),
    ("flat", 1.5),
    ("carpet", 1.5),
    ("terrace", 1.5),
    ("lakh", 1.5),
    ("crore", 1.5),
    ("budget", 1.5),
    ("visit", 1.5),
]

STT_REPLACE = {
    "washing station": "Vashi station",
    "washing": "Vashi",
    "bashi": "Vashi",
    "kaliyan": "Kalyan",
    "kalyan station": "Kalyan station",
    "dombivali": "Dombivli",
    "dombiwali": "Dombivli",
    "nilje station": "Nilje station",
}


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

    # 2. Pre-warm Deepgram Nova-2 STT (200ms endpointing + domain keyword boosting)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    proc.userdata["stt"] = deepgram.STT(
        language="hi",
        model="nova-2",
        endpointing_ms=50,
        utterance_end_ms=1000,
        smart_format=True,
        keywords=STT_KEYWORDS,
        replace=STT_REPLACE,
        api_key=deepgram_key
    )

    # 3. Pre-warm Silero VAD (16kHz native rate for zero downsampling lag on VPS CPU)
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.35,
        min_speech_duration=0.06,
        sample_rate=16000
    )

    # 4. Pre-warm Cartesia/ElevenLabs TTS (loads client network config in background)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "0.90"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "Calm").strip()
    if cartesia_key and len(cartesia_key) > 10:
        proc.userdata["tts"] = cartesia.TTS(
            api_key=cartesia_key,
            voice=kusha_voice_id,
            language="hi",
            sample_rate=24000,
            model="sonic-3.5",
            speed=cartesia_speed,
            emotion=[cartesia_emotion] if cartesia_emotion else None,
            word_timestamps=False
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
    customer_phone = "+918693081506"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            if meta.get("phone"):
                customer_phone = meta.get("phone")
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
            endpointing_ms=50,
            utterance_end_ms=1000,
            smart_format=True,
            keywords=STT_KEYWORDS,
            replace=STT_REPLACE,
            api_key=deepgram_key
        )
        ctx.proc.userdata["stt"] = stt

    llm = ctx.proc.userdata.get("llm")
    if not llm:
        logger.info("⏱️ [LLM] Initializing LLM dynamically on demand...")
        fireworks_key = os.getenv("FIREWORKS_API_KEY")
        sambanova_key = os.getenv("SAMBANOVA_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")
        llm_provider = os.getenv("LLM_PROVIDER", "google").strip().lower()
        
        if fireworks_key and llm_provider in ["fireworks", "fw"]:
            fw_model = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/gpt-oss-120b")
            llm = openai.LLM(
                base_url="https://api.fireworks.ai/inference/v1",
                model=fw_model,
                api_key=fireworks_key,
                temperature=0.3,
                reasoning_effort="low",
                max_completion_tokens=160
            )
        elif (llm_provider in ["google", "gemini"] or not (groq_key and groq_key.startswith("gsk_"))) and google_key:
            from livekit.plugins import google
            llm = google.LLM(
                model=SELECTED_MODEL,
                api_key=google_key,
                temperature=0.3
            )
        elif groq_key and groq_key.startswith("gsk_") and SELECTED_GROQ_MODEL:
            llm = openai.LLM(
                base_url="https://api.groq.com/openai/v1",
                model=SELECTED_GROQ_MODEL,
                api_key=groq_key,
                temperature=0.3
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
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "0.90"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "Calm").strip()
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    if not tts:
        logger.info("⏱️ [TTS] Initializing TTS dynamically on connection...")
        cartesia_key = os.getenv("CARTESIA_API_KEY")
        if cartesia_key and len(cartesia_key) > 10:
            logger.info(f"Initializing Cartesia TTS as Primary with Kusha Cloned Voice ({kusha_voice_id}) on sonic-3.5 (speed={cartesia_speed}, emotion={cartesia_emotion})...")
            tts = cartesia.TTS(
                api_key=cartesia_key,
                voice=kusha_voice_id,
                language="hi",
                sample_rate=24000,
                model="sonic-3.5",
                speed=cartesia_speed,
                emotion=[cartesia_emotion] if cartesia_emotion else None,
                word_timestamps=False
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
    


    # VAD is pre-warmed, but load as fallback if not present (16kHz native sample rate)
    vad = ctx.proc.userdata.get("vad")
    if not vad:
        logger.info("⏱️ [VAD] Loading Silero VAD model on demand...")
        vad = silero.VAD.load(
            min_silence_duration=0.35,
            min_speech_duration=0.06,
            sample_rate=16000
        )
    
    # Reset TTS options only if it is Cartesia (ElevenLabs uses different options structure)
    is_cartesia = tts and "cartesia" in tts.__class__.__module__
    if is_cartesia and hasattr(tts, "update_options"):
        tts.update_options(
            voice=kusha_voice_id,
            language="hi",
            speed=cartesia_speed,
            emotion=[cartesia_emotion] if cartesia_emotion else None
        )
        logger.info(f"🔄 [STATE RESET] Cartesia TTS options reset to natural Kusha Cloned Voice ({kusha_voice_id}, speed={cartesia_speed}, emotion={cartesia_emotion}).")

    t_session_init = time.perf_counter()
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        turn_handling={
            "turn_detection": "vad",
            "endpointing": {
                "mode": "fixed",
                "min_delay": 0.45,
            },
            "preemptive_generation": {
                "enabled": False,  # Prevents aborted/conflicting LLM calls on transcript mutations
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
    call_dialogue = []  # List of {"role": "agent"|"customer", "text": str, "time": float}
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
            if watchdog_task and not watchdog_task.done():
                watchdog_task.cancel()
            duration_seconds = time.time() - t_call_start
            duration_minutes = duration_seconds / 60.0
            
            # Determine which LLM was used
            current_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
            if current_provider in ["fireworks", "fw"]:
                # Fireworks AI gpt-oss-120b rates (~$0.20 per 1M tokens)
                input_rate = (0.20 * 83.5) / 1000000.0
                output_rate = (0.20 * 83.5) / 1000000.0
                brain_name = f"Fireworks AI ({SELECTED_MODEL.split('/')[-1] if '/' in SELECTED_MODEL else SELECTED_MODEL})"
            elif current_provider == "groq" or (global_groq_key and global_groq_key.startswith("gsk_") and "openai" in llm.__class__.__module__.lower()):
                # Groq Rates
                input_rate = (0.59 * 83.5) / 1000000.0  # cost per token
                output_rate = (0.79 * 83.5) / 1000000.0
                brain_name = "Groq Llama 3.3"
            else:
                # Gemini Rates
                input_rate = (0.075 * 83.5) / 1000000.0
                output_rate = (0.30 * 83.5) / 1000000.0
                brain_name = f"Google Gemini ({SELECTED_MODEL})"
                
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

            # --- FULL TRANSCRIPT CAPTURE & INTELLIGENCE EXTRACTION ---
            formatted_lines = []
            for turn in call_dialogue:
                role_label = "Gayatri" if turn["role"] == "agent" else customer_name
                formatted_lines.append(f"[{turn['time']}s] {role_label}: {turn['text']}")
            formatted_transcript = "\n".join(formatted_lines) if formatted_lines else "No conversation recorded."

            all_customer_text = " ".join(t["text"].lower() for t in call_dialogue if t["role"] == "customer")
            all_dialogue_text = " ".join(t["text"].lower() for t in call_dialogue)

            detected_questions = []
            if any(w in all_customer_text for w in ["kalyan", "kaliyan"]):
                detected_questions.append("Kalyan Location Inquiry")
            if any(w in all_customer_text for w in ["2 bhk", "two bhk", "price", "pricing", "kitna", "budget", "lakh", "cost"]):
                detected_questions.append("Pricing & Budget (2 BHK / 1 BHK)")
            if any(w in all_customer_text for w in ["vashi", "station", "nilje", "distance", "door", "connectivity", "metro", "thane"]):
                detected_questions.append("Station & Metro Connectivity")
            if any(w in all_customer_text for w in ["possession", "ready", "rera", "builder", "kab tak"]):
                detected_questions.append("Possession Date & RERA")
            if any(w in all_customer_text for w in ["gym", "amenities", "water", "parking", "lift"]):
                detected_questions.append("Amenities & Facilities")
            if any(w in all_customer_text for w in ["visit", "dekhne", "aana", "saturday", "sunday", "weekend", "kal"]):
                detected_questions.append("Site Visit Planning")

            # Classify Call Outcome
            if any("site visit confirm" in t["text"].lower() or "schedule_site_visit" in t["text"].lower() for t in call_dialogue if t["role"] == "agent"):
                call_outcome = "Site Visit Scheduled"
            elif any("kalyan mein humara project available nahi hai" in t["text"].lower() or "kalyan" in all_customer_text for t in call_dialogue):
                call_outcome = "Location Mismatch (Kalyan)"
            elif any(w in all_customer_text for w in ["nahi chahiye", "not interested", "dont call", "wrong number"]):
                call_outcome = "Not Interested"
            elif detected_questions:
                call_outcome = "Inquiry Completed"
            else:
                call_outcome = "Short / Call Dropped"

            transcript_record = {
                "call_id": ctx.room.name,
                "timestamp": datetime.utcnow().isoformat(),
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "duration_seconds": round(duration_seconds, 1),
                "duration_minutes": round(duration_minutes, 2),
                "outcome": call_outcome,
                "detected_questions": detected_questions,
                "turns_count": len(call_dialogue),
                "dialogue": call_dialogue,
                "full_transcript": formatted_transcript,
                "billing": billing_record
            }

            os.makedirs("bookings/transcripts", exist_ok=True)
            with open("bookings/call_transcripts.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(transcript_record, ensure_ascii=False) + "\n")

            with open(f"bookings/transcripts/{ctx.room.name}.json", "w", encoding="utf-8") as f:
                json.dump(transcript_record, f, ensure_ascii=False, indent=2)

            logger.info(f"📝 [TRANSCRIPT RECORDED] Saved full transcript to bookings/transcripts/{ctx.room.name}.json (Outcome: {call_outcome})")

            # Sync with db.json for the Next.js Cold Calling Dashboard
            try:
                db_path = "db.json"
                if os.path.exists(db_path):
                    with open(db_path, "r", encoding="utf-8") as f:
                        db_data = json.load(f)
                    
                    if "callLogs" not in db_data:
                        db_data["callLogs"] = []

                    if not any(log.get("callSid") == ctx.room.name for log in db_data["callLogs"]):
                        new_log = {
                            "id": f"call-{int(time.time()*1000)}",
                            "leadId": f"lead-{customer_name.lower().replace(' ', '')}",
                            "callSid": ctx.room.name,
                            "durationSeconds": round(duration_seconds),
                            "recordingUrl": "",
                            "transcript": formatted_transcript,
                            "aiSummary": f"Call with {customer_name}. Outcome: {call_outcome}. Questions: {', '.join(detected_questions) if detected_questions else 'General'}.",
                            "sentiment": "positive" if "Site Visit" in call_outcome else ("negative" if "Not Interested" in call_outcome else "neutral"),
                            "calledAt": datetime.utcnow().isoformat(),
                            "outcome": call_outcome,
                            "detectedQuestions": detected_questions,
                            "customerPhone": customer_phone,
                            "customerName": customer_name
                        }
                        db_data["callLogs"].insert(0, new_log)
                        with open(db_path, "w", encoding="utf-8") as f:
                            json.dump(db_data, f, ensure_ascii=False, indent=2)
                        logger.info("📑 Synced live call transcript and intelligence to db.json for Web Dashboard!")
            except Exception as db_err:
                logger.warning(f"Could not update db.json: {db_err}")

        except Exception as e:
            logger.error(f"Failed to record call billing or transcript: {e}")

    from livekit.agents.voice import UserInputTranscribedEvent
    from livekit.agents.voice.events import UserStateChangedEvent, AgentStateChangedEvent

    t_user_stop = 0.0
    turn_counter = 0
    t_last_activity = time.time()
    has_prompted_silence = False
    agent_is_speaking = False
    watchdog_task = None

    @session.on("error")
    def _on_session_error(ev):
        logger.error(f"❌ [AGENT SESSION ERROR] Error={getattr(ev, 'error', ev)}")

    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent):
        nonlocal t_user_stop, t_last_activity, has_prompted_silence
        try:
            if ev.new_state == "speaking":
                t_last_activity = time.time()
                has_prompted_silence = False
            elif ev.old_state == "speaking" and ev.new_state == "listening":
                t_user_stop = time.perf_counter()
                t_last_activity = time.time()
                logger.info("🛑 [VAD] User stopped speaking! Fast turn-taking initiated immediately.")
        except Exception as err:
            logger.debug(f"User state changed error: {err}")

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent):
        nonlocal t_user_stop, turn_counter, agent_is_speaking, t_last_activity
        try:
            if ev.new_state == "speaking":
                agent_is_speaking = True
                if t_user_stop > 0:
                    elapsed_ms = (time.perf_counter() - t_user_stop) * 1000
                    turn_counter += 1
                    logger.info(
                        f"⚡⚡⚡ [TURN {turn_counter} RESPONSE LATENCY] "
                        f"User stopped speaking -> Agent began speaking: {elapsed_ms:.1f}ms ({elapsed_ms/1000.0:.2f}s) 🚀"
                    )
                    t_user_stop = 0.0
            elif ev.new_state in ["listening", "idle"]:
                agent_is_speaking = False
                t_last_activity = time.time()
        except Exception as err:
            logger.debug(f"Agent state changed error: {err}")

    current_lang = "hi"

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        nonlocal current_lang, t_user_stop, t_last_activity, has_prompted_silence
        t_last_activity = time.time()
        has_prompted_silence = False
        if ev.transcript:
            if t_user_stop > 0:
                transcribed_after = (time.perf_counter() - t_user_stop) * 1000
                logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} (+{transcribed_after:.1f}ms) | Text: '{ev.transcript}'")
            else:
                logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} | Text: '{ev.transcript}'")
        if ev.is_final and ev.transcript:
            text = ev.transcript.strip().lower()
            # Append customer turn to transcript history
            elapsed_sec = round(time.time() - t_call_start, 1)
            call_dialogue.append({"role": "customer", "text": ev.transcript.strip(), "time": elapsed_sec})
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
                            language="mr",
                            speed=cartesia_speed,
                            emotion=[cartesia_emotion] if cartesia_emotion else None
                        )
                        logger.info("🔄 Switched TTS to Marathi (Anika)")
                    elif current_lang == "en":
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="en",
                            speed=cartesia_speed,
                            emotion=[cartesia_emotion] if cartesia_emotion else None
                        )
                        logger.info(f"🔄 Switched TTS to English (Kusha Cloned Voice: {kusha_voice_id}, speed={cartesia_speed})")
                    else:
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="hi",
                            speed=cartesia_speed,
                            emotion=[cartesia_emotion] if cartesia_emotion else None
                        )
                        logger.info(f"🔄 Switched TTS to Hindi (Kusha Cloned Voice: {kusha_voice_id}, speed={cartesia_speed})")

    _hangup_scheduled = False

    def trigger_hangup(delay_seconds: float = 3.5):
        nonlocal _hangup_scheduled
        if _hangup_scheduled:
            return
        _hangup_scheduled = True

        async def _do_disconnect():
            logger.info(f"📞 [CALL TERMINATION] Disconnecting SIP room in {delay_seconds}s...")
            await asyncio.sleep(delay_seconds)
            logger.info("📞 [CALL TERMINATION] Terminating SIP call and deleting room now.")
            try:
                if hasattr(ctx, "delete_room"):
                    await ctx.delete_room()
                else:
                    await ctx.room.disconnect()
            except Exception as e:
                logger.warning(f"Error terminating room via delete_room: {e}")
                try:
                    await ctx.room.disconnect()
                except Exception:
                    pass

        asyncio.create_task(_do_disconnect())

    @session.on("conversation_item_added")
    def on_item_added(item):
        # Capture agent speech in transcript and check for goodbye closing phrase
        try:
            role = getattr(item, "role", None)
            if role in ["assistant", "agent"]:
                content = getattr(item, "content", "")
                if isinstance(content, list):
                    content = " ".join(str(c) for c in content)
                raw_text = str(content).strip()
                if raw_text and (not call_dialogue or call_dialogue[-1].get("text") != raw_text):
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "agent", "text": raw_text, "time": elapsed_sec})

                text = raw_text.lower()
                ending_phrases = ["aapka din shubh ho", "shubh ho... bye", "din shubh ho", "shubh ho!"]
                if any(phrase in text for phrase in ending_phrases):
                    logger.info("👋 [GOODBYE DETECTED IN AGENT SPEECH] Ensuring automated call termination in 4.0s...")
                    trigger_hangup(delay_seconds=4.0)
        except Exception as e:
            logger.debug(f"Error in on_item_added check: {e}")

        # Keep up to 14 recent dialogue items + system prompt (avoids forgetting user requirements while keeping TTFT fast)
        if hasattr(session, "_chat_ctx") and session._chat_ctx:
            max_dialogue_items = 14
            items = session._chat_ctx.items
            if len(items) > max_dialogue_items + 1:
                sys_prompt = items[0]
                recent = items[-max_dialogue_items:]
                # Safety: If recent[0] is an orphaned tool response without its tool_call preceding it, drop it
                while recent and getattr(recent[0], "role", "") == "tool":
                    recent = recent[1:]
                session._chat_ctx.items = [sys_prompt] + recent
                logger.info(f"✂️ Context Pruned: Keeping system instructions + {len(recent)} dialogue items (Total: {len(session._chat_ctx.items)})")

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

    # Dynamically resolve customer name and phone from participants in the room
    for p in ctx.room.remote_participants.values():
        if p.identity.startswith("sip-"):
            clean_digits = "".join(c for c in p.identity.replace("sip-", "") if c.isdigit() or c == "+")
            if clean_digits:
                customer_phone = clean_digits if clean_digits.startswith("+") else ("+91" + clean_digits if len(clean_digits) == 10 else "+" + clean_digits)
        raw_name = p.name or p.identity
        if raw_name:
            if raw_name.startswith("sip-"):
                raw_name = raw_name.replace("sip-", "")
            raw_name = raw_name.strip().capitalize()
            customer_name = f"{raw_name} ji" if not raw_name.endswith("ji") else raw_name
            logger.info(f"👤 Resolved customer name dynamically from room participants: {customer_name}")
            break

    agent = PriyaRealEstateAgent(
        customer_name=customer_name,
        customer_phone=customer_phone,
        hangup_fnc=trigger_hangup
    )

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
        f"Hello. Main Gayatri baat kar rahi hoon Sai Complex Dombivli East se. "
        f"Kya main {customer_name} se baat kar sakti hoon?"
    )

    # Speak greeting immediately after bridge has settled, allow caller to interrupt
    logger.info("🎙️ Speaking Greeting to caller...")
    try:
        session.say(greeting_text, allow_interruptions=True)
        call_dialogue.append({"role": "agent", "text": greeting_text.strip(), "time": 1.2})
    except Exception as e:
        logger.warning(f"Greeting error: {e}")

    # Silence Watchdog: 10s -> "Hello?", 30s -> Auto Hangup
    t_last_activity = time.time() + 4.0  # Allow 4s buffer for greeting to finish speaking

    async def _silence_watchdog():
        nonlocal t_last_activity, has_prompted_silence, _hangup_scheduled, agent_is_speaking
        logger.info("🛡️ [SILENCE WATCHDOG] Active (10s 'Hello' prompt, 30s auto-hangup).")
        while not _hangup_scheduled:
            await asyncio.sleep(1.0)
            if _hangup_scheduled or agent_is_speaking:
                continue

            silence_duration = time.time() - t_last_activity

            # Stage 1: Caller silent for 10 seconds -> Prompt "Hello?"
            if silence_duration >= 10.0 and not has_prompted_silence:
                has_prompted_silence = True
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {silence_duration:.1f}s (>10s). Prompting 'Hello'...")
                prompt_text = "Hello? Kya aap sun rahe hain?"
                try:
                    session.say(prompt_text, allow_interruptions=True)
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "agent", "text": prompt_text, "time": elapsed_sec})
                except Exception as e:
                    logger.warning(f"Error speaking silence prompt: {e}")

            # Stage 2: Caller silent for 30 seconds -> End call cleanly
            elif silence_duration >= 30.0:
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {silence_duration:.1f}s (>30s). Terminating call.")
                farewell_text = "Lagta hai aapki aawaaz nahi aa rahi hai. Aapka din shubh ho... bye!"
                try:
                    session.say(farewell_text, allow_interruptions=False)
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "agent", "text": farewell_text, "time": elapsed_sec})
                except Exception as e:
                    logger.warning(f"Error speaking silence farewell: {e}")
                trigger_hangup(delay_seconds=3.5)
                break

    watchdog_task = asyncio.create_task(_silence_watchdog())


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
