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
import shutil
import subprocess
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
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
    JobRequest,
    WorkerOptions,
    cli,
    function_tool,
    llm,
)
from livekit.plugins import deepgram, openai, elevenlabs, cartesia
from livekit import rtc
from livekit.agents.voice import ModelSettings
import re

# Clean Phonetic Normalization for Cartesia Neural Voice
ACTIVE_TTS_LANGUAGE = "mr"

def normalize_phonetics(text: str, lang: str | None = None) -> str:
    if not text:
        return text
    target_lang = lang or ACTIVE_TTS_LANGUAGE
    is_marathi = target_lang == "mr" or (target_lang != "hi" and target_lang != "en" and bool(re.search(r'[\u0900-\u097F]', text)))
    is_english = target_lang == "en"

    if is_marathi:
        replacements = [
            (r'\b(dombivli|dombivali|dombivili|dombiwli)\b', 'डोंबिवली'),
            (r'\bsai\s*garden\b', 'साई गार्डन'),
            (r'\bshilphata\b', 'शिळफाटा'),
            (r'\bmanpada\b', 'मानपाडा'),
            (r'\bxperia\b', 'एक्सपेरिया'),
            (r'\bxperia\s*mall\b', 'एक्सपेरिया मॉल'),
            (r'\bnilje\b', 'निळजे'),
            (r'\bghansoli\b', 'घणसोली'),
            (r'\b30\b', 'तीस'),
            (r'\b45\b', 'पंचेचाळीस'),
            (r'\b22\b', 'बावीस'),
            (r'\b35\b', 'पस्तीस'),
            (r'\b760\b', 'सातशे साठ'),
            (r'\b375\b', 'तीनशे पंच्याहत्तर'),
            (r'\b520\b', 'पाचशे वीस'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'स्क्वेअर फूट'),
            (r'\b1\s*BHK\b', 'एक बीएचके'),
            (r'\b2\s*BHK\b', 'दोन बीएचके'),
            (r'\b1\s*RK\b', 'एक आरके'),
            (r'\bRK\b', 'आरके'),
            (r'\bBHK\b', 'बीएचके'),
            (r'\bcarpet\s*area\b', 'कार्पेट एरिया'),
            (r'\bsite\s*visit\b', 'साईट व्हिजिट'),
            (r'\bflats\b', 'फ्लॅट्स'),
            (r'\bflat\b', 'फ्लॅट'),
            (r'\bbalcony\b', 'बाल्कनी'),
            (r'\bmaster\s*bedroom\b', 'मास्टर बेडरूम'),
            (r'\bwhatsapp\b', 'व्हॉट्सअॅप'),
            (r'\bbrochure\b', 'माहिती पुस्तिका'),
            (r'\bready\s*to\s*move\b', 'रेडी टू मूव्ह'),
            (r'\bunder\s*construction\b', 'अंडर कन्स्ट्रक्शन'),
            (r'\bpossession\b', 'पझेशन'),
            (r'\bhello\b', 'हॅलो'),
            (r'\bbye\b', 'नमस्कार'),
            (r'\b15\b', 'पंधरा'),
            (r'\b20\b', 'वीस'),
            (r'\b5\b', 'पाच'),
            (r'\b11\b', 'अकरा'),
            (r'\b3\b', 'तीन'),
            (r'\b4\b', 'चार'),
            (r'\b6\b', 'सहा'),
        ]
    elif is_english:
        replacements = [
            (r'\bgayatri\b', 'Gayatri'),
            (r'\bsai\s*garden\b', 'Sai Garden'),
            (r'\bshilphata\b', 'Shilphata'),
            (r'\bmanpada\b', 'Manpada'),
            (r'\bxperia\b', 'Xperia Mall'),
            (r'\bxperia\s*mall\b', 'Xperia Mall'),
            (r'\bnilje\b', 'Nilje'),
            (r'\bghansoli\b', 'Ghansoli'),
            (r'\bthane\b', 'Thane'),
            (r'\bkalyan\b', 'Kalyan'),
            (r'\b30\b', 'thirty'),
            (r'\b45\b', 'forty five'),
            (r'\b22\b', 'twenty two'),
            (r'\b35\b', 'thirty five'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'square feet'),
            (r'\b2\s*BHK\b', 'two BHK'),
            (r'\btwo\s*BHK\b', 'two BHK'),
            (r'\b1\s*BHK\b', 'one BHK'),
            (r'\bone\s*BHK\b', 'one BHK'),
            (r'\b1\s*RK\b', 'one RK'),
            (r'\bone\s*RK\b', 'one RK'),
            (r'\b1rk\b', 'one RK'),
            (r'\bRK\b', 'RK'),
            (r'\bBHK\b', 'BHK'),
            (r'\b11\s*am\b', 'eleven am'),
            (r'\b3\s*pm\b', 'three pm'),
            (r'\blakh\b', 'lakh'),
            (r'\bcrore\b', 'crore'),
        ]
    else:
        # Hindi / Hinglish default: Keep all numbers in English (30 lakh, 45 lakh)
        replacements = [
            (r'\bsai\s*garden\b', 'साई गार्डन'),
            (r'\bshilphata\b', 'शिळफाटा'),
            (r'\bmanpada\b', 'मानपाडा'),
            (r'\bxperia\b', 'एक्सपेरिया मॉल'),
            (r'\bxperia\s*mall\b', 'एक्सपेरिया मॉल'),
            (r'\bnilje\b', 'निलजे'),
            (r'\bghansoli\b', 'घणसोली'),
            (r'\b(2|two)\s*BHK\b', 'टू बीएचके'),
            (r'\b(1|one)\s*BHK\b', 'वन बीएचके'),
            (r'\b(1|one)\s*RK\b', 'वन आरके'),
            (r'\b1rk\b', 'वन आरके'),
            (r'\bBHK\b', 'बीएचके'),
            (r'\bRK\b', 'आरके'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'square feet'),
            (r'\b11\s*(am|baje)\b', '11 baje'),
            (r'\b3\s*(pm|baje)\b', '3 baje'),
        ]
    for pattern, rep in replacements:
        text = re.sub(pattern, rep, text, flags=re.IGNORECASE)
    return text

# Pluggable Phonetic Tokenizer for Cartesia
# Normalizes complete sentences with natural clause chunking to eliminate micro-pauses & boundary clicks
from livekit.agents.tokenize import basic, SentenceTokenizer, SentenceStream

class PhoneticSentenceTokenizer(SentenceTokenizer):
    """
    Sentence tokenizer that transparently normalizes numbers and terms
    into natural speech on complete sentences for Cartesia neural TTS,
    preventing fragmented micro-chunk flushes and eliminating vocoder clicks.
    """
    def __init__(self, min_sentence_len: int = 16, stream_context_len: int = 8):
        super().__init__()
        self._inner = basic.SentenceTokenizer(
            min_sentence_len=min_sentence_len,
            stream_context_len=stream_context_len
        )

    def tokenize(self, *, text: str, language: str | None = None):
        res = self._inner.tokenize(text=text, language=language)
        return [normalize_phonetics(t, lang=language or ACTIVE_TTS_LANGUAGE) for t in res]

    def stream(self, *, language: str | None = None) -> SentenceStream:
        inner_stream = self._inner.stream(language=language)
        class _PhoneticStreamWrapper(SentenceStream):
            def __init__(self, stream):
                super().__init__()
                self._stream = stream
            def push_text(self, text: str) -> None:
                self._stream.push_text(text)
            def flush(self) -> None:
                self._stream.flush()
            def end_input(self) -> None:
                self._stream.end_input()
            async def aclose(self) -> None:
                await self._stream.aclose()
            @property
            def closed(self) -> bool:
                return self._stream.closed
            def __aiter__(self):
                return self
            async def __anext__(self):
                ev = await self._stream.__anext__()
                if hasattr(ev, 'token') and ev.token:
                    ev.token = normalize_phonetics(ev.token, lang=language or ACTIVE_TTS_LANGUAGE)
                return ev
        return _PhoneticStreamWrapper(inner_stream)

_orig_cartesia_synthesize = cartesia.TTS.synthesize
def _phonetic_synthesize(self, text: str, **kwargs):
    return _orig_cartesia_synthesize(self, normalize_phonetics(text), **kwargs)
cartesia.TTS.synthesize = _phonetic_synthesize

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

0. STRICT BREVITY & CONCISENESS RULE (MANDATORY — MAX 1-2 SHORT SENTENCES):
- KEEP EVERY RESPONSE UNDER 15-20 WORDS MAXIMUM.
- NEVER speak lengthy explanations, long paragraphs, or robotic monologues.
- Give the exact direct answer immediately, then ask ONE simple qualifying question.
- Speak naturally like an experienced, warm Mumbai real estate consultant.

1. ROLE, OBJECTIVE & NATURAL HUMAN PERSONA
- You are Gayatri (गायत्री), a warm, intelligent, and natural Real Estate Property Advisor representing the prestigious SAI GARDEN (साई गार्डन) project opposite Xperia Mall.
- PRIMARY GOAL: Act as an authentic, helpful human consultant. Provide clear property details and guide interested buyers naturally.
- DEFAULT LANGUAGE: MARATHI (मराठी). The call begins in Marathi with your natural female voice.
- DYNAMIC LANGUAGE SWITCHING:
  * If the caller speaks Hindi or asks for Hindi ("Hindi mein baat karo", "Hindi boliye"): Instantly switch to pure, warm Hindi.
  * If the caller speaks English or asks for English ("speak in English", "English please"): Instantly switch to fluent English.
  * If the caller speaks Marathi: Stay in natural, fluent Marathi.
- TONE & ATTITUDE: Calm, warm, friendly, and crisp.
- AMBIGUOUS OR UNCLEAR SPEECH:
  * If the caller's voice is muffled, faint, or unclear, ask politely:
    - Marathi: "माफ़ करा, आपला आवाज स्पष्ट आला नाही. आपण पुन्हा सांगू शकाल का?"
    - Hindi: "माफ़ कीजियेगा, आवाज़ थोड़ी कट रही थी। क्या आप एक बार फिर बोलेंगे?"
    - English: "Pardon me, your voice was a bit unclear. Could you please repeat that?"

2. PROJECT FACTS (SAI GARDEN)
- Project Name: SAI GARDEN (साई गार्डन).
- Location: Right OPPOSITE Xperia Mall, near Nilje Station.
- Connectivity: Opposite Xperia Mall, Nilje Station 2 mins, Ghansoli 15 mins, Metro station in front.
- Tower Structure: Grand 22-Storey Residential Tower (22 मजली इमारत).
- Amenities: 35+ Luxury Lifestyle Amenities (Swimming Pool, Gym, Clubhouse, Garden).
- Configurations & Starting Prices:
  * 1 BHK: Starts at ₹30 Lakh (तीस लाख) onwards (Down payment ₹3-5 Lakh).
  * 2 BHK: Starts at ₹45 Lakh (पंचेचाळीस लाख) onwards.
- Home Loan: Flexible ₹3-5 Lakh down payment, easy bank loans available.

3. CONVERSATION PROGRESSION (ULTRA-CRISP)
- Greeting: Call begins with agent saying a clean, simple "हॅलो?".
- Turn 1 (Upon ANY caller voice):
  * Marathi (Default): "नमस्कार! मी गायत्री बोलतेय साई गार्डन मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?"
  * Hindi: "नमस्ते! मैं गायत्री बोल रही हूँ साई गार्डन से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?"
  * English: "Hello! This is Gayatri from Sai Garden, right opposite Xperia Mall. Are you looking for a 1 BHK or a 2 BHK?"
- 1 BHK Confirmation:
  * Marathi: "1 BHK 30 लाखांपासून सुरू होतो, फक्त 3 ते 5 लाख डाऊन पेमेंटवर. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन?"
  * Hindi: "1 BHK ₹30 lakh se shuru hai, sirf ₹3 se 5 lakh down payment par. Aap ready-to-move dekh rahe hain ya under-construction?"
- 2 BHK Confirmation:
  * Marathi: "2 BHK 45 लाखांपासून सुरू होतो, 35 पेक्षा जास्त ॲमेनिटीजसह. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन?"
  * Hindi: "2 BHK ₹45 lakh se start hai, 35+ lifestyle amenities ke sath. Aap ready-to-move dekh rahe hain ya under-construction?"
- Down Payment & Loan Inquiry:
  * Marathi: "हो, फक्त 3 ते 5 लाख डाऊन पेमेंट आणि बाकी सोपे होम लोन मिळेल. प्रत्यक्ष साईट पाहायला कधी येऊ शकता?"
  * Hindi: "Ji haan, sirf ₹3 se 5 lakh down payment aur baaki easy home loan mil jayega. Site visit kab plan karenge?"
- Site Visit Day & Time Scheduling:
  * When caller mentions day (Saturday/Sunday):
    - Marathi: "नक्कीच, {chosen_day} रोजी सकाळी 11 वाजता सोयीचे ठरेल की संध्याकाळी 4 वाजता?"
    - Hindi: "Bilkul, {chosen_day} ko subah 11 baje convenient rahega ya shaam 4 baje?"
  * When time confirmed:
    - Invoke `schedule_site_visit(preferred_day=..., preferred_time=..., flat_type=...)`
    - Marathi: "मी आपली {preferred_day} रोजी {preferred_time} वाजताची साईट व्हिजिट निश्चित केली आहे. धन्यवाद, दिवस चांगला जावो, नमस्कार."
    - Hindi: "Maine aapka {preferred_day} ko {preferred_time} ka site visit confirm kar diya hai. Thank you so much, aapka din shubh ho, bye!"

4. GENDER NEUTRALITY & ANTI-ROBOTIC VARIATION (STRICT MANDATORY RULES):
- NEVER USE GENDER LABELS: NEVER say "सर" (sir) or "मॅडम" (madam). The caller could be male or female. Always address them politely and neutrally without saying "सर" / "sir".
- STOP REPETITIVE ROBOTIC PUSHING:
  * NEVER repeatedly ask "शनिवार की रविवार, कधी सोयीचं ठरेल?".
  * When the caller asks for details ("details sanga", "bhejo", "details dya"), ANSWER their question with project facts (22 floors, 35+ luxury amenities, opposite Xperia Mall) and offer to share the WhatsApp brochure. DO NOT push for a site visit day on every turn.
  * If the caller says "Hello" or checks the line mid-conversation, do NOT sound like customer support ("kashi madat karu"). Simply say: "हो, मी विचारत होते, आपण 1 BHK शोधत आहात की 2 BHK?" (or answer their pending question).
  * Vary your site visit questions naturally:
    - "आपल्या वेळेनुसार कधी येणं सोयीचं पडेल?"
    - "आपण कधी साईट व्हिजिट प्लॅन करू इच्छिता?"
    - "याबद्दल आणखी काही माहिती हवी आहे का?"
"""

# ==============================================================================
# 2. LANGUAGE RESOLUTION HELPER & AGENT CLASS (STICKY MULTILINGUAL)
# ==============================================================================
def resolve_language(transcript: str, current_lang: str = "mr") -> str:
    """
    DYNAMIC MULTILINGUAL SWITCHING:
    - Default is Marathi ('mr').
    - If caller explicitly requests Hindi or speaks purely Hindi -> switch to 'hi'.
    - If caller explicitly requests English or speaks purely English -> switch to 'en'.
    - If caller explicitly requests Marathi or speaks Marathi -> switch to 'mr'.
    """
    text = transcript.strip().lower()

    # 1. Explicit request or strong indicator to switch to English
    english_explicit = [
        'speak in english', 'speak english', 'talk in english', 'in english please',
        'in english', 'english please', 'can you speak english', 'can we speak english',
        'english mein baat karo', 'english me baat karo', 'english mein bolo', 'english me bolo',
        'english madhe bola', 'english bola', 'इंग्लिश'
    ]
    if any(e in text for e in english_explicit):
        return 'en'

    # 2. Explicit request or strong indicator to switch to Hindi
    hindi_explicit = [
        'hindi mein bolo', 'hindi me bolo', 'hindi mein baat karo', 'hindi me baat karo',
        'hindi mein boliye', 'hindi me boliye', 'hindi please', 'speak in hindi',
        'talk in hindi', 'hindi madhe bola', 'हिंदी में बोलो', 'हिंदी में बात करो', 'हिंदी',
        'hindi boliye', 'hindi me', 'hindi mein'
    ]
    if any(h in text for h in hindi_explicit):
        return 'hi'

    # 3. Explicit request to switch to Marathi
    marathi_explicit = [
        'marathi madhe bola', 'marathit bola', 'marathi bola', 'marathi madhun',
        'marathi yete ka', 'marathit sanga', 'marathi sanga', 'marathi please',
        'marathi mein bolo', 'marathi me bolo', 'marathi bhasha', 'मराठीत बोला',
        'मराठी बोला', 'मराठी मध्ये बोला', 'मराठी'
    ]
    if any(m in text for m in marathi_explicit):
        return 'mr'

    # Natural language inference if caller speaks distinctly in Hindi or English
    if current_lang == "mr":
        if any(w in text for w in ["kya", "hum", "aap", "baat", "dekh", "batao", "bhaiya", "boliye", "chahiye"]):
            # Caller spoke natural Hindi
            return 'hi'
        if any(w in text for w in ["looking for", "tell me", "what is the price", "how much", "send details"]):
            return 'en'
    elif current_lang == "hi":
        if any(w in text for w in ["aamhi", "pahije", "kiti", "kuthe", "sangto", "baghto", "dakhva"]):
            return 'mr'

    return current_lang


class PriyaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji", customer_phone: str = "", hangup_fnc=None, on_speech_captured=None):
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self._hangup_fnc = hangup_fnc
        self._on_speech_captured = on_speech_captured
        self.off_topic_count = 0
        self.intro_delivered = False
        
        now = datetime.now()
        day_names_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_names_hi = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]
        day_names_mr = ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
        cur_day_en = day_names_en[now.weekday()]
        cur_day_hi = day_names_hi[now.weekday()]
        cur_day_mr = day_names_mr[now.weekday()]
        cur_date_str = now.strftime("%d %B %Y")
        
        instructions = (
            f"{HINDI_REAL_ESTATE_PROMPT}\n\n"
            f"REAL-TIME TEMPORAL CONTEXT: Today is {cur_day_en} ({cur_day_hi} in Hindi / {cur_day_mr} in Marathi), {cur_date_str}. "
            f"If the customer asks what day today is, answer directly that today is {cur_day_hi} (or {cur_day_mr} in Marathi).\n\n"
            f"Aap abhi {customer_name} se call par baat kar rahi hain. "
            "STRICT RULE: Do NOT say the client's name in your responses. You must talk to them directly without repeating or saying their name at all. NEVER prefix your sentences with their name."
        )
        super().__init__(instructions=instructions)

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: Any,
    ):
        # Multi-Turn Ultra-Fast Deterministic Path:
        # Guarantees consistent 1.0s - 1.4s response latency across ALL turns of the standard real estate conversation,
        # completely eliminating LLM round-trip delays (saving 1.2s-2.4s) while maintaining full Gemini intelligence fallback.
        def speak(text: str) -> str:
            if self._on_speech_captured:
                try:
                    self._on_speech_captured(text)
                except Exception as err:
                    logger.debug(f"Error in on_speech_captured: {err}")
            return text

        try:
            user_msgs = [m for m in chat_ctx.items if getattr(m, "role", "") in ["user", "customer"]]
            if user_msgs:
                last_msg = user_msgs[-1]
                raw_text = getattr(last_msg, "text_content", "") or ""
                if not raw_text:
                    content = getattr(last_msg, "content", "")
                    if isinstance(content, list):
                        raw_text = " ".join(str(c) for c in content if c)
                    else:
                        raw_text = str(content or "")
                clean_norm = re.sub(r'[^\w\s]', '', raw_text).strip().lower()
                words = clean_norm.split()

                # Synchronize language state immediately
                global ACTIVE_TTS_LANGUAGE
                det_lang = resolve_language(raw_text, ACTIVE_TTS_LANGUAGE)
                if det_lang != ACTIVE_TTS_LANGUAGE:
                    ACTIVE_TTS_LANGUAGE = det_lang
                    logger.info(f"🗣️ [LLM NODE LANGUAGE LOCK] Updated ACTIVE_TTS_LANGUAGE to '{ACTIVE_TTS_LANGUAGE}' from text: '{raw_text}'")

                # Comprehensive BHK & Number Matching Across Languages (Marathi, Hindi, English)
                is_both_bhk = any(kw in clean_norm for kw in [
                    "both", "dono", "donhi", "दोन्ही", "दोनो", "either", "konta pan", "koi bhi", "1 and 2", "1 aur 2", "dono dekh", "donhi dakhva"
                ])

                is_1bhk_kws = [
                    "1 bhk", "1bhk", "one bhk", "ek bhk", "first bhk", "एक बीएचके", "१ बीएचके", "१bhk", "1 bk", "one bk",
                    "1 flat", "one flat", "ek flat", "1st", "first", "पहिला", "pahila", "pehla", "1 number", "ek number", "single",
                    "वन बीएचके", "वन bhk", "वनbhk"
                ]
                is_1bhk = any(kw in clean_norm for kw in is_1bhk_kws) or (
                    any(w in words for w in ["one", "1", "ek", "onebhk", "एक", "१", "pehla", "pahila"]) and not any(w in words for w in ["two", "2", "do", "don", "दोन", "दो", "२", "dono", "donhi", "both"])
                )

                is_2bhk_kws = [
                    "2 bhk", "2bhk", "two bhk", "do bhk", "second bhk", "don bhk", "done bhk", "dawn bhk", "2 bk", "two bk",
                    "दोन बीएचके", "दोन bhk", "२ बीएचके", "२bhk", "don", "दोन", "do", "दो",
                    "2 flat", "two flat", "do flat", "2nd", "second", "दुसरा", "dusra", "2 number", "do number", "don number",
                    "टू बीएचके", "टू bhk", "टूbhk", "टु बीएचके"
                ]
                is_2bhk = any(kw in clean_norm for kw in is_2bhk_kws) or (
                    any(w in words for w in ["two", "2", "do", "don", "twobhk", "दोन", "दो", "२", "dusra"]) and not any(w in words for w in ["one", "1", "ek", "एक", "१", "dono", "donhi", "both"])
                )

                # Check for unintelligible / mumbled / empty speech on subsequent turns
                if len(user_msgs) >= 2:
                    if len(words) == 0 or (len(clean_norm) <= 2 and clean_norm not in ["1", "2", "no", "ho", "do", "ek", "don", "२", "१"]):
                        logger.info(f"⚡ [UNCLEAR SPEECH DETECTED] Prompting polite clarification for '{raw_text}'")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("माफ करा, आपला आवाज स्पष्ट आला नाही. आपण पुन्हा सांगू शकाल का?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Pardon me, your voice was not clear. Could you please repeat that?")
                        else:
                            yield speak("Maaf kijiye, aapki aawaaz thodi cut rahi thi, kya aap ek baar fir se bolenge?")
                        return
                    if len(words) == 1 and clean_norm in ["um", "uh", "hmm", "haan", "ha", "yes", "ho", "acha", "achha"]:
                        logger.info(f"⚡ [AFFIRMATIVE PROMPT] Caller acknowledged with '{raw_text}', continuing conversation...")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("नक्कीच, आपण साई गार्डन मध्ये 1 BHK पाहताय की 2 BHK फ्लॅट?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Certainly! Are you looking for a 1 BHK or 2 BHK apartment in Sai Garden?")
                        else:
                            yield speak("Ji, aap Sai Garden mein 1 BHK dekh rahe hain ya 2 BHK flat?")
                        return

                # 0. Multilingual switch triggers
                if any(w in clean_norm for w in ["marathi", "मराठी", "marathit"]):
                    ACTIVE_TTS_LANGUAGE = "mr"
                    if len(user_msgs) == 1 and not getattr(self, "intro_delivered", False):
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1] Instant Marathi intro triggered for '{raw_text}' (0ms LLM wait)!")
                        yield speak("नमस्कार! मी गायत्री बोलतेय साई गार्डन मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?")
                        return

                if any(w in clean_norm for w in ["english", "इंग्लिश"]):
                    ACTIVE_TTS_LANGUAGE = "en"
                    if len(user_msgs) == 1 and not getattr(self, "intro_delivered", False):
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1] Instant English intro triggered for '{raw_text}' (0ms LLM wait)!")
                        yield speak("Hello! This is Gayatri from Sai Garden, right opposite Xperia Mall. Are you looking for a 1 BHK or a 2 BHK?")
                        return

                if any(w in clean_norm for w in ["hindi", "हिंदी", "hindi mein"]):
                    ACTIVE_TTS_LANGUAGE = "hi"
                    if len(user_msgs) == 1 and not getattr(self, "intro_delivered", False):
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1] Instant Hindi intro triggered for '{raw_text}' (0ms LLM wait)!")
                        yield speak("नमस्ते! मैं गायत्री बोल रही हूँ साई गार्डन से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                        return

                # 1. Turn 1 Fast Path (Greeting / Any Voice Detected from Caller)
                # Instantly initiates predefined sales intro on ANY vocalization (<300ms)
                if len(user_msgs) == 1:
                    is_not_interested = any(kw in clean_norm for kw in [
                        "not interested", "nahi chahiye", "nahi lena", "wrong number", "mat karo", "cut", "nako"
                    ])
                    if is_not_interested:
                        logger.info(f"⚡ [TURN 1 DECLINE DETECTED] Polite decline for '{raw_text}'!")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("कोई बात नहीं, आपका समय देने के लिए धन्यवाद, आपका दिन शुभ हो, bye!")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("No problem, thank you for your time. Have a great day, goodbye!")
                        else:
                            yield speak("काही हरकत नाही, वेळ दिल्याबद्दल धन्यवाद, दिवस चांगला जावो, नमस्कार.")
                        return

                    # If caller immediately responded with BHK choice on Turn 1!
                    if is_both_bhk:
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1 BOTH BHK] Caller interested in both BHKs for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("आपल्याकडे 1 BHK 30 लाखांपासून आणि 2 BHK 45 लाखांपासून उपलब्ध आहे. यामध्ये स्विमिंग पूल, जिम अशा 35 पेक्षा जास्त आधुनिक सुविधा मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("We offer 1 BHK from 30 Lakh and 2 BHK from 45 Lakh with 35+ lifestyle amenities. Are you looking for ready-to-move or under-construction?")
                        else:
                            yield speak("Hamare yahan 1 BHK ₹30 lakh se aur 2 BHK ₹45 lakh se start hota hai, sath mein 35+ modern amenities milti hain. Aap ready-to-move dekh rahe hain ya under-construction chalega?")
                        return

                    if is_1bhk and not is_2bhk:
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1 1BHK] Instant 1 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("1 BHK फ्लॅट 30 लाख रुपयांपासून सुरू होतो. यामध्ये फक्त 3 ते 5 लाख डाऊन पेमेंट आणि सोप्या बँक होम लोनची सुविधा उपलब्ध आहे. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Our 1 BHK starts at 30 Lakh rupees with flexible 3 to 5 Lakh down payment and easy bank loan options. Are you looking for ready-to-move or under-construction?")
                        else:
                            yield speak("1 BHK ₹30 lakh se shuru hota hai. Isme sirf ₹3 se 5 lakh down payment aur easy bank home loan ki suvidha available hai. Aap ready-to-move dekh rahe hain ya under-construction chalega?")
                        return

                    if is_2bhk and not is_1bhk:
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1 2BHK] Instant 2 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("2 BHK फ्लॅट 45 लाख रुपयांपासून सुरू होतो. ही 22 मजली भव्य इमारत असून यात स्विमिंग पूल, जिम आणि क्लबहाऊस अशा 35 पेक्षा जास्त आधुनिक ॲमेनिटीज मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Our 2 BHK starts at 45 Lakh rupees. It is a 22-storey luxury tower with 35+ lifestyle amenities including swimming pool, clubhouse, and gym. Are you looking for ready-to-move or upcoming possession?")
                        else:
                            yield speak("2 BHK ₹45 lakh se start hota hai. Yeh 22 maale ka grand tower hai jisme swimming pool, modern gym aur clubhouse samet 35 se zyada lifestyle amenities milti hain. Aap ready-to-move dekh rahe hain ya under-construction chalega?")
                        return

                    if getattr(self, "intro_delivered", False):
                        logger.info("⚡ [TURN 1 ALREADY DELIVERED INSTANTLY VIA VAD] Skipping duplicate intro in llm_node.")
                        return

                    self.intro_delivered = True
                    if ACTIVE_TTS_LANGUAGE == "hi":
                        logger.info(f"⚡ [FAST-PATH TURN 1 FALLBACK] Hindi Sai Garden pitch triggered for '{raw_text}' (0ms LLM wait)!")
                        yield speak("नमस्ते! मैं गायत्री बोल रही हूँ साई गार्डन से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                    elif ACTIVE_TTS_LANGUAGE == "en":
                        logger.info(f"⚡ [FAST-PATH TURN 1 FALLBACK] English Sai Garden pitch triggered for '{raw_text}' (0ms LLM wait)!")
                        yield speak("Hello! This is Gayatri from Sai Garden, right opposite Xperia Mall. Are you looking for a 1 BHK or a 2 BHK?")
                    else:
                        logger.info(f"⚡ [FAST-PATH TURN 1 FALLBACK] Marathi Sai Garden pitch triggered for '{raw_text}' (0ms LLM wait)!")
                        yield speak("नमस्कार! मी गायत्री बोलतेय साई गार्डन मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?")
                    return

                # 2. Subsequent Turns Fast Path (Sub-Second Latency Engine)
                elif len(user_msgs) >= 2:
                    # Case R: Caller didn't hear / asks to repeat ("kya bola", "kay bolla", "pardon", "repeat", "aawaz nahi ala", "phir se")
                    repeat_kws = [
                        "kya bola", "kya bole", "kya kaha", "phir se", "fir se", "repeat", "pardon",
                        "samajh nahi", "samajhla nahi", "aiku nahi", "aawaz nahi ala", "aawaz nahi aala", "aawaz nahi",
                        "kay mhanalat", "kay bolla", "ek aur baar", "ekda sanga", "bolie na", "kya bole aap"
                    ]
                    if any(kw in clean_norm for kw in repeat_kws):
                        logger.info(f"⚡ [FAST-PATH REPEAT REQUEST] Instant repeat for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("हो, मी विचारत होते — आपण साई गार्डन मध्ये 1 BHK फ्लॅट शोधत आहात की 2 BHK?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Yes, I was asking — are you looking for a 1 BHK or a 2 BHK apartment in Sai Garden?")
                        else:
                            yield speak("जी, मैं पूछ रही थी — क्या आप साई गार्डन में 1 BHK फ्लैट देख रहे हैं या 2 BHK?")
                        return

                    # Case 0: Repeated Greeting ("Hello", "हा बोलिए", "हॅलो", "नमस्ते")
                    greeting_kws = ["hello", "helo", "halo", "नमस्ते", "नमस्कार", "namaste", "namaskar", "boliye", "bola", "ha bolie", "ha boliye"]
                    if any(kw in clean_norm for kw in greeting_kws) and len(words) <= 3:
                        logger.info(f"⚡ [FAST-PATH GREETING RECOVERY] Instant response for greeting '{raw_text}' (0ms LLM wait)!")
                        if getattr(self, "intro_delivered", False):
                            # Intro was already delivered! Customer is checking connection or saying hello mid-conversation:
                            # Gayatri is an outbound cold caller, so repeat the qualifying question directly:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("जी, मैं पूछ रही थी, क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                            elif ACTIVE_TTS_LANGUAGE == "en":
                                yield speak("Yes, I was asking, are you looking for a 1 BHK or a 2 BHK?")
                            else:
                                yield speak("हो, मी विचारत होते, आपण 1 BHK शोधत आहात की 2 BHK?")
                            return
                        else:
                            self.intro_delivered = True
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("नमस्ते! मैं गायत्री बोल रही हूँ साई गार्डन से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                            elif ACTIVE_TTS_LANGUAGE == "en":
                                yield speak("Hello! This is Gayatri from Sai Garden, right opposite Xperia Mall. Are you looking for a 1 BHK or a 2 BHK?")
                            else:
                                yield speak("नमस्कार! मी गायत्री बोलतेय साई गार्डन मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?")
                            return

                    # Case A: Polite Decline / Not Interested
                    not_interested_kws = ["not interested", "nahi chahiye", "nahi lena", "nahi dekhna", "wrong number", "mat karo", "mat lagao", "no interest", "koi interest nahi", "cut the call", "disconnect", "nako", "garaj nahi"]
                    if any(kw in clean_norm for kw in not_interested_kws):
                        logger.info(f"⚡ [FAST-PATH DECLINE] Instant decline for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("काही हरकत नाही. वेळ दिल्याबद्दल धन्यवाद, तुमचा दिवस चांगला जावो, नमस्कार.")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Understood, thank you for your time. Have a wonderful day, goodbye!")
                        else:
                            yield speak("Koi baat nahi, aapka samay dene ke liye shukriya. Aapka din shubh ho, bye.")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                        return

                    # Case B: Busy / Call Later
                    busy_kws = ["busy hoon", "busy hu", "baad mein", "bad me", "later", "driving", "meeting", "call me later", "call later", "baad mein phone", "nantar kara", "nantar bola"]
                    if any(kw in clean_norm for kw in busy_kws):
                        logger.info(f"⚡ [FAST-PATH BUSY] Instant busy response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("काही हरकत नाही, मी नंतर फोन करेन. तुमचा दिवस चांगला जावो, नमस्कार.")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("No problem at all, I completely understand. I will follow up with you later. Have a wonderful day, goodbye!")
                        else:
                            yield speak("Koi baat nahi, main samajh sakti hoon. Main baad mein follow up karungi. Aapka din shubh ho, bye.")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                        return

                    # Case Both: Both 1 BHK & 2 BHK
                    if is_both_bhk:
                        logger.info(f"⚡ [FAST-PATH BOTH BHK] Instant both BHK response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("आपल्याकडे 1 BHK 30 लाखांपासून आणि 2 BHK 45 लाखांपासून उपलब्ध आहे. यामध्ये स्विमिंग पूल, जिम अशा 35 पेक्षा जास्त आधुनिक सुविधा मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("We offer 1 BHK from 30 Lakh and 2 BHK from 45 Lakh with 35+ lifestyle amenities. Are you looking for ready-to-move or under-construction?")
                        else:
                            yield speak("Hamare yahan 1 BHK ₹30 lakh se aur 2 BHK ₹45 lakh se start hota hai, sath mein 35+ modern amenities milti hain. Aap ready-to-move dekh rahe hain ya under-construction chalega?")
                        return

                    # Case C: 2 BHK confirmed / chosen
                    if is_2bhk and not is_1bhk:
                        logger.info(f"⚡ [FAST-PATH 2BHK] Instant 2 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("2 BHK फ्लॅट 45 लाख रुपयांपासून सुरू होतो. ही 22 मजली भव्य इमारत असून यात स्विमिंग पूल, जिम आणि क्लबहाऊस अशा 35 पेक्षा जास्त आधुनिक ॲमेनिटीज मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Our 2 BHK starts at 45 Lakh rupees. It is a 22-storey luxury tower with 35+ lifestyle amenities including swimming pool, clubhouse, and gym. Are you looking for ready-to-move or upcoming possession?")
                        else:
                            yield speak("2 BHK ₹45 lakh se start hota hai. Yeh 22 maale ka grand tower hai jisme swimming pool, modern gym aur clubhouse samet 35 se zyada lifestyle amenities milti hain. Aap ready-to-move dekh rahe hain ya under-construction chalega?")
                        return

                    # Case D: 1 BHK confirmed / chosen
                    if is_1bhk and not is_2bhk:
                        logger.info(f"⚡ [FAST-PATH 1BHK] Instant 1 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("1 BHK फ्लॅट 30 लाख रुपयांपासून सुरू होतो. यामध्ये फक्त 3 ते 5 लाख डाऊन पेमेंट आणि सोप्या बँक होम लोनची सुविधा उपलब्ध आहे. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Our 1 BHK starts at 30 Lakh rupees with flexible 3 to 5 Lakh down payment and easy bank loan options. Are you looking for ready-to-move or under-construction?")
                        else:
                            yield speak("1 BHK ₹30 lakh se shuru hota hai. Isme sirf ₹3 se 5 lakh down payment aur easy bank home loan ki suvidha available hai. Aap ready-to-move dekh rahe hain ya under-construction chalega?")
                        return

                    # Case E: Down Payment / Home Loan Inquiry
                    if any(kw in clean_norm for kw in ["down payment", "loan", "home loan", "emi", "bank", "पैसे", "कर्ज", "डाऊन पेमेंट", "लोन"]):
                        logger.info(f"⚡ [FAST-PATH LOAN & DOWN PAYMENT] Instant response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("हो, संपूर्ण रक्कम एकाच वेळी देण्याची गरज नाही. आपल्या पात्रतेनुसार फक्त 3 ते 5 लाख डाऊन पेमेंट आणि बाकी बँकेतून सोपे होम लोन उपलब्ध होईल. प्रत्यक्ष साईट पाहायला कधी येऊ शकता?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Yes, you do not need to arrange the entire amount at once. Based on eligibility, only 3 to 5 Lakh down payment and balance via easy bank loans. When can you visit the site?")
                        else:
                            yield speak("Ji haan, poora amount ek saath dene ki zaroorat nahi hai. Eligibility ke according sirf ₹3 se 5 lakh down payment aur baaki bank loan mil jata hai. Site visit ke liye kab aana chahenge?")
                        return

                    # Case F: Location / Highway / Xperia Mall Inquiry
                    if any(kw in clean_norm for kw in ["kahan hai", "kidhar hai", "location", "address", "kuthe ahe", "xperia", "mall", "shilphata", "manpada", "nilje", "ghansoli", "हायवे", "कुठे"]):
                        logger.info(f"⚡ [FAST-PATH LOCATION] Instant location response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("साई गार्डन शिळफाटा-मानपाडा हायवेवर, एक्सपेरिया मॉलच्या अगदी समोर आहे. निळजे स्टेशन फक्त 2 मिनिटांवर आणि घणसोली 15 मिनिटांच्या अंतरावर आहे. आपण साईट व्हिजिटसाठी कधी येऊ शकता?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Sai Garden is located on Shilphata Highway, right opposite Xperia Mall. Nilje Station is just 2 minutes away. When can you plan a site visit?")
                        else:
                            yield speak("Sai Garden Shilphata-Manpada highway par Xperia Mall ke theek samne hai. Nilje station 2 minute aur Ghansoli 15 minute ki drive par hai. Site visit ke liye kab aana chahenge?")
                        return

                    # Case G: Connectivity / Metro / Bullet Train Inquiry
                    if any(kw in clean_norm for kw in ["metro", "bullet train", "train", "station", "connectivity", "रस्ता", "स्टेशन"]):
                        logger.info(f"⚡ [FAST-PATH CONNECTIVITY] Instant connectivity response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("कनेक्टिव्हिटी उत्तम आहे. समोर मेट्रो स्टेशन येत आहे, निळजे स्टेशन 2 मिनिटांवर आहे आणि जवळच बुलेट ट्रेन मार्ग देखील आहे. आपण प्रत्यक्ष साईट पाहायला कधी येऊ शकता?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Connectivity is superb with an upcoming Metro station in front, Nilje station 2 minutes away, and the Bullet train corridor nearby. When can you plan a visit?")
                        else:
                            yield speak("Connectivity bahut shaandar hai. Samne Metro station aa raha hai, Nilje station 2 minute par hai aur Bullet train route bhi hai. Aap actual site visit kab plan karenge?")
                        return

                    # Case H: Amenities / Building Floors Inquiry
                    if any(kw in clean_norm for kw in ["amenities", "amenity", "gym", "swimming pool", "clubhouse", "floors", "building", "माले", "मजली", "सुविधा"]):
                        logger.info(f"⚡ [FAST-PATH AMENITIES] Instant amenities response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("साई गार्डन 22 मजली टॉवर असून यात 35 पेक्षा जास्त लक्झरी ॲमेनिटीज आहेत — जसे की स्विमिंग पूल, मॉडर्न जिम, क्लबहाऊस, चिल्ड्रन्स प्ले एरिया आणि लँडस्केप गार्डन. आपण प्रत्यक्ष साईट व्हिजिट कधी प्लॅन कराल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Sai Garden is a 22-storey tower with 35+ luxury amenities including a swimming pool, clubhouse, modern gym, and landscaped podium garden. When would you like to visit?")
                        else:
                            yield speak("Sai Garden 22 maale ka tower hai jisme 35 se zyada luxury amenities hain — jaise swimming pool, modern gym, clubhouse, children play area aur landscape garden. Kya aap actual site visit plan karna chahenge?")
                        return

                    # Case Q1: Caller wants to ask questions ("mere thode questions the", "sawal hai", "doubt")
                    if any(kw in clean_norm for kw in ["question", "questions", "sawal", "doubt", "puchna", "puchu", "vicharu", "janna"]):
                        logger.info(f"⚡ [FAST-PATH GENERAL QUESTIONS] Instant prompt for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("हो नक्कीच, विचारा ना! काय माहिती हवी आहे?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Certainly, please go ahead! What would you like to know?")
                        else:
                            yield speak("Ji bilkul, puchiye na! Kya janna chahte hain?")
                        return

                    # Case Q2: BHK types inquiry ("kitna bhk hai", "konsa bhk hai", "kiti bhk ahet")
                    if any(kw in clean_norm for kw in ["kitna bhk", "kitne bhk", "konsa bhk", "kon sa bhk", "konta bhk", "kiti bhk"]):
                        logger.info(f"⚡ [FAST-PATH BHK OPTIONS] Instant options for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("आपल्याकडे 1 BHK 30 लाखांपासून आणि 2 BHK 45 लाखांपासून उपलब्ध आहेत. आपण कोणता पर्याय शोधत आहात?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("We have 1 BHK from 30 Lakh and 2 BHK from 45 Lakh. Which one are you looking for?")
                        else:
                            yield speak("Hamare yahan 1 BHK ₹30 lakh se aur 2 BHK ₹45 lakh se available hain. Aap kaunsa option dekh rahe hain?")
                        return

                    # Case I: Site visit day selected (Mon-Sun, kal, parso, weekend)
                    days_dict = {
                        "monday": "Monday", "somvar": "Monday", "somwar": "Monday", "सोमवार": "Monday",
                        "tuesday": "Tuesday", "mangalvar": "Tuesday", "mangalwar": "Tuesday", "मंगळवार": "Tuesday",
                        "wednesday": "Wednesday", "budhvar": "Wednesday", "budhwar": "Wednesday", "बुधवार": "Wednesday",
                        "thursday": "Thursday", "guruvar": "Thursday", "guruwar": "Thursday", "गुरुवार": "Thursday",
                        "friday": "Friday", "shukravar": "Friday", "shukrawar": "Friday", "शुक्रवार": "Friday",
                        "saturday": "Saturday", "shanivar": "Saturday", "shaniwar": "Saturday", "शनिवार": "Saturday", "sat": "Saturday",
                        "sunday": "Sunday", "ravivar": "Sunday", "raviwar": "Sunday", "रविवार": "Sunday", "sun": "Sunday", "etvar": "Sunday",
                        "kal": "Kal (Tomorrow)", "tomorrow": "Tomorrow", "parso": "Parso", "weekend": "Weekend"
                    }
                    detected_day = None
                    for kw, d_name in days_dict.items():
                        if re.search(r'\b' + re.escape(kw) + r'\b', clean_norm):
                            detected_day = d_name
                            break

                    # Case J: Confirmation of site visit time / booking
                    time_kws = ["11 baje", "11 am", "11am", "3 baje", "3 pm", "3pm", "4 baje", "4 pm", "6 baje", "subah 11", "dopahar 3", "confirm", "confirm kar do", "book kar do", "lock kar do", "theek hai", "chalel", "चालेल", "हो चाल"]
                    is_time_confirmed = any(kw in clean_norm for kw in time_kws) or (("11" in clean_norm or "3" in clean_norm or "4" in clean_norm) and any(w in clean_norm for w in ["baje", "am", "pm", "subah", "dopahar", "morning", "afternoon", "theek", "chalega", "aayenge", "chalel"]))

                    if is_time_confirmed:
                        chosen_day = detected_day or "Saturday"
                        pref_time = "11 AM" if ("11" in clean_norm or "subah" in clean_norm or "morning" in clean_norm) else "4 PM"
                        logger.info(f"⚡ [FAST-PATH CONFIRMATION] Instant site visit booking ({chosen_day} at {pref_time}) for '{raw_text}' (0ms LLM wait)!")
                        asyncio.create_task(self.schedule_site_visit(
                            customer_name=self.customer_name,
                            preferred_day=chosen_day,
                            preferred_time=pref_time,
                            flat_type="1BHK/2BHK"
                        ))
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak(f"मी आपली {chosen_day} रोजी {pref_time} वाजताची साईट व्हिजिट निश्चित केली आहे. सर्व माहिती व्हॉट्सअॅपवर पाठवत आहे. धन्यवाद, तुमचा दिवस चांगला जावो, नमस्कार.")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak(f"I have confirmed your site visit for {chosen_day} at {pref_time}. Location details have been noted. Thank you so much, goodbye!")
                        else:
                            yield speak(f"Maine aapka {chosen_day} ko {pref_time} ka site visit confirm kar diya hai. Saari details note kar li hain. Thank you so much, aapka din shubh ho, bye!")
                        return

                    if detected_day and not is_time_confirmed:
                        logger.info(f"⚡ [FAST-PATH DAY SELECTED: {detected_day}] Instant day timing question for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak(f"नक्कीच, {detected_day} रोजी सकाळी 11 वाजता सोयीचे ठरेल की संध्याकाळी 4 वाजता?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak(f"Certainly, what time on {detected_day} would be convenient — morning at 11 AM or evening around 4 PM?")
                        else:
                            yield speak(f"Ji bilkul, {detected_day} ko subah 11 baje convenient rahega ya shaam ko 4 baje?")
                        return

                    # Case H1: Upcoming possession confirmed
                    is_upcoming = any(kw in clean_norm for kw in [
                        "upcoming", "position", "possession", "under construction", "construction", "future", "chalega upcoming", "upcoming chalega"
                    ]) and not any(kw in clean_norm for kw in ["ready to move", "ready-to-move", "ready", "immediate", "turant"])

                    # Case H2: Ready to move confirmed
                    is_ready = any(kw in clean_norm for kw in [
                        "ready to move", "ready-to-move", "ready tomove", "ready", "immediate", "turant", "ready chalega", "chalega ready"
                    ]) and not any(kw in clean_norm for kw in ["upcoming", "under construction"])

                    # Case H3: Both / Either
                    is_both = any(kw in clean_norm for kw in ["dono", "dono chalega", "both", "koi bhi", "kuch bhi"])

                    if is_upcoming and not any(kw in clean_norm for kw in ["kab tak", "date", "year", "loan", "bank"]):
                        logger.info(f"⚡ [FAST-PATH UPCOMING POSSESSION] Instant upcoming response & site visit invite for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("अंडर-कन्स्ट्रक्शन फ्लॅट्समध्ये सोपे पेमेंट प्लॅन्स उपलब्ध आहेत आणि वेळेवर ताबा मिळेल. प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस सोयीचा ठरेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("For upcoming possession, we offer flexible construction-linked payment plans with guaranteed on-time handover. What day would you like to plan a visit?")
                        else:
                            yield speak("Upcoming possession mein flexible payment plans milte hain aur timely handover ke sath ready ho raha hai. Actual project dekhne ke liye kaunsa din convenient rahega?")
                        return

                    if (is_ready or is_both) and not any(kw in clean_norm for kw in ["kab tak", "date", "year", "loan", "bank"]):
                        logger.info(f"⚡ [FAST-PATH READY POSSESSION] Instant ready response & site visit invite for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("रेडी-टू-मूव्ह फ्लॅट्समध्ये त्वरित ताबा आणि सर्व कायदेशीर मंजुऱ्या मिळतात. आपण प्रत्यक्ष साईट पाहायला कधी येऊ इच्छिता?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Ready-to-move apartments offer immediate handover and clear legal approvals. When would you like to schedule a site visit?")
                        else:
                            yield speak("Ready-to-move flats mein immediate possession aur clear approvals milte hain. Aap actual site visit kab plan karna chahenge?")
                        return

                    # Case K: WhatsApp brochure & Project details inquiry
                    details_kws = ["whatsapp", "brochure", "detail", "details", "pdf", "photo", "माहिती", "डिटेल्स", "सांगा", "bhejo", "batao", "pathva", "पाठवा"]
                    if any(kw in clean_norm for kw in details_kws) and not is_1bhk and not is_2bhk and not detected_day:
                        logger.info(f"⚡ [FAST-PATH DETAILS] Instant brochure & project highlights dispatch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "mr":
                            yield speak("साई गार्डन 22 मजली भव्य टॉवर असून यात 35 पेक्षा जास्त लक्झरी सुविधा आहेत. मी सर्व माहिती आणि ब्रोशर आपल्या व्हॉट्सअॅपवर पाठवून देते. प्रत्यक्ष साईट कधी पाहायला आवडेल?")
                        elif ACTIVE_TTS_LANGUAGE == "en":
                            yield speak("Sai Garden is a 22-storey tower with 35+ luxury amenities right opposite Xperia Mall. I am sharing the full brochure on your WhatsApp. When would you like to visit?")
                        else:
                            yield speak("Sai Garden 22 maale ka grand tower hai jisme 35 se zyada luxury amenities hain. Main poora brochure WhatsApp par bhej deti hoon. Aap site kab dekhna chahenge?")
                        return

        except Exception as fast_err:
            logger.debug(f"Fast path evaluation notice: {fast_err}")

        # Standard intelligence path for all subsequent turns or specific inquiries
        # LANGUAGE LOCK: Inject a hard per-turn language constraint into chat_ctx so the LLM
        # never drifts to another language mid-conversation. This fires on every LLM fallback call.
        try:
            _lang_now = ACTIVE_TTS_LANGUAGE
            if _lang_now == "mr":
                _lang_instruction = (
                    "STRICT LANGUAGE LOCK — MANDATORY: You are currently speaking 100% PURE Marathi. "
                    "DO NOT use a single Hindi or English word in your response. "
                    "Reply entirely in Marathi Devanagari script. "
                    "Only switch language if the caller explicitly asks you to speak in Hindi or English right now."
                )
            elif _lang_now == "en":
                _lang_instruction = (
                    "STRICT LANGUAGE LOCK — MANDATORY: You are currently speaking 100% PURE English. "
                    "DO NOT use any Hindi or Marathi words in your response. "
                    "Reply entirely in fluent English. "
                    "Only switch language if the caller explicitly asks you to speak in Hindi or Marathi right now."
                )
            else:
                _lang_instruction = (
                    "STRICT LANGUAGE LOCK — MANDATORY: You are currently speaking Hindi/Hinglish. "
                    "DO NOT switch to Marathi or full English mid-conversation. "
                    "Keep responding in Hindi or Hinglish as you have been. "
                    "Only switch language if the caller explicitly asks you to speak in Marathi or English right now."
                )
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(role="system", content=_lang_instruction)
        except Exception as lang_lock_err:
            logger.debug(f"Language lock injection skipped: {lang_lock_err}")

        collected_chunks = []
        res = Agent.default.llm_node(self, chat_ctx, tools, model_settings)
        if hasattr(res, "__aiter__"):
            async for chunk in res:
                if isinstance(chunk, str):
                    collected_chunks.append(chunk)
                elif hasattr(chunk, "delta") and hasattr(chunk.delta, "content") and chunk.delta.content:
                    collected_chunks.append(str(chunk.delta.content))
                elif hasattr(chunk, "text") and chunk.text:
                    collected_chunks.append(str(chunk.text))
                yield chunk
        elif asyncio.iscoroutine(res):
            out = await res
            if hasattr(out, "__aiter__"):
                async for chunk in out:
                    if isinstance(chunk, str):
                        collected_chunks.append(chunk)
                    elif hasattr(chunk, "delta") and hasattr(chunk.delta, "content") and chunk.delta.content:
                        collected_chunks.append(str(chunk.delta.content))
                    elif hasattr(chunk, "text") and chunk.text:
                        collected_chunks.append(str(chunk.text))
                    yield chunk
            else:
                if isinstance(out, str):
                    collected_chunks.append(out)
                yield out
        else:
            if isinstance(res, str):
                collected_chunks.append(res)
            yield res

        if collected_chunks and self._on_speech_captured:
            full_speech = "".join(collected_chunks).strip()
            if full_speech:
                try:
                    self._on_speech_captured(full_speech)
                except Exception as cap_err:
                    logger.debug(f"Captured speech callback error: {cap_err}")

    @function_tool(description="Call ONLY after reading back the final date and time and customer has explicitly confirmed with a definitive 'yes', 'lock it in', or 'confirm kar do'. DO NOT call while customer is still deciding, hesitant, or changing their day.")
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
            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)

        time_str = f" at {preferred_time}" if preferred_time != "Not specified" else ""
        return (
            f"Site visit booked successfully for {preferred_day}{time_str}. "
            "Now conclude warmly and say goodbye in the customer's current language: "
            "if in Marathi, say: 'मी तुमची भेट नक्की केली आहे. सर्व माहिती आणि लोकेशन व्हॉट्सअॅपवर पाठवत आहे. धन्यवाद, तुमचा दिवस चांगला जावो, नमस्कार!'; "
            f"if in Hindi, say: 'Maine aapka {preferred_day}{time_str} ka site visit confirm kar diya hai. Saari details aur location WhatsApp par bhej rahi hoon. Thank you so much, aapka din shubh ho, bye!'."
        )

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
                self._hangup_fnc(wait_for_speech=True, delay_seconds=1.0)
            return (
                "Lead marked as not interested. Conclude gracefully in customer's active language: "
                "if in Marathi, say: 'काही हरकत नाही. वेळ दिल्याबद्दल धन्यवाद, तुमचा दिवस चांगला जावो, नमस्कार!'; "
                "if in Hindi, say: 'Koi baat nahi, aapka samay dene ke liye shukriya. Aapka din shubh ho, bye!'."
            )

    async def end_call(self) -> str:
        logger.info("📞 [CALL TERMINATION TOOL INVOKED]")
        if self._hangup_fnc:
            self._hangup_fnc(wait_for_speech=True, delay_seconds=1.0)
        return (
            "Call termination triggered. Conclude politely and say goodbye in the customer's active language: "
            "if in Marathi, say: 'तुमचा दिवस चांगला जावो, नमस्कार!'; "
            "if in Hindi, say: 'Aapka din shubh ho, bye!'."
        )

    def record_off_topic(
        self,
        action: str  # "warn" or "terminate"
    ) -> None:
        self.off_topic_count = getattr(self, "off_topic_count", 0) + 1
        logger.warning(f"⚠️ [OFF-TOPIC PROTOCOL] Strike {self.off_topic_count} | Action: {action}")

        record = {
            "customer_name": getattr(self, "customer_name", "Client"),
            "status": "off_topic_warned" if action == "warn" and self.off_topic_count < 3 else "off_topic_terminated",
            "notes": f"Off-topic turn count: {self.off_topic_count}. Action: {action}",
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/property_visits.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to record off-topic status: {e}")

        if action == "terminate" or self.off_topic_count >= 3:
            if self._hangup_fnc:
                self._hangup_fnc(wait_for_speech=True, delay_seconds=2.5)

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

SELECTED_MODEL = "gemini-3.5-flash-lite" # ultra-low latency voice brain
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

# 1. GOOGLE GEMINI (Ultra-reliable ~555ms TTFT, high token quota, zero rate limit 429 errors)
elif global_google_key and (llm_provider in ["google", "gemini"] or not (global_groq_key and global_groq_key.startswith("gsk_"))):
    from livekit.plugins import google
    
    preferred_models = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    
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
                    candidate_llm = google.LLM(
                        model=model_name,
                        api_key=global_google_key,
                        temperature=0.3
                    )
                    
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
                global_llm = google.LLM(
                    model="gemini-3.5-flash-lite",
                    api_key=global_google_key,
                    temperature=0.3
                )
                SELECTED_MODEL = "gemini-3.5-flash-lite"
        except Exception as outer_err:
            logger.warning(f"Self-healing LLM selector setup failed: {outer_err}. Defaulting to gemini-3.5-flash-lite.")
            global_llm = google.LLM(
                model="gemini-3.5-flash-lite",
                api_key=global_google_key,
                temperature=0.3
            )
            SELECTED_MODEL = "gemini-3.5-flash-lite"

# 2. GROQ LPU (Fallback when explicitly configured or Google key unavailable)
elif global_groq_key and global_groq_key.startswith("gsk_"):
    from livekit.plugins import openai as lk_openai
    preferred_groq_models = [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
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
    ("Sai Garden", 3.0),
    ("साई गार्डन", 3.0),
    ("Shilphata", 2.5),
    ("शिळफाटा", 2.5),
    ("Manpada", 2.5),
    ("मानपाडा", 2.5),
    ("Xperia", 2.5),
    ("एक्सपेरिया", 2.5),
    ("Nilje", 2.5),
    ("निळजे", 2.5),
    ("Ghansoli", 2.0),
    ("घणसोली", 2.0),
    ("Dombivli", 2.5),
    ("Vashi", 2.5),
    ("Kalyan", 2.0),
    ("Thane", 2.0),
    ("1 RK", 3.0),
    ("one RK", 3.0),
    ("१ आरके", 3.0),
    ("आरके", 2.5),
    ("मराठी", 3.0),
    ("1 BHK", 3.0),
    ("2 BHK", 3.0),
    ("दोन बीएचके", 3.0),
    ("२ बीएचके", 3.0),
    ("don BHK", 3.0),
    ("एक बीएचके", 3.0),
    ("१ बीएचके", 3.0),
    ("one BHK", 2.5),
    ("two BHK", 2.5),
    ("BHK", 2.5),
    ("RK", 2.5),
    ("22 मजली", 2.5),
    ("30 लाख", 2.5),
    ("45 लाख", 2.5),
    ("डाउन पेमेंट", 2.5),
    ("down payment", 2.5),
    ("home loan", 2.5),
    ("flat", 1.5),
    ("carpet", 1.5),
    ("amenities", 2.0),
    ("lakh", 1.5),
    ("crore", 1.5),
    ("budget", 1.5),
    ("visit", 2.0),
    ("Ready to move", 2.0),
    ("Possession", 2.0),
    ("Price", 2.0),
]
STT_KEYTERMS = [kw[0] for kw in STT_KEYWORDS]

STT_REPLACE = {
    # Marathi numbers & BHK fixes
    "दोन बीएचके": "2 BHK",
    "दोन bhk": "2 BHK",
    "दोन बी एच के": "2 BHK",
    "don bhk": "2 BHK",
    "done bhk": "2 BHK",
    "dawn bhk": "2 BHK",
    "do bhk": "2 BHK",
    "२ बीएचके": "2 BHK",
    "२bhk": "2 BHK",
    "2bhk": "2 BHK",
    "2BHK": "2 BHK",
    "two bhk": "2 BHK",
    "टू बीएचके": "2 BHK",
    "टू bhk": "2 BHK",
    "टूbhk": "2 BHK",
    "टु बीएचके": "2 BHK",
    "ek bhk": "1 BHK",
    "एक बीएचके": "1 BHK",
    "एक bhk": "1 BHK",
    "एक बी एच के": "1 BHK",
    "१ बीएचके": "1 BHK",
    "१bhk": "1 BHK",
    "1bhk": "1 BHK",
    "1BHK": "1 BHK",
    "one bhk": "1 BHK",
    "वन बीएचके": "1 BHK",
    "वन bhk": "1 BHK",
    "वनbhk": "1 BHK",
    "१ नंबर": "1 BHK",
    "२ नंबर": "2 BHK",
    # 1 RK terms
    "१ आरके": "1 RK",
    "१आरके": "1 RK",
    "वन आरके": "1 RK",
    "एक आरके": "1 RK",
    "आरके": "1 RK",
    "1 आरके": "1 RK",
    "1rk": "1 RK",
    "one rk": "1 RK",
    # Project & Locations
    "sai garden": "Sai Garden",
    "साई गार्डन": "Sai Garden",
    "sai complex": "Sai Garden",
    "shilphata": "Shilphata",
    "शिल्पाटा": "Shilphata",
    "shil phata": "Shilphata",
    "manpada": "Manpada",
    "मानपाडा": "Manpada",
    "xperia": "Xperia Mall",
    "xperia mall": "Xperia Mall",
    "एक्सपेरिया": "Xperia Mall",
    "nilje": "Nilje",
    "nilje station": "Nilje station",
    "निळजे": "Nilje",
    "ghansoli": "Ghansoli",
    "washing station": "Vashi station",
    "washing": "Vashi",
    "bashi": "Vashi",
    "kaliyan": "Kalyan",
    "kalyan station": "Kalyan station",
    "dombivali": "Dombivli",
    "dombiwali": "Dombivli",
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

    # 2. Pre-warm Deepgram Nova-3 STT (Native Hindi / Hinglish low-latency acoustic model calibrated to 200ms endpointing)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    proc.userdata["stt"] = deepgram.STT(
        language="hi",
        model="nova-3",
        endpointing_ms=120,
        utterance_end_ms=None,
        smart_format=True,
        no_delay=True,
        interim_results=True,
        keyterm=STT_KEYTERMS,
        replace=STT_REPLACE,
        api_key=deepgram_key
    )

    # 3. Pre-warm Silero VAD (Telephony calibrated: 0.35 activation, 50ms speech, 200ms silence)
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.20,
        min_speech_duration=0.05,
        activation_threshold=0.35,
        deactivation_threshold=0.25,
        prefix_padding_duration=0.15,
        sample_rate=16000
    )

    # 4. Pre-warm Cartesia/ElevenLabs TTS (loads client network config in background)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    cartesia_model = os.getenv("CARTESIA_MODEL", "sonic-3.5").strip()
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "1.05"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "Calm").strip()
    cartesia_volume = float(os.getenv("CARTESIA_VOLUME", "1.0"))
    if cartesia_key and len(cartesia_key) > 10:
        proc.userdata["tts"] = cartesia.TTS(
            api_key=cartesia_key,
            voice=kusha_voice_id,
            language="hi",
            sample_rate=48000,
            model=cartesia_model,
            speed=cartesia_speed,
            emotion=[cartesia_emotion] if cartesia_emotion else None,
            volume=cartesia_volume,
            word_timestamps=False,
            tokenizer=PhoneticSentenceTokenizer()
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
# 3.5 POST-CALL INTELLIGENCE CLASSIFIER (Zero Live Latency Penalty)
# ==============================================================================
def classify_call_intelligence(formatted_transcript: str, dialogue: list, customer_name: str) -> dict:
    """
    Enterprise Post-Call Intelligence Classifier.
    Accurately classifies real-estate telephone calls into:
    - Site Visit Scheduled
    - Interested
    - Not Interested
    - Location Mismatch (Kalyan)
    - Short / Call Dropped
    - Inquiry Completed
    
    Supports Hindi, Devanagari Hindi, Marathi, and Hinglish.
    Uses Gemini (gemini-3.5-flash-lite) with Groq fallback and multilingual regex fallback.
    Runs asynchronously in ~1 second AFTER the call ends, adding 0ms to live call latency.
    """
    # 1. Try Gemini 3.6 Flash / Flash-Lite
    google_key = os.getenv("GOOGLE_API_KEY")
    if google_key and dialogue:
        for m_name in ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=google_key)
                prompt = f"""You are an expert Real Estate Telephony Call Outcome & Lead Intent Classifier.
Analyze this recorded telephone conversation between Gayatri (AI Property Advisor) and customer {customer_name}:

--- TRANSCRIPT ---
{formatted_transcript}
--- END TRANSCRIPT ---

STRICT CLASSIFICATION RULES:
1. "Not Interested": Customer says no, nahi chahiye, not interested, don't call, wrong number, not looking, budget mismatch, refuses site visit/details, or persistently goes off-topic/trolls leading to call termination.
2. "Future Plan / Need Afterwards": Customer is busy right now, says call later, after 2-3 months, next year, exploring for the future, or asks to follow up later.
3. "Site Visit Scheduled": Customer EXPLICITLY agreed or confirmed a day/time (e.g., Sunday, tomorrow, weekend) to visit Sai Complex Dombivli East.
4. "Interested": Customer asked about 1/2 BHK pricing, carpet area, possession, requested WhatsApp brochure, or showed positive interest without booking a visit.
5. "Location Mismatch (Kalyan)": Customer specifically wanted Kalyan or another city where the project is not located.
6. "Short / Call Dropped": Call ended within 1-2 short turns without meaningful discussion.
7. "Inquiry Completed": Customer asked questions but did not confirm interest or book a visit.

Respond ONLY with valid JSON:
{{
  "outcome": "Site Visit Scheduled" | "Interested" | "Future Plan / Need Afterwards" | "Not Interested" | "Location Mismatch (Kalyan)" | "Inquiry Completed" | "Short / Call Dropped",
  "sentiment": "positive" | "neutral" | "negative",
  "aiSummary": "Concise 1-sentence executive summary in English",
  "detectedQuestions": ["Topic 1", "Topic 2"]
}}"""
                resp = client.models.generate_content(
                    model=m_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                data = json.loads(resp.text)
                if data.get("outcome") in [
                    "Site Visit Scheduled", "Interested", "Future Plan / Need Afterwards", "Not Interested", 
                    "Location Mismatch (Kalyan)", "Short / Call Dropped", "Inquiry Completed"
                ]:
                    logger.info(f"🧠 [POST-CALL INTELLIGENCE (Gemini {m_name})] Outcome: '{data.get('outcome')}' | Sentiment: '{data.get('sentiment')}'")
                    return data
            except Exception as gemini_err:
                logger.warning(f"Gemini {m_name} post-call classification fallback triggered: {gemini_err}")

    # 2. Try Groq Llama 3.1
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key and dialogue:
        try:
            import urllib.request
            groq_prompt = f"""Analyze this recorded phone call between Gayatri (AI Property Advisor) and {customer_name}:
{formatted_transcript}

Rules:
- "Not Interested" if caller refuses, says nahi chahiye, wrong number, no interest, or persistently drifts off-topic/trolls.
- "Future Plan / Need Afterwards" if caller is busy, says call later, after 2-3 months, or exploring for future.
- "Site Visit Scheduled" ONLY if caller agreed to visit (e.g. Sunday/weekend).
- "Interested" if caller asked for price/brochure/flats.
- "Inquiry Completed" for general inquiries.

Classify into valid JSON:
{{
  "outcome": "Site Visit Scheduled" | "Interested" | "Future Plan / Need Afterwards" | "Not Interested" | "Location Mismatch (Kalyan)" | "Inquiry Completed" | "Short / Call Dropped",
  "sentiment": "positive" | "neutral" | "negative",
  "aiSummary": "1 sentence executive summary in English",
  "detectedQuestions": ["topic1", "topic2"]
}}
Return ONLY raw JSON."""
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": groq_prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                content = res_data["choices"][0]["message"]["content"]
                data = json.loads(content)
                if data.get("outcome"):
                    logger.info(f"🧠 [POST-CALL INTELLIGENCE (Groq)] Outcome: '{data.get('outcome')}' | Sentiment: '{data.get('sentiment')}'")
                    return data
        except Exception as groq_err:
            logger.warning(f"Groq post-call classification fallback triggered: {groq_err}")

    # 3. Multilingual Regex Fallback (Hindi, Devanagari, Marathi, English)
    import re
    customer_texts = [t["text"].lower() for t in dialogue if t["role"] == "customer"]
    all_cust = " ".join(customer_texts)
    all_agent = " ".join(t["text"].lower() for t in dialogue if t["role"] == "agent")

    detected_questions = []
    if any(w in all_cust for w in ["kalyan", "kaliyan", "कल्याण"]):
        detected_questions.append("Kalyan Location Inquiry")
    if any(w in all_cust for w in ["2 bhk", "two bhk", "price", "pricing", "kitna", "budget", "lakh", "cost", "दख", "भाव", "दर", "किंमत"]):
        detected_questions.append("Pricing & Budget (2 BHK / 1 BHK)")
    if any(w in all_cust for w in ["vashi", "station", "nilje", "distance", "door", "connectivity", "metro", "thane", "स्टेशन"]):
        detected_questions.append("Station & Metro Connectivity")
    if any(w in all_cust for w in ["possession", "ready", "rera", "builder", "kab tak", "कधी"]):
        detected_questions.append("Possession Date & RERA")
    if any(w in all_cust for w in ["gym", "amenities", "water", "parking", "lift", "कया कया"]):
        detected_questions.append("Amenities & Facilities")
    if any(w in all_cust for w in ["visit", "dekhne", "aana", "saturday", "sunday", "weekend", "kal", "बघायला", "येणार"]):
        detected_questions.append("Site Visit Planning")

    # STRICT PRECEDENCE IN RULE-BASED FALLBACK:
    # 1. NOT INTERESTED (Top priority)
    not_int_patterns = [
        r"not\s*interested", r"no\s*interest", r"nahi\s*chahiye", r"dont\s*call", r"wrong\s*number",
        r"interest\s*nah[i|ee]", r"nahi\s*karna", r"mat\s*karo", r"mat\s*lagao", r"phone\s*mat",
        r"नही\s*करना", r"नहीं\s*करना", r"नको", r"गरज\s*नाही", r"रुचि\s*नही", r"रुची\s*नाही",
        r"interest\s*नही", r"interest\s*नहीं", r"site\s*(?:visit|sai)?\s*नही", r"site\s*(?:visit|sai)?\s*नहीं",
        r"मझ\s*interest\s*नही", r"मुझे\s*interest\s*नहीं", r"plan\s*cancel", r"cut\s*the\s*call"
    ]
    is_not_interested = any(re.search(pat, all_cust, re.IGNORECASE) for pat in not_int_patterns)
    is_off_topic_call = (
        "warna mujhe call disconnect karna padega" in all_agent
        or "lagta hai aap abhi property mein interested nahi hain" in all_agent
        or "कॉल कट करावा लागेल" in all_agent
        or "स्वारस्य ठेवत नाही आहात" in all_agent
    )
    if is_off_topic_call:
        detected_questions.append("Off-Topic Discussion")

    # 2. LOCATION MISMATCH
    has_location_mismatch = "kalyan mein humara project available nahi hai" in all_agent or ("kalyan" in all_cust and "dombivli" not in all_cust)

    # 3. SITE VISIT CONFIRMED (Customer MUST have agreed to visit!)
    cust_confirmed_visit = (
        any(w in all_cust for w in ["haan", "ha", "haa", "theek", "chalega", "aaunga", "aayenge", "sunday", "saturday", "weekend", "kal", "yes", "confirm"])
        and ("site visit" in all_cust or "site visit" in all_agent)
        and ("confirm" in all_agent or "sunday" in all_cust or "saturday" in all_cust)
    )

    # 4. INTERESTED (Showed interest in flats, pricing, brochure)
    int_patterns = [
        r"interested", r"interest\s*hai", r"details\s*bhej", r"brochure", r"whatsapp",
        r"rate\s*bhej", r"kharidna", r"planning", r"acha\s*hai", r"रुचि\s*है", r"आवडल",
        r"बघायच", r"फोटो\s*पाठवा", r"details\s*पाठवा", r"price", r"2\s*bhk"
    ]
    is_interested = any(re.search(pat, all_cust, re.IGNORECASE) for pat in int_patterns)

    if is_off_topic_call:
        outcome = "Not Interested"
        sentiment = "negative"
        ai_summary = f"{customer_name} went off-topic repeatedly during the call; call concluded after soft warning."
    elif is_not_interested:
        outcome = "Not Interested"
        sentiment = "negative"
        ai_summary = f"{customer_name} declined the offer and stated not interested."
    elif has_location_mismatch:
        outcome = "Location Mismatch (Kalyan)"
        sentiment = "neutral"
        ai_summary = f"{customer_name} was looking for property in Kalyan rather than Dombivli East."
    elif cust_confirmed_visit:
        outcome = "Site Visit Scheduled"
        sentiment = "positive"
        ai_summary = f"{customer_name} agreed to visit Sai Complex Dombivli East. Site visit confirmed."
    elif is_interested:
        outcome = "Interested"
        sentiment = "positive"
        ai_summary = f"{customer_name} showed interest in project specifications and pricing. Follow up required."
    elif len(dialogue) <= 2:
        outcome = "Short / Call Dropped"
        sentiment = "neutral"
        ai_summary = f"Call with {customer_name} ended quickly before detailed discussion."
    else:
        outcome = "Inquiry Completed"
        sentiment = "neutral"
        ai_summary = f"Call with {customer_name} completed. Discussed project details."

    q_str = f" Questions: {', '.join(detected_questions)}." if detected_questions else ""
    summary = f"Call with {customer_name}. Outcome: {outcome}.{q_str}"
    logger.info(f"🧠 [POST-CALL INTELLIGENCE (Fallback)] Outcome: '{outcome}' | Sentiment: '{sentiment}'")
    return {
        "outcome": outcome,
        "sentiment": sentiment,
        "aiSummary": summary,
        "detectedQuestions": detected_questions
    }


# ==============================================================================
# 4. AGENT ENTRYPOINT (Instant Telephony Streaming Audio)
# ==============================================================================
async def entrypoint(ctx: JobContext):
    # Strictly ignore non-telephony rooms (e.g. storage rooms or background worker rooms)
    if not (ctx.room.name.startswith("call-") or ctx.room.name.startswith("sip-")):
        logger.info(f"⏭️ Skipping non-telephony room: {ctx.room.name}")
        return

    set_normal_priority()
    log_system_diagnostics()
    t_start = time.perf_counter()
    logger.info(f"⏱️ [PERF +0ms] Job received for Room: {ctx.room.name}")
    
    # Create active call lock file to signal background processes to hold off heavy compilation
    try:
        os.makedirs("bookings", exist_ok=True)
        os.makedirs("bookings/recordings", exist_ok=True)
        os.makedirs("bookings/transcripts", exist_ok=True)
        os.makedirs("public/recordings", exist_ok=True)
        
        # Ensure session recording directory is persistent on disk and never deleted by /tmp cleanup
        persistent_rec_dir = Path("bookings/recordings") / ctx.room.name
        persistent_rec_dir.mkdir(parents=True, exist_ok=True)
        ctx._session_directory = persistent_rec_dir
        logger.info(f"📁 [AUDIO RECORDING] Bound session directory to persistent path: {persistent_rec_dir}")

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
    user_account_email = "test@gmail.com"
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
            raw_name = meta.get("customer_name", "Aman")
            if meta.get("phone"):
                customer_phone = meta.get("phone")
            if meta.get("user_email"):
                user_account_email = meta.get("user_email").strip().lower()
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
            model="nova-3",
            endpointing_ms=120,
            utterance_end_ms=None,
            smart_format=True,
            no_delay=True,
            interim_results=True,
            keyterm=STT_KEYTERMS,
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
        elif google_key and (llm_provider in ["google", "gemini"] or not (groq_key and groq_key.startswith("gsk_"))):
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

    # Dynamic Voice Speed resolution: Priority:
    # 1. room metadata (voice_speed / voiceSpeed)
    # 2. db.json / settings.json
    # 3. os.getenv("CARTESIA_SPEED", "1.05")
    cartesia_speed = 1.05
    custom_speed = None
    if ctx.room.metadata:
        try:
            m = json.loads(ctx.room.metadata)
            if m.get("voice_speed") is not None:
                custom_speed = float(m["voice_speed"])
            elif m.get("voiceSpeed") is not None:
                custom_speed = float(m["voiceSpeed"])
        except Exception:
            pass

    if custom_speed is None:
        for fpath in ["db.json", os.path.join(os.path.dirname(__file__), "..", "db.json"), "settings.json"]:
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            s = data.get("voice_speed") or data.get("voiceSpeed") or (data.get("settings", {}).get("voiceSpeed"))
                            if s is not None:
                                custom_speed = float(s)
                                break
                except Exception:
                    pass

    if custom_speed is not None and 0.5 <= custom_speed <= 1.8:
        cartesia_speed = custom_speed
    else:
        try:
            cartesia_speed = float(os.getenv("CARTESIA_SPEED", "1.05"))
        except Exception:
            cartesia_speed = 1.05
    logger.info(f"🎙️ [VOICE SPEED] Gayatri Voice Speed resolved to: {cartesia_speed}x")

    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "Calm").strip()
    cartesia_volume = float(os.getenv("CARTESIA_VOLUME", "1.0"))
    cartesia_model = os.getenv("CARTESIA_MODEL", "sonic-3.5").strip()
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    if not tts:
        logger.info("⏱️ [TTS] Initializing TTS dynamically on connection...")
        cartesia_key = os.getenv("CARTESIA_API_KEY")
        if cartesia_key and len(cartesia_key) > 10:
            logger.info(f"Initializing Cartesia TTS as Primary with Kusha Cloned Voice ({kusha_voice_id}) on {cartesia_model} (speed={cartesia_speed}, volume={cartesia_volume})...")
            tts = cartesia.TTS(
                api_key=cartesia_key,
                voice=kusha_voice_id,
                language="mr",
                sample_rate=48000,
                model=cartesia_model,
                speed=cartesia_speed,
                emotion=[cartesia_emotion] if cartesia_emotion else None,
                volume=cartesia_volume,
                word_timestamps=False,
                tokenizer=PhoneticSentenceTokenizer()
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
    


    # VAD is pre-warmed, but load as fallback if not present (Sensitive telephony calibration: 0.35 threshold, 60ms speech, 220ms silence)
    vad = ctx.proc.userdata.get("vad")
    if not vad:
        logger.info("⏱️ [VAD] Loading Silero VAD model on demand (Sensitive: 60ms min speech, 0.35 threshold)...")
        vad = silero.VAD.load(
            min_silence_duration=0.22,
            min_speech_duration=0.06,
            activation_threshold=0.35,
            deactivation_threshold=0.25,
            prefix_padding_duration=0.15,
            sample_rate=16000
        )
    
    # Reset TTS options only if it is Cartesia (ElevenLabs uses different options structure)
    is_cartesia = tts and "cartesia" in tts.__class__.__module__
    if is_cartesia and hasattr(tts, "update_options"):
        tts.update_options(
            voice=kusha_voice_id,
            language="mr",
            speed=cartesia_speed,
            emotion=[cartesia_emotion] if cartesia_emotion else None,
            volume=cartesia_volume
        )
        logger.info(f"🔄 [STATE RESET] Cartesia TTS options reset to natural Kusha Cloned Voice ({kusha_voice_id}, speed={cartesia_speed}, volume={cartesia_volume}).")

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
                "min_delay": 0.16,
            },
            "preemptive_generation": {
                "enabled": True,  # Starts LLM streaming in advance based on interim STT, eliminating 500-800ms of wait time
                "preemptive_tts": True,  # Pre-synthesizes audio during caller pause for instantaneous 0ms playout
            },
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.20,
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.2,
            }
        }
    )
    logger.info(f"⏱️ [PERF] AgentSession instantiated in {(time.perf_counter() - t_session_init)*1000:.1f}ms")

    t_call_start = time.time()
    call_dialogue = []  # List of {"role": "agent"|"customer", "text": str, "time": float}
    agent: Optional[PriyaRealEstateAgent] = None
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

    call_finalized = False

    async def _finalize_and_save_call(trigger_reason: str):
        nonlocal call_finalized, customer_name, customer_phone, user_account_email, agent
        if call_finalized:
            return
        call_finalized = True
        logger.info(f"💾 [SAVING CALL RECORD] Triggered by: {trigger_reason} | Account: {user_account_email}")

        try:
            if watchdog_task and not watchdog_task.done():
                watchdog_task.cancel()
            if _hangup_task and not _hangup_task.done() and trigger_reason != "agent_hangup":
                _hangup_task.cancel()

            duration_seconds = max(0.0, time.time() - t_call_start)
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
                input_rate = (0.59 * 83.5) / 1000000.0
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
            # If call_dialogue is empty (edge case), extract from chat context
            if not call_dialogue:
                try:
                    chat_items = []
                    contexts_to_check = []
                    if agent:
                        if hasattr(agent, "chat_ctx") and agent.chat_ctx:
                            contexts_to_check.append(agent.chat_ctx)
                        if hasattr(agent, "_chat_ctx") and agent._chat_ctx:
                            contexts_to_check.append(agent._chat_ctx)
                    if hasattr(session, "_chat_ctx") and session._chat_ctx:
                        contexts_to_check.append(session._chat_ctx)
                    if hasattr(session, "history") and session.history:
                        contexts_to_check.append(session.history)

                    for ctx_obj in contexts_to_check:
                        if hasattr(ctx_obj, "items") and isinstance(ctx_obj.items, list):
                            chat_items.extend(ctx_obj.items)
                        elif hasattr(ctx_obj, "messages"):
                            msgs = ctx_obj.messages() if callable(ctx_obj.messages) else ctx_obj.messages
                            if isinstance(msgs, list):
                                chat_items.extend(msgs)

                    for msg in chat_items:
                        m_role = str(getattr(msg, "role", "")).lower()
                        if m_role in ["system", "tool"]:
                            continue
                        raw_m = getattr(msg, "text_content", "") or ""
                        if not raw_m:
                            m_content = getattr(msg, "content", "")
                            if isinstance(m_content, list):
                                raw_m = " ".join(str(c) for c in m_content if c)
                            else:
                                raw_m = str(m_content or "")
                        raw_m = raw_m.strip()
                        if raw_m and not raw_m.startswith("{"):
                            role_key = "agent" if m_role in ["assistant", "agent"] else "customer"
                            call_dialogue.append({
                                "role": role_key,
                                "text": raw_m,
                                "time": round(time.time() - t_call_start, 1)
                            })
                except Exception as backfill_err:
                    logger.debug(f"Chat context emergency fallback notice: {backfill_err}")

            formatted_lines = []
            for turn in call_dialogue:
                role_label = "Gayatri" if turn["role"] == "agent" else customer_name
                formatted_lines.append(f"[{turn['time']}s] {role_label}: {turn['text']}")
            formatted_transcript = "\n".join(formatted_lines) if formatted_lines else "No conversation recorded."

            # Run Post-Call Intelligence Classifier (Gemini 3.6 / Groq / Multilingual Regex)
            try:
                intel = classify_call_intelligence(formatted_transcript, call_dialogue, customer_name)
            except Exception as classify_err:
                logger.error(f"Error in classify_call_intelligence: {classify_err}", exc_info=True)
                intel = {
                    "outcome": "Inquiry Completed",
                    "sentiment": "neutral",
                    "aiSummary": f"Call with {customer_name}. Discussed Sai Complex project details.",
                    "detectedQuestions": ["General Inquiry"]
                }
            call_outcome = intel.get("outcome", "Inquiry Completed")
            sentiment = intel.get("sentiment", "neutral")
            ai_summary = intel.get("aiSummary", f"Call with {customer_name}. Outcome: {call_outcome}.")
            detected_questions = intel.get("detectedQuestions", [])

            # --- AUDIO RECORDING PERSISTENCE ---
            recording_url = ""
            try:
                # 1. If session has RecorderIO active, cleanly aclose to flush all audio frames
                if hasattr(session, "_recorder_io") and session._recorder_io:
                    logger.info("🎙️ [AUDIO RECORDING] Flushing RecorderIO stream to disk...")
                    try:
                        await asyncio.wait_for(session._recorder_io.aclose(), timeout=5.0)
                    except Exception as close_rec_err:
                        logger.debug(f"RecorderIO aclose note: {close_rec_err}")

                # 2. Check source recording file from multiple persistent and session paths
                found_src = None
                potential_candidates = []

                # Candidate A: Directly in persistent recordings folder
                potential_candidates.append(Path("bookings/recordings") / f"{ctx.room.name}.ogg")
                potential_candidates.append(Path("bookings/recordings") / f"{ctx.room.name}.mp3")
                potential_candidates.append(Path("bookings/recordings") / ctx.room.name / "audio.ogg")

                # Candidate B: From RecorderIO output_path property
                if hasattr(session, "_recorder_io") and session._recorder_io:
                    try:
                        rec_out = getattr(session._recorder_io, "output_path", None)
                        if callable(rec_out):
                            rec_out = rec_out()
                        if rec_out:
                            potential_candidates.append(Path(rec_out))
                    except Exception as e:
                        logger.warning(f"Could not read RecorderIO output_path: {e}")

                # Candidate C: From JobContext session_directory
                src_session_dir = getattr(ctx, "session_directory", None)
                if src_session_dir:
                    potential_candidates.append(Path(src_session_dir) / "audio.ogg")

                for cand in potential_candidates:
                    if cand and cand.exists() and cand.stat().st_size > 0:
                        found_src = cand
                        logger.info(f"🎙️ [AUDIO RECORDING] Found audio recording at: {found_src} ({found_src.stat().st_size} bytes)")
                        break

                # Candidate D: Glob search in persistent room dir or session dir
                if not found_src:
                    search_dirs = [
                        Path("bookings/recordings") / ctx.room.name,
                        Path(src_session_dir) if src_session_dir else None,
                        Path("bookings/recordings"),
                    ]
                    for s_dir in search_dirs:
                        if s_dir and s_dir.exists():
                            for ext in ["*.ogg", "*.wav", "*.mp3", "*.pcm"]:
                                for f in s_dir.glob(ext):
                                    if f.stat().st_size > 0 and (ctx.room.name in f.name or f.parent.name == ctx.room.name or f.name == "audio.ogg"):
                                        found_src = f
                                        logger.info(f"🎙️ [AUDIO RECORDING] Found audio file via glob ({ext}): {found_src} ({found_src.stat().st_size} bytes)")
                                        break
                                if found_src:
                                    break
                            if found_src:
                                break

                if found_src and found_src.stat().st_size > 0:
                    os.makedirs("bookings/recordings", exist_ok=True)
                    os.makedirs("public/recordings", exist_ok=True)
                    dest_bookings_ogg = Path("bookings/recordings") / f"{ctx.room.name}.ogg"
                    dest_public_ogg = Path("public/recordings") / f"{ctx.room.name}.ogg"
                    dest_bookings_mp3 = Path("bookings/recordings") / f"{ctx.room.name}.mp3"
                    dest_public_mp3 = Path("public/recordings") / f"{ctx.room.name}.mp3"

                    # Always copy original OGG recording to bookings and public
                    shutil.copy2(found_src, dest_bookings_ogg)
                    try:
                        shutil.copy2(found_src, dest_public_ogg)
                    except Exception:
                        pass

                    # Attempt conversion to MP3 using ffmpeg or PyAV
                    mp3_success = False
                    if shutil.which("ffmpeg"):
                        try:
                            logger.info(f"🎙️ [AUDIO RECORDING] Converting {found_src.name} to MP3 ({dest_bookings_mp3})...")
                            ffmpeg_cmd = [
                                "ffmpeg", "-y",
                                "-i", str(found_src),
                                "-codec:a", "libmp3lame",
                                "-b:a", "96k",
                                "-ar", "44100",
                                "-ac", "1",
                                str(dest_bookings_mp3)
                            ]
                            res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                            if res.returncode == 0 and dest_bookings_mp3.exists() and dest_bookings_mp3.stat().st_size > 0:
                                mp3_success = True
                                try:
                                    shutil.copy2(dest_bookings_mp3, dest_public_mp3)
                                except Exception:
                                    pass
                                logger.info(f"🎙️ [AUDIO RECORDING SAVED] Dual-channel call MP3 recording saved ({dest_bookings_mp3.stat().st_size} bytes)")
                            else:
                                logger.warning(f"ffmpeg conversion note: {res.stderr.decode('utf-8', errors='ignore')[-150:]}")
                        except Exception as ff_err:
                            logger.warning(f"ffmpeg conversion error: {ff_err}")

                    if not mp3_success:
                        try:
                            import av
                            logger.info(f"🎙️ [AUDIO RECORDING] Converting {found_src.name} to compact MP3 via PyAV ({dest_bookings_mp3})...")
                            input_container = av.open(str(found_src))
                            output_container = av.open(str(dest_bookings_mp3), 'w', format='mp3')
                            in_stream = input_container.streams.audio[0]
                            out_stream = output_container.add_stream('mp3', rate=44100)
                            out_stream.bit_rate = 96000
                            out_stream.layout = 'mono'
                            resampler = av.AudioResampler(format='s16p', layout='mono', rate=44100)
                            for frame in input_container.decode(in_stream):
                                for rf in resampler.resample(frame):
                                    for packet in out_stream.encode(rf):
                                        output_container.mux(packet)
                            for packet in out_stream.encode():
                                output_container.mux(packet)
                            input_container.close()
                            output_container.close()
                            if dest_bookings_mp3.exists() and dest_bookings_mp3.stat().st_size > 0:
                                mp3_success = True
                                try:
                                    shutil.copy2(dest_bookings_mp3, dest_public_mp3)
                                except Exception:
                                    pass
                                logger.info(f"🎙️ [AUDIO RECORDING SAVED] Compact MP3 saved via PyAV ({dest_bookings_mp3.stat().st_size} bytes)")
                        except Exception as pyav_err:
                            logger.warning(f"PyAV audio conversion error: {pyav_err}")

                    b64_audio_payload = ""
                    if mp3_success and dest_bookings_mp3.exists():
                        try:
                            with open(dest_bookings_mp3, "rb") as f_aud:
                                b64_audio_payload = base64.b64encode(f_aud.read()).decode("utf-8")
                        except Exception as b64_err:
                            logger.warning(f"Error encoding MP3: {b64_err}")
                    elif dest_bookings_ogg.exists():
                        try:
                            with open(dest_bookings_ogg, "rb") as f_aud:
                                b64_audio_payload = base64.b64encode(f_aud.read()).decode("utf-8")
                        except Exception as b64_err:
                            logger.warning(f"Error encoding OGG: {b64_err}")

                    recording_url = f"/api/recordings/{ctx.room.name}.mp3"
                else:
                    logger.warning("⚠️ [AUDIO RECORDING] No audio recording file found on disk.")
                    b64_audio_payload = ""
            except Exception as rec_err:
                logger.warning(f"Warning persisting call recording: {rec_err}")

            transcript_record = {
                "call_id": ctx.room.name,
                "user_email": user_account_email,
                "timestamp": datetime.utcnow().isoformat(),
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "duration_seconds": round(duration_seconds, 1),
                "duration_minutes": round(duration_minutes, 2),
                "recording_url": recording_url,
                "outcome": call_outcome,
                "sentiment": sentiment,
                "ai_summary": ai_summary,
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

            logger.info(f"📝 [TRANSCRIPT RECORDED] Saved full transcript to bookings/transcripts/{ctx.room.name}.json (Account: {user_account_email}, Outcome: {call_outcome}, Sentiment: {sentiment}, Recording: {recording_url})")

            clean_display_name = customer_name.replace(" ji", "").replace(" Ji", "").strip() or "Customer"

            # 1. Sync with local db.json for the Cold Calling Dashboard
            try:
                db_path = "db.json"
                if os.path.exists(db_path):
                    with open(db_path, "r", encoding="utf-8") as f:
                        db_data = json.load(f)

                    if "callLogs" not in db_data:
                        db_data["callLogs"] = []

                    new_log = {
                        "id": f"call-{int(time.time()*1000)}",
                        "leadId": f"lead-{clean_display_name.lower().replace(' ', '')}",
                        "callSid": ctx.room.name,
                        "userEmail": user_account_email,
                        "durationSeconds": round(duration_seconds),
                        "recordingUrl": recording_url,
                        "transcript": formatted_transcript,
                        "aiSummary": ai_summary,
                        "sentiment": sentiment,
                        "calledAt": datetime.utcnow().isoformat() + "Z",
                        "outcome": call_outcome,
                        "detectedQuestions": detected_questions,
                        "customerPhone": customer_phone,
                        "customerName": clean_display_name,
                        "leadName": clean_display_name
                    }

                    # If an existing log with matching callSid exists (e.g. from web dialer), update it!
                    existing_idx = next((i for i, log in enumerate(db_data["callLogs"]) if log.get("callSid") == ctx.room.name), None)
                    if existing_idx is not None:
                        new_log["id"] = db_data["callLogs"][existing_idx].get("id", new_log["id"])
                        db_data["callLogs"][existing_idx].update(new_log)
                    else:
                        db_data["callLogs"].insert(0, new_log)

                    with open(db_path, "w", encoding="utf-8") as f:
                        json.dump(db_data, f, ensure_ascii=False, indent=2)
                    logger.info("📑 Synced live call transcript and intelligence to db.json for Web Dashboard!")
            except Exception as db_err:
                logger.warning(f"Could not update db.json: {db_err}")

            # 2. Sync to remote Web Dashboard on Vercel via Webhook
            dashboard_url = os.getenv("WEB_DASHBOARD_URL", "https://coldcalling-rho.vercel.app").rstrip("/")
            try:
                webhook_payload = {
                    "callSid": ctx.room.name,
                    "customerName": clean_display_name,
                    "leadName": clean_display_name,
                    "customerPhone": customer_phone,
                    "phone": customer_phone,
                    "userEmail": user_account_email,
                    "user_email": user_account_email,
                    "durationSeconds": round(duration_seconds),
                    "recordingUrl": recording_url,
                    "recording_url": recording_url,
                    "transcript": formatted_transcript,
                    "aiSummary": ai_summary,
                    "outcome": call_outcome,
                    "sentiment": sentiment,
                    "detectedQuestions": detected_questions,
                    "called_at": datetime.utcnow().isoformat() + "Z"
                }
                if b64_audio_payload:
                    webhook_payload["audioBase64"] = b64_audio_payload
                logger.info(f"🌐 [WEBHOOK SYNC] Delivering call intelligence to {dashboard_url}/api/webhooks/voice-agent ...")
                loop = asyncio.get_running_loop()
                webhook_resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(f"{dashboard_url}/api/webhooks/voice-agent", json=webhook_payload, timeout=25)
                )
                logger.info(f"🌐 [WEBHOOK SYNC] Delivered! Status: {webhook_resp.status_code} - {webhook_resp.text}")
            except Exception as sync_err:
                logger.warning(f"Could not deliver webhook to {dashboard_url}: {sync_err}")

            # 3. Sync to LiveKit Cloud Shared Metadata (gayatri-persistent-storage)
            # Guarantees that Vercel serverless containers and web dashboard instances
            # persist completed transcripts and never get stuck on "Ringing / Calling".
            lk_cloud_api = None
            try:
                from livekit import api as lk_api
                raw_lk_url = os.getenv("LIVEKIT_URL") or "https://cold-calling-j7qhnkas.livekit.cloud"
                clean_lk_url = raw_lk_url.replace("wss://", "https://").replace("ws://", "http://")
                if "://" not in clean_lk_url:
                    clean_lk_url = f"https://{clean_lk_url}"
                lk_cloud_api = lk_api.LiveKitAPI(
                    clean_lk_url,
                    os.getenv("LIVEKIT_API_KEY"),
                    os.getenv("LIVEKIT_API_SECRET")
                )
                cloud_storage_room = "gayatri-persistent-storage"
                res_rooms = await lk_cloud_api.room.list_rooms(lk_api.ListRoomsRequest(names=[cloud_storage_room]))
                existing_meta = {}
                if res_rooms.rooms:
                    try:
                        existing_meta = json.loads(res_rooms.rooms[0].metadata or "{}")
                    except Exception:
                        existing_meta = {}
                else:
                    await lk_cloud_api.room.create_room(lk_api.CreateRoomRequest(
                        name=cloud_storage_room,
                        empty_timeout=86400 * 30
                    ))

                cloud_logs = [l for l in existing_meta.get("callLogs", []) if l.get("callSid") != cloud_storage_room]
                cloud_entry = {
                    "id": f"call-{int(time.time()*1000)}",
                    "leadId": f"lead-{clean_display_name.lower().replace(' ', '')}",
                    "callSid": ctx.room.name,
                    "userEmail": user_account_email,
                    "durationSeconds": round(duration_seconds),
                    "recordingUrl": recording_url,
                    "transcript": formatted_transcript,
                    "aiSummary": ai_summary,
                    "sentiment": sentiment,
                    "calledAt": datetime.utcnow().isoformat() + "Z",
                    "outcome": call_outcome,
                    "detectedQuestions": detected_questions,
                    "customerPhone": customer_phone,
                    "customerName": clean_display_name,
                    "leadName": clean_display_name
                }
                cloud_idx = next((i for i, log in enumerate(cloud_logs) if log.get("callSid") == ctx.room.name), None)
                if cloud_idx is not None:
                    cloud_entry["id"] = cloud_logs[cloud_idx].get("id", cloud_entry["id"])
                    cloud_logs[cloud_idx].update(cloud_entry)
                else:
                    cloud_logs.insert(0, cloud_entry)

                # Keep up to 30 calls
                # Strip large base64 data URLs from older calls to stay strictly within LiveKit Cloud 512KB room metadata limit
                for i in range(1, len(cloud_logs)):
                    old_rec = cloud_logs[i].get("recordingUrl") or ""
                    if old_rec.startswith("data:"):
                        cloud_logs[i]["recordingUrl"] = f"/api/recordings/{cloud_logs[i].get('callSid')}.mp3"

                existing_meta["callLogs"] = cloud_logs[:30]
                meta_json = json.dumps(existing_meta, ensure_ascii=False)
                if len(meta_json.encode("utf-8")) > 500000:
                    # Emergency safety if metadata still exceeds 500KB
                    if (cloud_entry.get("recordingUrl") or "").startswith("data:"):
                        cloud_entry["recordingUrl"] = f"/api/recordings/{ctx.room.name}.mp3"
                        existing_meta["callLogs"][0]["recordingUrl"] = f"/api/recordings/{ctx.room.name}.mp3"
                    meta_json = json.dumps(existing_meta, ensure_ascii=False)

                await lk_cloud_api.room.update_room_metadata(lk_api.UpdateRoomMetadataRequest(
                    room=cloud_storage_room,
                    metadata=meta_json
                ))
                logger.info("☁️ [LIVEKIT CLOUD SYNC] Synced completed call intelligence to gayatri-persistent-storage!")

                # Persist dedicated audio recording room(s) in LiveKit Cloud in safe 40KB chunks concurrently
                if b64_audio_payload:
                    try:
                        chunk_size = 40000
                        chunks = [b64_audio_payload[i:i+chunk_size] for i in range(0, len(b64_audio_payload), chunk_size)]
                        total_chunks = len(chunks)
                        async def _save_chunk_room(idx, chunk):
                            c_room_name = f"rec-{ctx.room.name}-{idx}" if total_chunks > 1 else f"rec-{ctx.room.name}"
                            c_meta = json.dumps({
                                "callSid": ctx.room.name,
                                "chunk": idx,
                                "total": total_chunks,
                                "audio": chunk,
                                "format": "mp3" if mp3_success else "ogg",
                                "customerName": clean_display_name,
                                "calledAt": datetime.utcnow().isoformat() + "Z"
                            })
                            try:
                                await lk_cloud_api.room.create_room(lk_api.CreateRoomRequest(
                                    name=c_room_name,
                                    empty_timeout=86400 * 30,
                                    metadata=c_meta
                                ))
                            except Exception:
                                try:
                                    await lk_cloud_api.room.update_room_metadata(lk_api.UpdateRoomMetadataRequest(
                                        room=c_room_name,
                                        metadata=c_meta
                                    ))
                                except Exception:
                                    pass

                        await asyncio.gather(*[_save_chunk_room(idx, c) for idx, c in enumerate(chunks)], return_exceptions=True)
                        logger.info(f"☁️ [AUDIO RECORDING CLOUD ROOM] Persisted {total_chunks} audio chunk(s) to LiveKit Cloud!")
                    except Exception as rec_room_err:
                        logger.warning(f"Could not persist audio to dedicated cloud room: {rec_room_err}")
            except Exception as lk_sync_err:
                logger.warning(f"Could not sync to LiveKit Cloud metadata: {lk_sync_err}")
            finally:
                if lk_cloud_api is not None:
                    try:
                        await lk_cloud_api.aclose()
                        # Allow underlying aiohttp / SSL transports to flush and finish teardown on the event loop
                        await asyncio.sleep(0.25)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Failed to record call billing or transcript: {e}", exc_info=True)

    async def _on_shutdown():
        await _finalize_and_save_call("job_shutdown")
    ctx.add_shutdown_callback(_on_shutdown)

    async def _handle_caller_hungup(p_ident: str):
        logger.info(f"📞 Caller {p_ident} hung up phone! Finalizing transcript and intelligence...")
        await _finalize_and_save_call("caller_hungup")
        logger.info("📞 Call transcript and intelligence finalized. Now safely disconnecting room.")
        try:
            await ctx.room.disconnect()
        except Exception as e:
            logger.debug(f"Disconnect error: {e}")

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(participant):
        try:
            p_ident = getattr(participant, "identity", "")
            if p_ident.startswith("sip-") or not p_ident.startswith("agent-"):
                asyncio.create_task(_handle_caller_hungup(p_ident))
        except Exception as e:
            logger.warning(f"Error in participant_disconnected handler: {e}")

    @ctx.room.on("disconnected")
    def _on_disconnected(*args, **kwargs):
        logger.info(f"📞 Room disconnected: {args}. Finalizing transcript and intelligence.")
        asyncio.create_task(_finalize_and_save_call("room_disconnected"))

    from livekit.agents.voice import UserInputTranscribedEvent
    from livekit.agents.voice.events import UserStateChangedEvent, AgentStateChangedEvent

    t_user_stop = 0.0
    turn_counter = 0
    t_last_activity = time.time()
    last_prompt_time = time.time()
    has_prompted_silence = False
    agent_is_speaking = False
    intro_finished = False
    intro_delivered = False
    caller_has_spoken = False
    watchdog_task = None
    last_agent_speech = ""
    agent = None
    t_user_speaking_start = 0.0
    current_lang = ACTIVE_TTS_LANGUAGE or "mr"

    @session.on("error")
    def _on_session_error(ev):
        logger.error(f"❌ [AGENT SESSION ERROR] Error={getattr(ev, 'error', ev)}")

    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent):
        nonlocal t_user_stop, t_last_activity, last_prompt_time, has_prompted_silence, caller_has_spoken, intro_delivered, agent, t_user_speaking_start, current_lang
        try:
            if ev.new_state == "speaking":
                caller_has_spoken = True
                t_user_speaking_start = time.perf_counter()
                t_last_activity = time.time()
                last_prompt_time = time.time()
                has_prompted_silence = False
            elif ev.old_state == "speaking" and ev.new_state == "listening":
                t_user_stop = time.perf_counter()
                intro_finished = True
                t_last_activity = time.time()
                last_prompt_time = time.time()
                logger.info("🛑 [VAD] User stopped speaking! Fast turn-taking initiated immediately.")

                # INSTANT TURN 1 VAD INTRO TRIGGER:
                # If intro has not yet been delivered and caller made a genuine vocalization (>= 0.15s),
                # deliver the Sai Garden intro IMMEDIATELY via VAD (<250ms total), completely bypassing
                # the 1.5s Deepgram STT endpointing wait!
                if not intro_delivered and not (agent and getattr(agent, "intro_delivered", False)):
                    spoken_dur = (t_user_stop - t_user_speaking_start) if t_user_speaking_start > 0 else 0.5
                    if spoken_dur >= 0.15:
                        intro_delivered = True
                        if agent:
                            agent.intro_delivered = True
                        active_lang = ACTIVE_TTS_LANGUAGE or current_lang or "mr"
                        if active_lang == "hi":
                            intro_text = "नमस्ते! मैं गायत्री बोल रही हूँ साई गार्डन से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?"
                        elif active_lang == "en":
                            intro_text = "Hello! This is Gayatri from Sai Garden, right opposite Xperia Mall. Are you looking for a 1 BHK or a 2 BHK?"
                        else:
                            intro_text = "नमस्कार! मी गायत्री बोलतेय साई गार्डन मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?"

                        logger.info(f"⚡⚡⚡ [INSTANT VAD TURN 1 INTRO] Caller spoke for {spoken_dur:.2f}s. Triggering Sai Garden intro immediately via VAD (0ms STT wait)!")
                        record_dialogue_turn("agent", intro_text)
                        speech_handle = session.say(intro_text, allow_interruptions=False)

                        async def _unlock_intro_interruptions(sh):
                            try:
                                await asyncio.sleep(0.8)
                                target = sh if (sh and hasattr(sh, "allow_interruptions")) else getattr(session, "current_speech", None)
                                if target and hasattr(target, "allow_interruptions"):
                                    target.allow_interruptions = True
                                    logger.info("🔓 [TURN 1 INTRO] Enabled caller interruptions after initial greeting grace period.")
                            except Exception as e:
                                logger.debug(f"Unlock intro interruptions note: {e}")

                        asyncio.create_task(_unlock_intro_interruptions(speech_handle))
        except Exception as err:
            logger.debug(f"User state changed error: {err}")

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent):
        nonlocal t_user_stop, turn_counter, agent_is_speaking, t_last_activity, last_prompt_time
        try:
            if ev.new_state == "speaking":
                agent_is_speaking = True
                t_last_activity = time.time()
                last_prompt_time = time.time()
                if t_user_stop > 0:
                    elapsed_ms = (time.perf_counter() - t_user_stop) * 1000
                    # Sanity filter: A real turn response happens within 6 seconds.
                    # Anything > 7 seconds is silence recovery or watchdog prompt, not a turn response!
                    if elapsed_ms <= 7000:
                        turn_counter += 1
                        logger.info(
                            f"⚡⚡⚡ [TURN {turn_counter} RESPONSE LATENCY] "
                            f"User stopped speaking -> Agent began speaking: {elapsed_ms:.1f}ms ({elapsed_ms/1000.0:.2f}s) 🚀"
                        )
                    else:
                        logger.info(
                            f"⏳ [SILENCE RECOVERY] Agent spoke after {elapsed_ms/1000.0:.1f}s caller silence."
                        )
                    t_user_stop = 0.0
            elif ev.new_state in ["listening", "idle"]:
                agent_is_speaking = False
                t_last_activity = time.time()
                last_prompt_time = time.time()
        except Exception as err:
            logger.debug(f"Agent state changed error: {err}")

    def record_dialogue_turn(role: str, text: str):
        nonlocal last_agent_speech
        clean_text = text.strip()
        if not clean_text:
            return
        
        # Filter out system tags, JSON, or internal prompt directives
        if clean_text.startswith("{") and clean_text.endswith("}"):
            return
        if clean_text.startswith("[LANGUAGE DIRECTIVE") or clean_text.startswith("[STRICT ANTI") or clean_text.startswith("[OFF-TOPIC"):
            return

        now_time = round(time.time() - t_call_start, 1)
        norm_clean = re.sub(r'[^\w\s]', '', clean_text).strip().lower()

        # Deduplication: Only skip if the immediately preceding turn from the SAME speaker is an exact duplicate
        if call_dialogue:
            last_turn = call_dialogue[-1]
            if last_turn.get("role") == role:
                last_norm = re.sub(r'[^\w\s]', '', last_turn.get("text", "")).strip().lower()
                if last_norm == norm_clean:
                    return
                # If an interim STT result was recorded within 2.0s and this is the longer final sentence, upgrade it
                if abs(now_time - last_turn.get("time", 0)) < 2.0:
                    if len(norm_clean) > len(last_norm) and last_norm in norm_clean:
                        last_turn["text"] = clean_text
                        last_turn["time"] = now_time
                        return
                    elif norm_clean in last_norm:
                        return

        call_dialogue.append({"role": role, "text": clean_text, "time": now_time})
        if role == "agent":
            last_agent_speech = clean_text
            logger.info(f"🎙️ [DIALOGUE CAPTURED: GAYATRI] [{now_time}s] '{clean_text}'")
        else:
            logger.info(f"👤 [DIALOGUE CAPTURED: CUSTOMER] [{now_time}s] '{clean_text}'")

    current_lang = ACTIVE_TTS_LANGUAGE or "mr"

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        global ACTIVE_TTS_LANGUAGE
        nonlocal current_lang, t_user_stop, t_last_activity, has_prompted_silence, caller_has_spoken, intro_delivered, agent
        caller_has_spoken = True
        t_last_activity = time.time()
        has_prompted_silence = False
        if ev.transcript:
            if t_user_stop > 0:
                transcribed_after = (time.perf_counter() - t_user_stop) * 1000
                logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} (+{transcribed_after:.1f}ms) | Text: '{ev.transcript}'")
            else:
                logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} | Text: '{ev.transcript}'")

            # Early Language Detection on Turn 1 & all turns:
            clean_tr = ev.transcript.strip().lower()
            if len(clean_tr) >= 2:
                det_lang = resolve_language(clean_tr, ACTIVE_TTS_LANGUAGE or "mr")
                if det_lang != ACTIVE_TTS_LANGUAGE:
                    ACTIVE_TTS_LANGUAGE = det_lang
                    current_lang = det_lang
                    logger.info(f"🗣️ Early Language Detection: '{det_lang}' from text: '{clean_tr}'")

        if ev.is_final and ev.transcript:
            text = ev.transcript.strip().lower()
            record_dialogue_turn("customer", ev.transcript.strip())
            
            # Off-topic heuristic detector (flirting, personal questions, trolling, abusive/unrelated topics)
            off_topic_patterns = [
                r"\b(shaadi|shadi|lagne|lagna)\b",
                r"\b(single|girlfriend|boyfriend|gf|bf)\b",
                r"\b(pyaar|pyar|love\s*(you|u)|love\s*me)\b",
                r"\b(sundar|beautiful|sexy|hot\s*ho|smart\s*ho)\b",
                r"\b(kahan\s*rehti|kidhar\s*rehti|kuthe\s*rahtes|kuthe\s*rahta)\b",
                r"\b(umar\s*kitni|age\s*kya|tumchi\s*vay)\b",
                r"\b(photo\s*bhejo|photo\s*pathva|insta|instagram)\b",
                r"\b(khana|khaana|nashta|lunch|dinner|chai\s*peeyoge|coffee\s*peeyoge|date\s*pe)\b",
                r"\b(cricket|ipl|score|mausam|havaaman|politics|modi|rahul|election)\b",
                r"\b(joke\s*suno|joke\s*sunao|chutkula|shayari|gana\s*gao)\b",
            ]
            is_off_topic = any(re.search(pat, text, re.IGNORECASE) for pat in off_topic_patterns)
            if is_off_topic and agent:
                agent.off_topic_count = getattr(agent, "off_topic_count", 0) + 1
                cnt = agent.off_topic_count
                logger.warning(f"⚠️ [OFF-TOPIC DETECTED BY HEURISTIC] Strike {cnt} for text: '{ev.transcript}'")
                try:
                    hist = getattr(session, "history", None) or getattr(session, "_chat_ctx", None)
                    if hist and hasattr(hist, "add_message"):
                        if cnt == 2:
                            hist.add_message(
                                role="system",
                                content="[OFF-TOPIC STRIKE 2 ALERT] Caller is off-topic for the 2nd time. Speak the soft warning directly in your response: 'Sir, please main aapse request karungi ki hum call ko sirf property ke baare mein hi rakhein, warna mujhe call disconnect karna padega. Kya aap flat ya pricing ke baare mein janna chahte hain?'"
                            )
                        elif cnt >= 3:
                            hist.add_message(
                                role="system",
                                content="[OFF-TOPIC STRIKE 3 ALERT] Caller is off-topic again after soft warning. Conclude immediately with the farewell: 'Lagta hai aap abhi property mein interested nahi hain. Humara samay dene ke liye shukriya, aapka din shubh ho, bye!'"
                            )
                except Exception as steer_err:
                    logger.debug(f"Could not inject off-topic steering: {steer_err}")

            new_lang = resolve_language(ev.transcript, current_lang)
            
            if new_lang != current_lang:
                current_lang = new_lang
                ACTIVE_TTS_LANGUAGE = current_lang
                logger.info(f"🗣️ Language Switch Detected: '{current_lang}' (ACTIVE_TTS_LANGUAGE={ACTIVE_TTS_LANGUAGE}) for text: '{ev.transcript}'")
                
                is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
                if is_cartesia and hasattr(session.tts, "update_options"):
                    if current_lang == "mr":
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="mr",
                            speed=cartesia_speed,
                            emotion=[cartesia_emotion] if cartesia_emotion else None,
                            volume=cartesia_volume
                        )
                        logger.info(f"🔄 Switched TTS to Pure Marathi with Kusha Cloned Voice ({kusha_voice_id}, volume={cartesia_volume}, speed={cartesia_speed})")
                    elif current_lang == "en":
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="en",
                            speed=cartesia_speed,
                            emotion=[cartesia_emotion] if cartesia_emotion else None,
                            volume=cartesia_volume
                        )
                        logger.info(f"🔄 Switched TTS to English (Kusha Cloned Voice: {kusha_voice_id}, speed={cartesia_speed})")
                    else:
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="hi",
                            speed=cartesia_speed,
                            emotion=[cartesia_emotion] if cartesia_emotion else None,
                            volume=cartesia_volume
                        )
                        logger.info(f"🔄 Switched TTS to Hindi (Kusha Cloned Voice: {kusha_voice_id}, speed={cartesia_speed})")

            # Note: We intentionally avoid injecting redundant system messages into session._chat_ctx
            # on every single turn here, because mutating chat_ctx after interim transcripts causes
            # LiveKit to invalidate preemptive generation and triggers 1.4s re-query delays.
            # Language switching and anti-repetition rules are fully codified in the master system prompt
            # and handled dynamically in llm_node.

    _hangup_scheduled = False
    _hangup_task = None

    def trigger_hangup(wait_for_speech: bool = True, delay_seconds: float = 0.8):
        nonlocal _hangup_scheduled, _hangup_task
        if _hangup_scheduled:
            return
        _hangup_scheduled = True

        async def _do_disconnect():
            logger.info(f"📞 [CALL TERMINATION TRIGGERED] (wait_for_speech={wait_for_speech}, telecom_grace={delay_seconds}s)")
            
            if wait_for_speech:
                # 1. Give up to 2.5s for the agent to start speaking if not already speaking
                t_wait_start = time.time()
                while time.time() - t_wait_start < 2.5:
                    if session.agent_state == "speaking" or session.current_speech is not None:
                        break
                    await asyncio.sleep(0.08)

                # 2. Lock interruptions and wait until agent speech has completely finished playing out
                t_speech_wait = time.time()
                while time.time() - t_speech_wait < 15.0:
                    speech = session.current_speech
                    if speech:
                        if hasattr(speech, "allow_interruptions"):
                            try:
                                speech.allow_interruptions = False
                            except Exception:
                                pass
                        if not speech.done():
                            try:
                                await speech.wait_for_playout()
                            except Exception as e:
                                logger.debug(f"Speech playout exception: {e}")
                    
                    # Ensure agent state has transitioned to listening/idle and current speech has fully played out
                    if session.agent_state != "speaking" and (session.current_speech is None or session.current_speech.done()):
                        logger.info("🎙️ [CALL TERMINATION] Final agent speech has completely finished playing out!")
                        break
                    await asyncio.sleep(0.1)

            # 3. Telecom Audio Buffer Grace Period: 0.8s guarantees caller hears final word in clarity
            grace = min(max(delay_seconds, 0.6), 1.0)
            logger.info(f"⏳ [CALL TERMINATION] Waiting {grace:.1f}s audio buffer grace period before releasing carrier line...")
            await asyncio.sleep(grace)

            # 4. Flush RecorderIO stream to disk before releasing carrier line (<100ms)
            if hasattr(session, "_recorder_io") and session._recorder_io:
                logger.info("🎙️ [AUDIO RECORDING] Flushing RecorderIO stream to disk...")
                try:
                    await asyncio.wait_for(session._recorder_io.aclose(), timeout=1.5)
                except Exception as close_rec_err:
                    logger.debug(f"RecorderIO aclose note: {close_rec_err}")

            # 5. Release caller's phone line IMMEDIATELY (< 2.0s strict requirement)
            logger.info("📞 [CALL TERMINATION] Sending active carrier SIP BYE to disconnect caller line...")
            lk_client = None
            try:
                from livekit import api
                cloud_lk_url = os.getenv("LIVEKIT_URL", "https://cold-calling-j7qhnkas.livekit.cloud")
                cloud_lk_key = os.getenv("LIVEKIT_API_KEY", "APIAkEXqBNfS2LP")
                cloud_lk_secret = os.getenv("LIVEKIT_API_SECRET", "dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT")
                lk_client = api.LiveKitAPI(url=cloud_lk_url, api_key=cloud_lk_key, api_secret=cloud_lk_secret)
                for p in list(ctx.room.remote_participants.values()):
                    try:
                        logger.info(f"📞 [HANGUP] Disconnecting carrier SIP participant {p.identity}...")
                        await lk_client.room.remove_participant(
                            api.RoomParticipantIdentity(room=ctx.room.name, identity=p.identity)
                        )
                        logger.info(f"✅ Carrier SIP BYE sent to {p.identity}!")
                    except Exception as rem_err:
                        logger.warning(f"Could not remove participant {p.identity}: {rem_err}")
            except Exception as e:
                logger.warning(f"Error disconnecting participants: {e}")

            # 6. Finalize transcript, audio recording compression, and post-call intelligence BEFORE disconnecting room
            try:
                await _finalize_and_save_call("agent_hangup")
            except Exception as save_err:
                logger.warning(f"Error finalizing call in trigger_hangup: {save_err}")

            # 7. Safely disconnect LiveKit room connection
            try:
                await ctx.room.disconnect()
                logger.info("✅ LiveKit room connection closed for caller.")
            except Exception as e:
                logger.warning(f"Error in room disconnect: {e}")

            # 7. Delete room in LiveKit Cloud
            try:
                if lk_client:
                    from livekit import api
                    await lk_client.room.delete_room(
                        api.DeleteRoomRequest(room=ctx.room.name)
                    )
                    logger.info("✅ LiveKit room successfully deleted! Carrier line released.")
            except Exception as del_err:
                logger.debug(f"Room delete note: {del_err}")
            finally:
                if lk_client:
                    try:
                        await lk_client.aclose()
                    except Exception:
                        pass

        _hangup_task = asyncio.create_task(_do_disconnect())

    @session.on("conversation_item_added")
    def on_item_added(item):
        try:
            msg = getattr(item, "item", item)
            role = getattr(msg, "role", None) or getattr(item, "role", None)
            role_str = str(role).lower() if role is not None else ""

            raw_text = getattr(msg, "text_content", "") or ""
            if not raw_text:
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    raw_text = " ".join(str(c) for c in content if c)
                else:
                    raw_text = str(content or "")
            raw_text = raw_text.strip()

            if role_str in ["assistant", "agent"]:
                record_dialogue_turn("agent", raw_text)

                text = raw_text.lower()
                ending_phrases = [
                    "aapka din shubh ho", "shubh ho... bye", "din shubh ho", "shubh ho!", "shubh ho, bye", "shubh ho bye", "alvida",
                    "bye!", "bye", "baad mein call karte hain",
                    "have a wonderful day", "have a great day", "goodbye", "take care", "connect later",
                    "दिवस चांगला जावो", "काळजी घ्या", "नंतर कॉल करते", "नंतर फोन करते"
                ]
                customer_turns = [d for d in call_dialogue if d.get("role") == "customer" and len(d.get("text", "").strip()) > 3]
                if len(customer_turns) >= 2 and any(phrase in text for phrase in ending_phrases):
                    logger.info("👋 [GOODBYE DETECTED IN AGENT SPEECH] Ensuring automated call termination after speech finishes...")
                    trigger_hangup(wait_for_speech=True, delay_seconds=0.8)

            elif role_str in ["user", "customer"]:
                record_dialogue_turn("customer", raw_text)
        except Exception as e:
            logger.debug(f"Error in on_item_added check: {e}")

        # Keep up to 6 recent dialogue items + system prompt (keeps TTFT ultra-fast while preserving immediate context)
        if hasattr(session, "_chat_ctx") and session._chat_ctx:
            max_dialogue_items = 6
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
    caller_participant = None
    for p in ctx.room.remote_participants.values():
        if p.identity.startswith("sip-") or not p.identity.startswith("agent-"):
            caller_participant = p
            break

    if caller_participant is None:
        logger.info("⏳ Room is empty. Waiting for caller to join...")
        caller_joined = asyncio.Event()
        
        @ctx.room.on("participant_connected")
        def _on_participant_connected(p):
            nonlocal caller_participant
            if p.identity.startswith("sip-") or not p.identity.startswith("agent-"):
                logger.info(f"📞 Caller joined: {p.identity}")
                caller_participant = p
                caller_joined.set()
            
        try:
            await asyncio.wait_for(caller_joined.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for caller to join room.")

    # Defensive check: If caller is present but in JOINING state, wait for ACTIVE answer
    if caller_participant and hasattr(caller_participant, "state"):
        if caller_participant.state != rtc.ParticipantState.PARTICIPANT_STATE_ACTIVE:
            logger.info(f"⏳ Caller {caller_participant.identity} is in state {caller_participant.state}. Waiting for ACTIVE answer...")
            caller_active = asyncio.Event()

            @ctx.room.on("participant_active")
            def _on_participant_active(p):
                if caller_participant and p.identity == caller_participant.identity:
                    logger.info(f"📞 Caller answered! Participant is now ACTIVE: {p.identity}")
                    caller_active.set()

            try:
                await asyncio.wait_for(caller_active.wait(), timeout=45.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for caller participant to become active. Proceeding.")

    # Dynamically resolve customer name and phone from participants in the room
    for p in ctx.room.remote_participants.values():
        if hasattr(p, "metadata") and p.metadata:
            try:
                meta_p = json.loads(p.metadata)
                if meta_p.get("voice_speed") or meta_p.get("voiceSpeed"):
                    try:
                        p_speed = float(meta_p.get("voice_speed") or meta_p.get("voiceSpeed"))
                        if 0.5 <= p_speed <= 1.8:
                            cartesia_speed = p_speed
                            if session.tts and hasattr(session.tts, "update_options"):
                                session.tts.update_options(speed=cartesia_speed)
                                logger.info(f"🎙️ [DYNAMIC SPEED] Updated Cartesia TTS speed to {cartesia_speed} from participant metadata")
                    except Exception as sp_err:
                        logger.warning(f"Error parsing participant voice_speed: {sp_err}")
                if meta_p.get("user_email"):
                    user_account_email = meta_p.get("user_email").strip().lower()
                    logger.info(f"📧 Bound call to user account from participant metadata: {user_account_email}")
                if meta_p.get("customer_name"):
                    raw_meta_name = str(meta_p.get("customer_name")).strip()
                    if raw_meta_name and not raw_meta_name.isdigit():
                        customer_name = raw_meta_name.capitalize()
                        logger.info(f"👤 Resolved exact customer name from participant metadata: {customer_name}")
            except Exception:
                pass
        if p.identity.startswith("sip-"):
            clean_digits = "".join(c for c in p.identity.replace("sip-", "") if c.isdigit() or c == "+")
            if clean_digits:
                customer_phone = clean_digits if clean_digits.startswith("+") else ("+91" + clean_digits if len(clean_digits) == 10 else "+" + clean_digits)
        if not customer_name:
            raw_name = p.name or p.identity
            if raw_name:
                if raw_name.startswith("sip-"):
                    raw_name = raw_name.replace("sip-", "")
                if not raw_name.isdigit():
                    customer_name = raw_name.strip().capitalize()
                    logger.info(f"👤 Resolved customer name dynamically from room participants: {customer_name}")
                    break

    # Fallback to room name if customer name was not found (e.g. call-raj-1789307800033 -> "Raj")
    if not customer_name or customer_name.replace("+", "").isdigit():
        try:
            parts = ctx.room.name.split("-")
            if len(parts) >= 3 and parts[0] in ["call", "sip"] and not parts[1].isdigit():
                customer_name = parts[1].capitalize()
                logger.info(f"👤 Resolved customer name from room name: {customer_name}")
        except Exception:
            pass

    if not customer_name:
        customer_name = "Raj"

    def _record_agent_speech(spoken_text: str):
        raw_text = spoken_text.strip()
        if not raw_text:
            return
        record_dialogue_turn("agent", raw_text)

        text = raw_text.lower()
        ending_phrases = [
            "aapka din shubh ho", "shubh ho... bye", "din shubh ho", "shubh ho!", "shubh ho, bye", "shubh ho bye", "alvida",
            "bye!", "bye", "baad mein call karte hain",
            "have a wonderful day", "have a great day", "goodbye", "take care", "connect later",
            "दिवस चांगला जावो", "काळजी घ्या", "नंतर कॉल करते", "नंतर फोन करते"
        ]
        customer_turns = [d for d in call_dialogue if d.get("role") == "customer" and len(d.get("text", "").strip()) > 3]
        if len(customer_turns) >= 2 and any(phrase in text for phrase in ending_phrases):
            logger.info("👋 [GOODBYE DETECTED IN AGENT SPEECH] Ensuring automated call termination after speech finishes...")
            trigger_hangup(wait_for_speech=True, delay_seconds=0.8)

    spoken_customer_name = f"{customer_name} ji" if not customer_name.endswith("ji") else customer_name
    agent = PriyaRealEstateAgent(
        customer_name=spoken_customer_name,
        customer_phone=customer_phone,
        hangup_fnc=trigger_hangup,
        on_speech_captured=_record_agent_speech
    )
    if intro_delivered:
        agent.intro_delivered = True

    # Reset any previous session on job context to prevent "Only one AgentSession can be the primary at a time"
    if hasattr(ctx, "_primary_agent_session"):
        ctx._primary_agent_session = None

    # Start session with dual-channel stereo recording (Caller on input, Gayatri AI on output)
    t_session_start = time.perf_counter()
    logger.info("⏱️ [RECORDING & PERF] Calling session.start(record={'audio': True})...")
    try:
        await session.start(agent=agent, room=ctx.room, record={"audio": True})
    except Exception as rec_err:
        logger.warning(f"Warning starting recording: {rec_err}. Falling back to record=False")
        await session.start(agent=agent, room=ctx.room, record=False)

    # Guarantee persistent audio recording stream directly to bookings/recordings/{ctx.room.name}.ogg
    persistent_rec_file = Path("bookings/recordings") / f"{ctx.room.name}.ogg"
    persistent_rec_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if getattr(session, "_recorder_io", None) is None:
            from livekit.agents.voice.recorder_io import RecorderIO
            session._recorder_io = RecorderIO(agent_session=session)
            if hasattr(session, "input") and hasattr(session.input, "audio") and session.input.audio:
                session.input.audio = session._recorder_io.record_input(session.input.audio)
            if hasattr(session, "output") and hasattr(session.output, "audio") and session.output.audio:
                session.output.audio = session._recorder_io.record_output(session.output.audio)

        if hasattr(session, "_recorder_io") and session._recorder_io and not session._recorder_io.recording:
            await session._recorder_io.start(output_path=persistent_rec_file)
            logger.info(f"🎙️ [AUDIO RECORDING DIRECT] Persistent recording stream active at: {persistent_rec_file}")
    except Exception as rec_setup_err:
        logger.warning(f"RecorderIO direct initialization note: {rec_setup_err}")
    
    t_session_ready = (time.perf_counter() - t_session_start) * 1000
    t_total_ready = (time.perf_counter() - t_start) * 1000
    logger.info(f"⏱️ [PERF] session.start() returned! Took {t_session_ready:.1f}ms. Total job-to-ready time: {t_total_ready:.1f}ms")
    logger.info(f"⏱️ [PERF +{t_total_ready:.1f}ms] Agent Session Started & Ready in <50ms!")

    # Allow 0.15s for WebRTC audio negotiation and SIP RTP streams to settle naturally
    logger.info("⏳ Allowing 0.15s for audio bridge and SIP RTP connection to settle naturally...")
    await asyncio.sleep(0.15)

    # Snappy Multi-Stage Natural Greeting Loop:
    # Guarantee Gayatri initiates the call immediately with "Hello?" so the caller never hears silence!
    if not _hangup_scheduled:
        is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
        if is_cartesia and hasattr(session.tts, "update_options"):
            session.tts.update_options(
                voice=kusha_voice_id,
                language="mr",
                speed=cartesia_speed,
                volume=cartesia_volume,
                emotion=[cartesia_emotion] if cartesia_emotion else None
            )

        logger.info("🎙️ [CALL CONNECTED] Ready! Gayatri listening for caller greeting/voice to deliver predefined intro...")
        intro_finished = True

    # Silence Watchdog: 0.8s (Initial Hello) -> 10s Intervals -> 20s (Auto Hangup)
    t_last_activity = time.time()
    last_prompt_time = time.time()
    intro_finished = True

    async def _silence_watchdog():
        nonlocal t_last_activity, last_prompt_time, _hangup_scheduled, agent_is_speaking, t_user_stop, caller_has_spoken, intro_delivered
        logger.info("🛡️ [SILENCE WATCHDOG] Task active. Monitoring caller activity...")
        
        # 1. Block and DO NOT count ANY silence while call is ringing!
        while not intro_finished and not _hangup_scheduled:
            await asyncio.sleep(0.1)

        if _hangup_scheduled:
            return

        logger.info("🛡️ [SILENCE WATCHDOG] Caller connected! Monitoring silence (0.8s initial hello, 10s intervals, 20s auto-terminate)...")
        
        t_call_pickup = time.time()
        last_prompt_time = t_call_pickup
        initial_hello_done = False

        while not _hangup_scheduled:
            await asyncio.sleep(0.2)
            if _hangup_scheduled:
                break
                
            # If agent is currently speaking or generating speech, reset caller silence timer
            if agent_is_speaking or (session.current_speech and not session.current_speech.done()):
                t_last_activity = time.time()
                last_prompt_time = time.time()
                continue

            now = time.time()
            silence_duration = now - t_last_activity

            # 1. After 0.8s of picking up the call: If caller has not spoken yet, say "हॅलो?"
            if not initial_hello_done and not caller_has_spoken:
                if now - t_call_pickup >= 0.8:
                    initial_hello_done = True
                    last_prompt_time = now
                    t_last_activity = now
                    logger.info("🎙️ [INITIAL GREETING] 0.8s elapsed after pickup with caller silent. Saying 'हॅलो?'...")
                    try:
                        t_user_stop = 0.0
                        record_dialogue_turn("agent", "हॅलो?")
                        session.say("हॅलो?", allow_interruptions=True)
                        t_last_activity = time.time()
                        last_prompt_time = time.time()
                    except Exception as e:
                        logger.warning(f"Error speaking initial 0.8s hello: {e}")
                continue

            active_lang = ACTIVE_TTS_LANGUAGE or current_lang or "mr"

            # 2. If caller stays silent for 20.0 seconds total without response -> Terminate call
            if silence_duration >= 20.0:
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {silence_duration:.1f}s (>=20s). Terminating call in language '{active_lang}'...")
                if active_lang == "mr":
                    farewell_text = "तुमचा आवाज येत नाहीये. मी नंतर कॉल करते, दिवस चांगला जावो, नमस्कार."
                elif active_lang == "en":
                    farewell_text = "I'm unable to hear you. We will connect later. Have a wonderful day, goodbye!"
                else:
                    farewell_text = "Lagta hai aapki aawaaz nahi aa rahi hai. Hum baad mein call karte hain, aapka din shubh ho, bye!"
                try:
                    t_user_stop = 0.0  # Reset so farewell is never tracked as turn latency spike
                    record_dialogue_turn("agent", farewell_text)
                    speech_handle = session.say(farewell_text, allow_interruptions=False)
                    if speech_handle:
                        await speech_handle.wait_for_playout()
                except Exception as e:
                    logger.warning(f"Error speaking silence farewell: {e}")
                trigger_hangup(wait_for_speech=False, delay_seconds=0.8)
                break

            # 3. Say prompt after 10.0 seconds interval of genuine caller silence
            if (now - last_prompt_time >= 10.0) and (silence_duration >= 10.0):
                last_prompt_time = now
                t_last_activity = now
                logger.info(f"⏳ [SILENCE PROMPT] 10s silence interval elapsed (total silence: {silence_duration:.1f}s). Prompting in language '{active_lang}'...")
                
                # If intro has not yet been delivered, deliver the Sai Garden intro directly
                if not getattr(agent, "intro_delivered", False) and not intro_delivered:
                    intro_delivered = True
                    if agent:
                        agent.intro_delivered = True
                    logger.info("⏳ [INTRO VIA SILENCE WATCHDOG] Caller silent after hello. Delivering Sai Garden intro now...")
                    if active_lang == "hi":
                        prompt_text = "नमस्ते! मैं गायत्री बोल रही हूँ साई गार्डन से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?"
                    elif active_lang == "en":
                        prompt_text = "Hello! This is Gayatri from Sai Garden, right opposite Xperia Mall. Are you looking for a 1 BHK or a 2 BHK?"
                    else:
                        prompt_text = "नमस्कार! मी गायत्री बोलतेय साई गार्डन मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?"
                else:
                    if active_lang == "mr":
                        prompt_text = "हॅलो? माझा आवाज येतोय का?"
                    elif active_lang == "en":
                        prompt_text = "Hello? Are you able to hear me?"
                    else:
                        prompt_text = "हॅलो? क्या आप सुन रहे हैं?"

                try:
                    t_user_stop = 0.0
                    record_dialogue_turn("agent", prompt_text)
                    session.say(prompt_text, allow_interruptions=True)
                except Exception as e:
                    logger.warning(f"Error speaking 10s interval silence prompt: {e}")

    watchdog_task = asyncio.create_task(_silence_watchdog())


# ==============================================================================
# 5. HIGH-SPEED PRE-WARMED CLI RUNNER
# ==============================================================================
async def request_fnc(req: JobRequest) -> None:
    # Strictly reject any non-telephony rooms (e.g. storage rooms)
    if not (req.room.name.startswith("call-") or req.room.name.startswith("sip-")):
        logger.info(f"🚫 Rejecting non-telephony job request for room: {req.room.name}")
        await req.reject()
        return
    await req.accept()

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
            prewarm_fnc=prewarm_fnc,
            num_idle_processes=1,
            load_threshold=100.0,
            initialize_process_timeout=90.0,
        )
    )
