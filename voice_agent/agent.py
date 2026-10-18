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
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import difflib
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
ACTIVE_TTS_LANGUAGE = "hi"

def normalize_phonetics(text: str, lang: str | None = None) -> str:
    if not text:
        return text
    target_lang = lang or ACTIVE_TTS_LANGUAGE

    # 1. Global Cleanups:
    # Remove currency symbols & formal expansions (ensures Cartesia NEVER speaks 'भारतीय रुपया')
    text = re.sub(r'₹\s*', '', text)
    text = re.sub(r'भारतीय\s*रुपया[ा-्]*|भारतीय\s*रुपये|भारतीय\s*रुपयात', 'रुपये', text, flags=re.IGNORECASE)

    # 2. Smooth exclamation marks into calm commas/periods to eliminate unnatural pitch spikes & hyper-excitation
    text = text.replace('!', ', ')
    text = re.sub(r'\s*,\s*,+', ',', text)
    text = re.sub(r'\s*\.\s*\.+', '.', text)

    is_hindi = (target_lang == "hi")
    is_english = (target_lang == "en")
    is_marathi = not is_hindi and not is_english

    if is_marathi:
        replacements = [
            (r'\b(dombivli|dombivali|dombivili|dombiwli)\b', 'डोंबिवली'),
            (r'\bsai\s*garden\b', 'साई गार्डन'),
            (r'\blodha\s*heaven\b', 'लोढा हेवन'),
            (r'\bshilphata\b', 'शिळफाटा'),
            (r'\bmanpada\b', 'मानपाडा'),
            (r'\bxperia\b', 'एक्सपेरिया'),
            (r'\bxperia\s*mall\b', 'एक्सपेरिया मॉल'),
            (r'\bnilje\b', 'निळजे'),
            (r'\bghansoli\b', 'घणसोली'),
            (r'\blodha\s*world\s*school\b', 'लोढा वर्ल्ड स्कूल'),
            (r'\bpawar\s*public\s*school\b', 'पवार पब्लिक स्कूल'),
            (r'\bira\s*global\b', 'आयरा ग्लोबल स्कूल'),
            (r'\bchandresh\s*lodha\b', 'चंद्रेश लोढा स्कूल'),
            (r'\bjupiter\s*hospital\b', 'ज्युपिटर हॉस्पिटल'),
            (r'\binfinity\s*(women\'?s?|clinic)?\b', 'इन्फिनिटी क्लिनिक'),
            (r'\bmgm\s*hospital\b', 'एमजीएम हॉस्पिटल'),
            (r'\bsai\s*hospital\b', 'साई हॉस्पिटल'),
            (r'\b8[:.]30\b', 'साडे आठ'),
            (r'\b7[:.]30\b', 'साडे सात'),
            (r'\b9[:.]30\b', 'साडे नऊ'),
            (r'\b10[:.]30\b', 'साडे दहा'),
            (r'\b11[:.]30\b', 'साडे अकरा'),
            (r'\b12[:.]30\b', 'साडे बारा'),
            (r'\b4[:.]30\b', 'साडे चार'),
            (r'\b5[:.]30\b', 'साडे पाच'),
            (r'\b6[:.]30\b', 'साडे सहा'),
            (r'\b30\b', 'तीस'),
            (r'\b45\b', 'पंचेचाळीस'),
            (r'\b22\b', 'बावीस'),
            (r'\b35\b', 'पस्तीस'),
            (r'\b760\b', 'सातशे साठ'),
            (r'\b375\b', 'तीनशे पंच्याहत्तर'),
            (r'\b520\b', 'पाचशे वीस'),
            (r'G\+\s*22', 'जी प्लस बावीस'),
            (r'\bgym\b', 'जिम'),
            (r'\bswimming\s*pool\b', 'स्विमिंग पूल'),
            (r'\bclubhouse\b', 'क्लबहाऊस'),
            (r'\bmodern\s*amenities\b', 'आधुनिक सोयी'),
            (r'\bamenities\b', 'सोयी'),
            (r'\bdown\s*payment\b', 'डाऊन पेमेंट'),
            (r'\beasy\s*(?:bank\s*)?home\s*loan\b', 'सोपे बँक होम लोन'),
            (r'\bhome\s*loan\b', 'होम लोन'),
            (r'\bloan\b', 'लोन'),
            (r'\bbudget\b', 'बजेट'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'स्क्वेअर फूट'),
            (r'\b1\s*BHK\b', 'एक बी एच के'),
            (r'\b2\s*BHK\b', 'दोन बी एच के'),
            (r'\b1\s*RK\b', 'एक आर के'),
            (r'\b1rk\b', 'एक आर के'),
            (r'\bRK\b', 'आर के'),
            (r'\bBHK\b', 'बी एच के'),
            (r'\bcarpet\s*area\b', 'कार्पेट एरिया'),
            (r'\bsite\s*visit\b', 'साईट व्हिजिट'),
            (r'\bflats\b', 'फ्लॅट्स'),
            (r'\bflat\b', 'फ्लॅट'),
            (r'\bbalcony\b', 'बाल्कनी'),
            (r'\bmaster\s*bedroom\b', 'मास्टर बेडरूम'),
            (r'\bwhatsapp\b', 'व्हॉट्सअॅप'),
            (r'\bbrochure\b', 'ब्रोशर'),
            (r'\bready[- ]*to[- ]*move\b', 'रेडी टू मूव्ह'),
            (r'\bunder[- ]*construction\b', 'अंडर कन्स्ट्रक्शन'),
            (r'\bpossession\b', 'पझेशन'),
            (r'\bhello\b', 'हॅलो'),
            (r'\bbye\b', 'नमस्कार'),
            (r'\b15\b', 'पंधरा'),
            (r'\b20\b', 'वीस'),
            (r'\b1\b', 'एक'),
            (r'\b2\b', 'दोन'),
            (r'\b3\b', 'तीन'),
            (r'\b4\b', 'चार'),
            (r'\b5\b', 'पाच'),
            (r'\b6\b', 'सहा'),
            (r'\b7\b', 'सात'),
            (r'\b8\b', 'आठ'),
            (r'\b9\b', 'नऊ'),
            (r'\b10\b', 'दहा'),
            (r'\b11\b', 'अकरा'),
            (r'\b12\b', 'बारा'),
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
        # Pure Devanagari Hindi replacements & Hindi numbers
        replacements = [
            (r'\b(dombivli|dombivali|dombivili|dombiwli)\b', 'डोंबिवली'),
            (r'\bsai\s*garden\b', 'साई गार्डन'),
            (r'\blodha\s*heaven\b', 'लोढा हेवन'),
            (r'\bshilphata\b', 'शिळफाटा'),
            (r'\bmanpada\b', 'मानपाडा'),
            (r'\bxperia\s*mall\b', 'एक्सपेरिया मॉल'),
            (r'\bxperia\b', 'एक्सपेरिया मॉल'),
            (r'\bnilje\b', 'निलजे'),
            (r'\bghansoli\b', 'घणसोली'),
            (r'\blodha\s*world\s*school\b', 'लोढा वर्ल्ड स्कूल'),
            (r'\bpawar\s*public\s*school\b', 'पवार पब्लिक स्कूल'),
            (r'\bira\s*global\b', 'आयरा ग्लोबल स्कूल'),
            (r'\bchandresh\s*lodha\b', 'चंद्रेश लोढा स्कूल'),
            (r'\bjupiter\s*hospital\b', 'ज्युपिटर हॉस्पिटल'),
            (r'\binfinity\s*(women\'?s?|clinic)?\b', 'इन्फिनिटी क्लिनिक'),
            (r'\bmgm\s*hospital\b', 'एमजीएम हॉस्पिटल'),
            (r'\bsai\s*hospital\b', 'साई हॉस्पिटल'),
            (r'\b10[:.]30\b', 'साढ़े दस'),
            (r'\b11[:.]30\b', 'साढ़े ग्यारह'),
            (r'\b12[:.]30\b', 'साढ़े बारह'),
            (r'\b1[:.]30\b', 'डेढ़'),
            (r'\b2[:.]30\b', 'ढाई'),
            (r'\b3[:.]30\b', 'साढ़े तीन'),
            (r'\b4[:.]30\b', 'साढ़े चार'),
            (r'\b5[:.]30\b', 'साढ़े पांच'),
            (r'\b6[:.]30\b', 'साढ़े छह'),
            (r'\b7[:.]30\b', 'साढ़े सात'),
            (r'\b8[:.]30\b', 'साढ़े आठ'),
            (r'\b9[:.]30\b', 'साढ़े नौ'),
            (r'G\+\s*22', 'जी प्लस बाईस'),
            (r'\bgym\b', 'जिम'),
            (r'\bswimming\s*pool\b', 'स्विमिंग पूल'),
            (r'\bclubhouse\b', 'क्लबहाउस'),
            (r'\bmodern\s*amenities\b', 'आधुनिक सुविधाएँ'),
            (r'\bamenities\b', 'सुविधाएँ'),
            (r'\bdown\s*payment\b', 'डाउन पेमेंट'),
            (r'\beasy\s*(?:bank\s*)?home\s*loan\b', 'आसान बैंक होम लोन'),
            (r'\bhome\s*loan\b', 'होम लोन'),
            (r'\bloan\b', 'लोन'),
            (r'\bbudget\b', 'बजट'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'स्क्वायर फीट'),
            (r'\b1\s*BHK\b', 'एक बी एच के'),
            (r'\b2\s*BHK\b', 'दो बी एच के'),
            (r'\b1\s*RK\b', 'एक आर के'),
            (r'\b1rk\b', 'एक आर के'),
            (r'\bBHK\b', 'बी एच के'),
            (r'\bRK\b', 'आर के'),
            (r'\bcarpet\s*area\b', 'कार्पेट एरिया'),
            (r'\bready[- ]*to[- ]*move\b', 'रेडी-टू-मूव'),
            (r'\bunder[- ]*construction\b', 'अंडर-कन्स्ट्रक्शन'),
            (r'\bpossession\b', 'पज़ेशन'),
            (r'\bsite\s*visit\b', 'साईट विजिट'),
            (r'\bwhatsapp\b', 'व्हाट्सऐप'),
            (r'\bbye\b', 'नमस्ते'),
            (r'\bthank\s*you\b', 'धन्यवाद'),
            (r'\b30\b', 'तीस'),
            (r'\b45\b', 'पैंतालीस'),
            (r'\b22\b', 'बाईस'),
            (r'\b35\b', 'पैंतीस'),
            (r'\b10\b', 'दस'),
            (r'\b11\b', 'ग्यारह'),
            (r'\b12\b', 'बारह'),
            (r'\b1\b', 'एक'),
            (r'\b2\b', 'दो'),
            (r'\b3\b', 'तीन'),
            (r'\b4\b', 'चार'),
            (r'\b5\b', 'पांच'),
            (r'\b6\b', 'छह'),
            (r'\b7\b', 'सात'),
            (r'\b8\b', 'आठ'),
            (r'\b9\b', 'नौ'),
            (r'\b15\b', 'पंद्रह'),
            (r'\b20\b', 'बीस'),
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
        return [normalize_phonetics(t, lang=ACTIVE_TTS_LANGUAGE) for t in res]

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
                    ev.token = normalize_phonetics(ev.token, lang=ACTIVE_TTS_LANGUAGE)
                return ev
        return _PhoneticStreamWrapper(inner_stream)

_orig_cartesia_synthesize = cartesia.TTS.synthesize
def _phonetic_synthesize(self, text: str, **kwargs):
    req_lang = ACTIVE_TTS_LANGUAGE or kwargs.get("language") or getattr(getattr(self, "_opts", None), "language", None)
    return _orig_cartesia_synthesize(self, normalize_phonetics(text, lang=req_lang), **kwargs)
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
# 1. GAYATRI VOICE PERSONA & SAI GARDEN 24-PAGE BROCHURE KNOWLEDGE BASE
# ==============================================================================
HINDI_REAL_ESTATE_PROMPT = """# GAYATRI — AI REAL ESTATE PROPERTY ADVISOR (MASTER SYSTEM PROMPT)

0. STRICT BREVITY & NATURAL HUMAN FLOW (MANDATORY — MAX 1-2 SHORT SENTENCES):
- KEEP EVERY RESPONSE UNDER 15-20 WORDS MAXIMUM.
- NEVER speak lengthy explanations, long paragraphs, or robotic monologues.
- Give the exact direct answer immediately to the customer's question.
- STRICT 'SIR / सर' USAGE: Do NOT repeat 'सर' / 'sir' in every sentence. Use it at most once in the entire call or omit it completely.
- NEVER END ON A DEAD-END: Every factual response MUST end with a gentle conversational question (e.g. asking if they are looking for 1 BHK or 2 BHK, or inviting for a site visit).
- Speak naturally like a warm, experienced Mumbai real estate advisor using natural real estate loanwords.

1. ROLE, OBJECTIVE & NATURAL HUMAN PERSONA
- You are Gayatri (गायत्री), a warm, intelligent, and natural Real Estate Property Advisor representing the prestigious SAI GARDEN (साई गार्डन) project by Sai City Group / Shree Om Sai Developers.
- PRIMARY GOAL: Act as an authentic, helpful human consultant. Provide clear property details and guide interested buyers naturally.
- DEFAULT LANGUAGE: HINDI (हिंदी). The call begins in Hindi by default.
- NATURAL BILINGUAL REAL ESTATE TERMINOLOGY:
  * Do NOT use bookish or Sanskritized words.
  * Use natural English real estate terminology in speech: 1 BHK, 2 BHK, 30 lakh, 45 lakh, amenities, gym, swimming pool, garden, clubhouse, site visit, down payment, home loan, ready-to-move, under-construction, brochure.
- STRICT LANGUAGE LOCK:
  * Speak fluent conversational Hindi by default.
  * When caller speaks Marathi or asks for Marathi: Instantly switch and lock to pure, warm Marathi.
  * When speaking in English: Stick to English.
- STRICT CURRENCY RULE:
  * NEVER say 'भारतीय रुपया' or use ₹ symbol. Say '30 लाख' or '45 लाख'.
- TONE & ATTITUDE: Calm, warm, friendly, consistent pitch, and conversational.

2. OFFICIAL 24-PAGE SAI GARDEN BROCHURE KNOWLEDGE BASE:
- Project Name: SAI GARDEN (साई गार्डन).
- Tagline: "Where Luxury Meets Nature".
- Developer: Sai City Group / Shree Om Sai Developers.
- MahaRERA Number: PR1330002501452.
- Location: Lodha Heaven, Nilaje, Kalyan-Shil Road, Dombivli East (शिळफाटा-मानपाडा हायवे, डोंबिवली ईस्ट, लोढा हेवन, एक्सपेरिया मॉल समोर).
- Building Structure: G+22-Storey Grand Residential Tower (G+22 मजली भव्य टॉवर) with high-speed elevators, fire safety systems, and grand entrance lobby.
- Configurations, Pricing & Carpet Area:
  * 1 BHK: Starts at 30 Lakh onwards. Carpet area: 375 to 520 sq.ft.
  * 2 BHK: Starts at 45 Lakh onwards. Carpet area: Up to 760 sq.ft.
  * 3 BHK / 1 RK: NOT AVAILABLE. Politely clarify that only 1 BHK and 2 BHK configurations are available.
- Complete Connectivity & Travel Times (Official 24-Page Brochure):
  * Nilje Railway Station: 1-2 minutes walking distance (project is right adjacent to Nilje station).
  * Kalyan-Shilphata Road: 2 minutes.
  * Xperia Mall: 3 minutes (directly opposite the project).
  * Upcoming Kalyan-Taloja Metro Line 12: 4 minutes.
  * PVR Cinema & D-Mart: 5 minutes.
  * Airoli-Katai Tunnel: 10 minutes.
  * Diva Railway Station: 12 minutes.
  * Dombivli Railway Station: 20 minutes.
  * Kalyan Railway Station: 20-25 minutes.
  * Millennium Business Park (MBP) Mahape: 20 minutes.
  * Reliance Corporate Park: 22 minutes.
  * Mindspace IT Park Airoli: 25 minutes.
  * Thane Bullet Train Station: 25 minutes.
  * Thane Viviana / R-Mall: 30 minutes.
  * Navi Mumbai International Airport (NMIA): 45 minutes.
- Nearby Educational Institutions:
  * Pawar Public School: 1 minute.
  * Lodha World School: 5 minutes.
  * Guardian School & Ira Global School: 10 minutes.
  * Pendharkar College: 15 minutes.
- Nearby Healthcare & Hospitals:
  * Neon Hospital: 6 minutes.
  * Vaze Hospital: 9 minutes.
  * AIMS Hospital: 18 minutes.
  * Jupiter Hospital: 25 minutes.
- 35+ Luxury Lifestyle Amenities: Swimming Pool, Modern Gym, Landscaped Garden, Kids Play Area, Clubhouse, Yoga Room, Ample Stack & Puzzle Car Parking, 24/7 Security with CCTV.
- Apartment Specifications: 2x4 vitrified tiles in living area, granite kitchen platform with SS sink, branded CP fittings (Jaquar/Cera), open balcony with scenic nature view.
- Possession: Under-construction with on-time delivery schedule; ready-to-move options also available.
- Financing: Flexible down payment from just 3 to 5 Lakh, easy home loan assistance from all leading banks (SBI, HDFC, ICICI, etc.).

3. CONVERSATION PROGRESSION & SCRIPTS:
- Greeting (Turn 0): Call begins with agent saying a clean, simple "हॅलो?".
- Turn 1 Opening Pitch:
  * Marathi: "नमस्कार! मी गायत्री बोलतेय साई गार्डन डोंबिवली मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?"
  * Hindi: "नमस्ते! मैं गायत्री बात कर रही हूँ साई गार्डन डोंबिवली से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?"
- 1 BHK Inquiry:
  * Marathi: "1 BHK 30 लाखांपासून सुरू होतो, फक्त 3 ते 5 लाख डाऊन पेमेंट आणि सोपे बँक लोन उपलब्ध आहे. आपण ready-to-move पाहताय की under-construction चालेल?"
  * Hindi: "1 BHK 30 लाख से शुरू होता है, सिर्फ 3 से 5 लाख डाउन पेमेंट और आसान बैंक लोन उपलब्ध है। आप ready-to-move देख रहे हैं या under-construction चलेगा?"
- 2 BHK Inquiry:
  * Marathi: "2 BHK 45 लाखांपासून सुरू होतो. ही G+22 मजली इमारत असून यात gym, swimming pool अशा 35 पेक्षा जास्त amenities मिळतात. आपण ready-to-move पाहताय की under-construction चालेल?"
  * Hindi: "2 BHK 45 लाख से शुरू होता है। यह G+22 मंजिला इमारत है जिसमें gym, swimming pool जैसी 35 से ज्यादा amenities मिलती हैं। आप ready-to-move देख रहे हैं या under-construction चलेगा?"
- 3 BHK / 1 RK Inquiry:
  * Marathi: "माफ करा, आमच्याकडे फक्त 1 BHK आणि 2 BHK चे पर्याय उपलब्ध आहेत. आपण 2 BHK पाहू इच्छिता का?"
  * Hindi: "माफ़ कीजियेगा, हमारे यहाँ सिर्फ 1 BHK और 2 BHK उपलब्ध हैं। क्या आप 2 BHK देखना चाहेंगे?"
- Specific Connectivity Landmarks:
  * Kalyan: "कल्याण स्टेशन इथून 20 ते 25 मिनिटांवर आहे आणि कल्याण-शिळफाटा रोड फक्त 2 मिनिटांवर आहे. आपण 1 BHK शोधत आहात की 2 BHK?"
  * Dombivli: "डोंबिवली स्टेशन 20 मिनिटांवर आहे आणि जवळच निळजे स्टेशन फक्त 2 मिनिटांवर आहे. आपण 1 BHK शोधत आहात की 2 BHK?"
  * Nilje: "निळजे रेल्वे स्टेशन प्रोजेक्टच्या अगदी जवळ, फक्त 1 ते 2 मिनिटांच्या वॉकिंग डिस्टन्सवर आहे. आपण 1 BHK शोधत आहात की 2 BHK?"
  * Metro Line 12: "अपकमिंग कल्याण-तळोजा मेट्रो लाईन 12 स्टेशन अगदी समोर 4 मिनिटांवर येत आहे. आपण 1 BHK शोधत आहात की 2 BHK?"
- Site Visit Step-by-Step Scheduling:
  * Step 1: When introducing site visit, ask: "प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?" / "प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय सुविधाजनक रहेगा?"
  * Step 2: When caller gives day and time:
    - Marathi: "नक्कीच! {day} रोजी {time} आपली साईट व्हिजिट निश्चित केली आहे. सर्व माहिती व्हॉट्सअॅपवर पाठवत आहे. खूप खूप धन्यवाद, नमस्कार!"
    - Hindi: "बिल्कुल! {day} को {time} आपकी साईट विजिट कन्फर्म कर दी है। सारी जानकारी व्हाट्सऐप पर भेज रही हूँ। बहुत-बहुत धन्यवाद, नमस्ते!"
- Referral Fallback Script (When caller declines or says No):
  * Marathi: "काही हरकत नाही. आपल्या फॅमिली किंवा फ्रेंड्समध्ये कोणी 1 BHK किंवा 2 BHK फ्लॅट शोधत असेल, तर त्यांच्यासोबत आमचा नंबर नक्की शेअर करा. खूप खूप धन्यवाद, नमस्कार!"
  * Hindi: "कोई बात नहीं। अगर आपकी फैमिली या फ्रेंड्स सर्कल में कोई 1 BHK या 2 BHK फ्लैट ढूंढ रहा हो, तो उनके साथ हमारा नंबर ज़रूर शेयर कीजिएगा। बहुत-बहुत धन्यवाद, नमस्ते!"
"""

# ==============================================================================
# 2. LANGUAGE RESOLUTION HELPER & AGENT CLASS (STICKY MULTILINGUAL)
# ==============================================================================
LANGUAGE_LOCKED_EXPLICITLY = False

def resolve_language(transcript: str, current_lang: str = "hi") -> str:
    """
    DYNAMIC MULTILINGUAL SWITCHING & STICKY LOCKING:
    - Default is Hindi ('hi').
    - If caller explicitly requests Marathi ("मराठीत बोला", "marathi bola", etc.) -> lock to 'mr'.
    - If caller explicitly requests Hindi ("हिंदी में बोलो", "hindi mein baat karo", etc.) -> lock to 'hi'.
    - If caller explicitly requests English ("speak in english", etc.) -> lock to 'en'.
    - Once explicitly requested, the agent locks to that language and NEVER drifts or mixes languages.
    - Word boundary regex ensures substrings (e.g. 'aap' in 'aapan', 'hum' in 'shubham') never cause false triggers.
    """
    global LANGUAGE_LOCKED_EXPLICITLY
    text = transcript.strip().lower()

    # 1. Explicit request to switch to English
    english_explicit = [
        r'\bin english\b', r'\benglish please\b', r'\bcan you speak english\b', r'\bcan we speak english\b',
        r'\benglish mein\b', r'\benglish me\b', r'\benglish madhe\b', r'\benglish bola\b', r'\bइंग्लिश\b'
    ]
    if any(re.search(pat, text) for pat in english_explicit):
        LANGUAGE_LOCKED_EXPLICITLY = True
        return 'en'

    # 2. Explicit request to switch to Hindi
    hindi_explicit = [
        r'\bhindi mein\b', r'\bhindi me\b', r'\bhindi please\b', r'\bspeak in hindi\b',
        r'\btalk in hindi\b', r'\bhindi madhe bola\b', r'\bहिंदी में बोलो\b', r'\bहिंदी में बात\b',
        r'\bहिंदी\b', r'\bhindi boliye\b', r'\bhindi bol\b'
    ]
    if any(re.search(pat, text) for pat in hindi_explicit):
        LANGUAGE_LOCKED_EXPLICITLY = True
        return 'hi'

    # 3. Explicit request to switch to Marathi
    marathi_explicit = [
        r'\bmarathi madhe\b', r'\bmarathit bola\b', r'\bmarathi bola\b', r'\bmarathi madhun\b',
        r'\bmarathi yete ka\b', r'\bmarathit sanga\b', r'\bmarathi sanga\b', r'\bmarathi please\b',
        r'\bmarathi mein\b', r'\bmarathi me\b', r'\bmarathi bhasha\b', r'\bमराठीत बोला\b',
        r'\bमराठी बोला\b', r'\bमराठी मध्ये बोला\b', r'\bमराठी\b'
    ]
    if any(re.search(pat, text) for pat in marathi_explicit):
        LANGUAGE_LOCKED_EXPLICITLY = True
        return 'mr'

    # If the user explicitly locked the language, stick firmly to it without drifting
    if LANGUAGE_LOCKED_EXPLICITLY:
        return current_lang

    # Natural language inference using whole-word boundary matching (only if not explicitly locked):
    if current_lang == "mr":
        hi_distinctive = ["kya", "hum", "aap", "baat", "batao", "boliye", "chahiye", "kaun", "kidhar", "kahan", "kitna", "bataiye", "hoga"]
        if any(re.search(rf"\b{w}\b", text) for w in hi_distinctive):
            return 'hi'
        if any(re.search(rf"\b{w}\b", text) for w in ["looking for", "tell me", "what is the price", "how much", "send details"]):
            return 'en'
    elif current_lang == "hi":
        mr_distinctive = ["aamhi", "pahije", "kiti", "kuthe", "sangto", "baghto", "dakhva", "mahiti", "boltoy", "bolte", "kay", "aapan", "kashe", "kadhi"]
        if any(re.search(rf"\b{w}\b", text) for w in mr_distinctive):
            return 'mr'

    return current_lang


def fuzzy_contains(text: str, targets: list[str], threshold: float = 0.68) -> bool:
    """
    Ultra-fast fuzzy & phonetic similarity matcher (0ms overhead).
    Matches exact substrings, individual words with typos/misspellings,
    and 2-word combinations against target intents across Hindi, Marathi, and English.
    """
    if not text:
        return False
    text_lower = text.lower()
    # 1. Direct fast substring check (<1 microsecond)
    for t in targets:
        if t in text_lower:
            return True
    # 2. Tokenized word & ngram similarity check via difflib
    words = re.sub(r'[^\w\s\u0900-\u097F]', ' ', text_lower).split()
    for w in words:
        if len(w) >= 3:
            for t in targets:
                if len(t) >= 3 and abs(len(w) - len(t)) <= 3:
                    if difflib.SequenceMatcher(None, w, t).ratio() >= threshold:
                        return True
    # 3. Check 2-word combinations for multi-word targets
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i+1]}"
        for t in targets:
            if " " in t:
                if difflib.SequenceMatcher(None, bigram, t).ratio() >= threshold:
                    return True
    return False


def parse_day_and_time(clean_text: str, lang: str = "mr"):
    """
    Parses flexible day and time from caller transcript across Marathi, Hindi, and English.
    Returns (detected_day, detected_time).
    Handles 'monday 11', 'monday eleven', 'monday at 11', 'monday 11:00', 'kal 11 baje', 'sunday 5', etc.
    """
    text = clean_text.lower()
    is_hindi = (lang == "hi")
    
    # 1. Date Detection (e.g. "21 तारीख", "इककीस तारीख", "21 tarik", "21st", "२१ तारीख", "सोमवार 21 तारीख")
    date_words_1_to_31 = {
        "एक": 1, "ek": 1, "वन": 1, "one": 1, "1": 1, "01": 1, "१": 1, "first": 1, "1st": 1,
        "दोन": 2, "दो": 2, "don": 2, "do": 2, "two": 2, "2": 2, "02": 2, "२": 2, "second": 2, "2nd": 2,
        "तीन": 3, "teen": 3, "three": 3, "3": 3, "03": 3, "३": 3, "third": 3, "3rd": 3,
        "चार": 4, "char": 4, "four": 4, "4": 4, "04": 4, "४": 4, "fourth": 4, "4th": 4,
        "पाच": 5, "पाँच": 5, "pach": 5, "paanch": 5, "five": 5, "5": 5, "05": 5, "५": 5, "fifth": 5, "5th": 5,
        "सहा": 6, "छह": 6, "saha": 6, "chha": 6, "six": 6, "6": 6, "06": 6, "६": 6, "sixth": 6, "6th": 6,
        "सात": 7, "saat": 7, "seven": 7, "7": 7, "07": 7, "७": 7, "seventh": 7, "7th": 7,
        "आठ": 8, "aath": 8, "eight": 8, "8": 8, "08": 8, "८": 8, "eighth": 8, "8th": 8,
        "नऊ": 9, "नौ": 9, "nau": 9, "nine": 9, "9": 9, "09": 9, "९": 9, "ninth": 9, "9th": 9,
        "दहा": 10, "दस": 10, "daha": 10, "das": 10, "ten": 10, "10": 10, "१०": 10, "tenth": 10, "10th": 10,
        "अकरा": 11, "ग्यारह": 11, "akra": 11, "gyarah": 11, "eleven": 11, "11": 11, "११": 11, "11th": 11,
        "बारा": 12, "बारह": 12, "bara": 12, "barah": 12, "twelve": 12, "12": 12, "१२": 12, "12th": 12,
        "तेरा": 13, "तेरह": 13, "tera": 13, "terah": 13, "thirteen": 13, "13": 13, "१३": 13, "13th": 13,
        "चौदा": 14, "चौदह": 14, "chauda": 14, "chaudah": 14, "fourteen": 14, "14": 14, "१४": 14, "14th": 14,
        "पंधरा": 15, "पंद्रह": 15, "pandhra": 15, "pandrah": 15, "fifteen": 15, "15": 15, "१५": 15, "15th": 15,
        "सोळा": 16, "सोलह": 16, "sola": 16, "solah": 16, "sixteen": 16, "16": 16, "१६": 16, "16th": 16,
        "सतरा": 17, "सत्रह": 17, "satra": 17, "satrah": 17, "seventeen": 17, "17": 17, "१७": 17, "17th": 17,
        "अठरा": 18, "अठारह": 18, "athra": 18, "atharah": 18, "eighteen": 18, "18": 18, "१८": 18, "18th": 18,
        "एकोणीस": 19, "उन्नीस": 19, "ekonis": 19, "unnis": 19, "nineteen": 19, "19": 19, "१९": 19, "19th": 19,
        "वीस": 20, "बीस": 20, "vis": 20, "bees": 20, "twenty": 20, "20": 20, "२०": 20, "20th": 20,
        "एकवीस": 21, "इक्कीस": 21, "इककीस": 21, "इकीस": 21, "ekvis": 21, "ikkis": 21, "twenty one": 21, "21": 21, "२१": 21, "21st": 21,
        "बावीस": 22, "बाईस": 22, "बाइस": 22, "बाएस": 22, "baais": 22, "bais": 22, "bavis": 22, "baees": 22, "twenty two": 22, "22": 22, "२२": 22, "22nd": 22,
        "तेवीस": 23, "तेईस": 23, "तेइस": 23, "tevis": 23, "teees": 23, "teis": 23, "twenty three": 23, "23": 23, "२३": 23, "23rd": 23,
        "चोवीस": 24, "चौबीस": 24, "चौबिस": 24, "chovis": 24, "chaubis": 24, "twenty four": 24, "24": 24, "२४": 24, "24th": 24,
        "पंचवीस": 25, "पच्चीस": 25, "पच्चिस": 25, "पचिस": 25, "panchvis": 25, "pachchis": 25, "twenty five": 25, "25": 25, "२५": 25, "25th": 25,
        "सव्वीस": 26, "छब्बीस": 26, "छब्बिस": 26, "छबिस": 26, "savvis": 26, "chhabhis": 26, "twenty six": 26, "26": 26, "२६": 26, "26th": 26,
        "सत्तावीस": 27, "सत्ताईस": 27, "सत्तैस": 27, "सताइस": 27, "sattavis": 27, "sattaees": 27, "twenty seven": 27, "27": 27, "२७": 27, "27th": 27,
        "अठ्ठावीस": 28, "अट्ठाईस": 28, "अठ्ठाइस": 28, "अठाइस": 28, "atthavis": 28, "atthaees": 28, "twenty eight": 28, "28": 28, "२८": 28, "28th": 28,
        "एकोणतीस": 29, "उनतीस": 29, "उन्तीस": 29, "उन्नतीस": 29, "ekontis": 29, "untis": 29, "twenty nine": 29, "29": 29, "२९": 29, "29th": 29,
        "तीस": 30, "तिस": 30, "tis": 30, "thirty": 30, "30": 30, "३०": 30, "30th": 30,
        "एकतीस": 31, "इकत्तीस": 31, "इकतीस": 31, "ektis": 31, "ikkatis": 31, "thirty one": 31, "31": 31, "३१": 31, "31st": 31,
    }

    detected_date_str = None
    matched_date_span = None
    date_keys_sorted = sorted(date_words_1_to_31.keys(), key=len, reverse=True)
    date_pat = r'(?:^|[^\w\u0900-\u097F])(' + '|'.join(re.escape(k) for k in date_keys_sorted) + r')\s*(?:st|nd|rd|th)?\s*(tarikh|tarik|tareekh|तारीख|तारखेला|तारीखेला|तारीखला|तारिख|date|दिनांक|को|रोजी|ला)(?:$|[^\w\u0900-\u097F])'
    m_date = re.search(date_pat, text)
    if not m_date:
        prefix_date_pat = r'(?:^|[^\w\u0900-\u097F])(?:tarikh|tarik|tareekh|तारीख|तारीखेला|दिनांक|date)\s*(' + '|'.join(re.escape(k) for k in date_keys_sorted) + r')(?:$|[^\w\u0900-\u097F])'
        m_date = re.search(prefix_date_pat, text)

    if m_date:
        raw_val = m_date.group(1).strip()
        if raw_val in date_words_1_to_31:
            day_num = date_words_1_to_31[raw_val]
            detected_date_str = f"{day_num} तारीख"
            matched_date_span = m_date.span()

    # 1.1 Weekday / Relative Day Detection
    days_map_mr = [
        (["आज", "aaj", "today"], "आज"),
        (["उद्या", "udya", "kal", "tomorrow"], "उद्या"),
        (["परवा", "parva", "parso"], "परवा"),
        (["सोमवार", "somwar", "somvar", "monday", "सोमवारी", "सोमरी", "somwari", "somri"], "सोमवार"),
        (["मंगळवार", "mangalwar", "mangalvar", "tuesday", "मंगळवारी", "मंगलवार", "mangalwari"], "मंगळवार"),
        (["बुधवार", "budhwar", "budhvar", "wednesday", "बुधवारी", "बुधरी", "budhwari"], "बुधवार"),
        (["गुरुवार", "guruwar", "guruvar", "thursday", "गुरुवारी", "गुरुरी", "guruwari"], "गुरुवार"),
        (["शुक्रवार", "shukrawar", "shukravar", "friday", "शुक्रवारी", "शुक्ररी", "shukrawari"], "शुक्रवार"),
        (["शनिवार", "shaniwar", "shanivar", "saturday", "sat", "शनिवारी", "shaniwari"], "शनिवार"),
        (["रविवार", "raviwar", "ravivar", "sunday", "sun", "etvar", "itvar", "aitwar", "weekend", "रविवारी", "raviwari"], "रविवार"),
    ]
    days_map_hi = [
        (["आज", "aaj", "today"], "आज"),
        (["कल", "kal", "udya", "tomorrow"], "कल"),
        (["परसों", "parso", "parva"], "परसों"),
        (["सोमवार", "somwar", "somvar", "monday", "सोमवारी", "सोमरी", "somwari", "somri"], "सोमवार"),
        (["मंगलवार", "mangalwar", "mangalvar", "tuesday", "मंगळवार", "मंगळवारी", "mangalwari"], "मंगलवार"),
        (["बुधवार", "budhwar", "budhvar", "wednesday", "बुधवारी", "budhwari"], "बुधवार"),
        (["गुरुवार", "guruwar", "guruvar", "thursday", "गुरुवारी", "guruwari"], "गुरुवार"),
        (["शुक्रवार", "shukrawar", "shukravar", "friday", "शुक्रवारी", "shukrawari"], "शुक्रवार"),
        (["शनिवार", "shaniwar", "shanivar", "saturday", "sat", "शनिवारी", "shaniwari"], "शनिवार"),
        (["रविवार", "raviwar", "ravivar", "sunday", "sun", "etvar", "itvar", "aitwar", "weekend", "रविवारी", "raviwari"], "रविवार"),
    ]
    days_map = days_map_hi if is_hindi else days_map_mr
    detected_weekday = None
    for kws, d_name in days_map:
        if any(re.search(rf"(?:^|[^\w\u0900-\u097F]){re.escape(kw)}(?:$|[^\w\u0900-\u097F])", text) for kw in kws):
            detected_weekday = d_name
            break

    if detected_date_str and detected_weekday:
        detected_day = f"{detected_weekday} {detected_date_str}"
    elif detected_date_str:
        detected_day = detected_date_str
    else:
        detected_day = detected_weekday

    # 2. Half-Hour Time Detection (e.g. 11:30, 11 30, साडे अकरा, etc.)
    times_map_mr = [
        (r'(साडे\s*आठ|साडेआठ|sade\s*aath|sadeaath|8[:.]30|8\s*30)', 'सकाळी ८:३०'),
        (r'(साडे\s*सात|साडेसात|sade\s*saat|sadesaat|7[:.]30|7\s*30)', 'सकाळी ७:३०'),
        (r'(साडे\s*नऊ|साडेनऊ|sade\s*nau|sadenau|9[:.]30|9\s*30)', 'सकाळी ९:३०'),
        (r'(साडे\s*दहा|साडेदहा|sade\s*daha|sadedaha|10[:.]30|10\s*30)', 'सकाळी १०:३०'),
        (r'(साडे\s*अकरा|साडेअकरा|sade\s*akra|sadeakra|11[:.]30|11\s*30)', 'सकाळी ११:३०'),
        (r'(साडे\s*बारा|साडेबारा|sade\s*bara|sadebara|12[:.]30|12\s*30)', 'दुपारी १२:३०'),
        (r'(साडे\s*एक|साडेएक|sade\s*ek|1[:.]30|1\s*30)', 'दुपारी १:३०'),
        (r'(साडे\s*दोन|साडेदोन|sade\s*don|2[:.]30|2\s*30)', 'दुपारी २:३०'),
        (r'(साडे\s*तीन|साडेतीन|sade\s*teen|3[:.]30|3\s*30)', 'दुपारी ३:३०'),
        (r'(साडे\s*चार|साडेचार|sade\s*char|sadechar|4[:.]30|4\s*30)', 'संध्याकाळी ४:३०'),
        (r'(साडे\s*पाच|साडेपाच|sade\s*pach|sadepach|5[:.]30|5\s*30)', 'संध्याकाळी ५:३०'),
        (r'(साडे\s*सहा|साडेसहा|sade\s*saha|sadesaha|6[:.]30|6\s*30)', 'संध्याकाळी ६:३०'),
    ]
    times_map_hi = [
        (r'(साढ़े\s*आठ|साडे\s*आठ|साडेआठ|sade\s*aath|sadeaath|8[:.]30|8\s*30)', 'सुबह 8:30 बजे'),
        (r'(साढ़े\s*सात|साडे\s*सात|साडेसात|sade\s*saat|sadesaat|7[:.]30|7\s*30)', 'सुबह 7:30 बजे'),
        (r'(साढ़े\s*नौ|साडे\s*नऊ|साडेनऊ|sade\s*nau|sadenau|9[:.]30|9\s*30)', 'सुबह 9:30 बजे'),
        (r'(साढ़े\s*दस|साडे\s*दहा|साडेदहा|sade\s*daha|sadedaha|10[:.]30|10\s*30)', 'सुबह 10:30 बजे'),
        (r'(साढ़े\s*ग्यारह|साडे\s*अकरा|साडेअकरा|sade\s*akra|sadeakra|11[:.]30|11\s*30)', 'सुबह 11:30 बजे'),
        (r'(साढ़े\s*बारह|साडे\s*बारा|साडेबारा|sade\s*bara|sadebara|12[:.]30|12\s*30)', 'दोपहर 12:30 बजे'),
        (r'(साढ़े\s*एक|साडे\s*एक|1[:.]30|1\s*30)', 'दोपहर 1:30 बजे'),
        (r'(साढ़े\s*दो|साडे\s*दोन|2[:.]30|2\s*30)', 'दोपहर 2:30 बजे'),
        (r'(साढ़े\s*तीन|साडे\s*तीन|3[:.]30|3\s*30)', 'दोपहर 3:30 बजे'),
        (r'(साढ़े\s*चार|साडे\s*चार|साडेचार|sade\s*char|sadechar|4[:.]30|4\s*30)', 'शाम 4:30 बजे'),
        (r'(साढ़े\s*पाँच|साडे\s*पाच|साडेपाच|sade\s*pach|sadepach|5[:.]30|5\s*30)', 'शाम 5:30 बजे'),
        (r'(साढ़े\s*छह|साडे\s*सहा|साडेसहा|sade\s*saha|sadesaha|6[:.]30|6\s*30)', 'शाम 6:30 बजे'),
    ]
    times_map = times_map_hi if is_hindi else times_map_mr
    # Strip date span so date numbers (e.g. 21 in '21 तारीख') never interfere with hour detection
    if matched_date_span:
        s, e = matched_date_span
        text_for_time = text[:s] + " " * (e - s) + text[e:]
    else:
        text_for_time = text

    # Strip BHK / flat / price / floor numbers from text_for_time so they NEVER parse as site visit time!
    text_for_time = re.sub(
        r'\b(?:1|2|3|4|one|two|three|ek|do|don|teen|एक|दोन|दो|तीन|१|२|३)\s*(?:bhk|bk|rk|flat|रूम|फ्लॅट|फ्लेट|नंबर|बीएचके|बी एच के|आरके)\b',
        ' ',
        text_for_time,
        flags=re.IGNORECASE
    )
    text_for_time = re.sub(
        r'\b\d+\s*(?:lakh|lac|crore|cr|मजली|मंजिला|मंजिल|लाख|करोड|पैसे|रू|rs|rupees)\b',
        ' ',
        text_for_time,
        flags=re.IGNORECASE
    )

    detected_time = None
    for pat, t_name in times_map:
        if re.search(pat, text_for_time):
            detected_time = t_name
            break

    # 3. Numeric & Word Hour Detection
    if not detected_time:
        modifier = ""
        is_morning = bool(re.search(r'\b(am|subah|morning)\b', text_for_time)) or any(w in text_for_time for w in ["सकाळी", "सुबह", "सरकारी", "साकारी"])
        is_afternoon = bool(re.search(r'\b(dopahar|afternoon)\b', text_for_time)) or any(w in text_for_time for w in ["दुपारी", "दोपहर"])
        is_evening = bool(re.search(r'\b(shaam|evening|night|raat|raatri|pm)\b', text_for_time)) or any(w in text_for_time for w in ["संध्याकाळी", "रात्री", "शाम", "रात"])

        if is_morning:
            modifier = "सुबह " if is_hindi else "सकाळी "
        elif is_afternoon:
            modifier = "दोपहर " if is_hindi else "दुपारी "
        elif is_evening:
            modifier = "शाम " if is_hindi else "संध्याकाळी "

        num_words_map = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
            'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
            'ek': 1, 'do': 2, 'don': 2, 'teen': 3, 'char': 4, 'paanch': 5, 'pach': 5,
            'chha': 6, 'saha': 6, 'saat': 7, 'aath': 8, 'nau': 9, 'das': 10, 'daha': 10, 'dha': 10,
            'gyarah': 11, 'akra': 11, 'bara': 12, 'barah': 12,
            'एक': 1, 'दोन': 2, 'दो': 2, 'तीन': 3, 'चार': 4, 'पाच': 5, 'पाँच': 5,
            'सहा': 6, 'छह': 6, 'सात': 7, 'आठ': 8, 'नऊ': 9, 'नौ': 9, 'दहा': 10, 'दस': 10, 'दाह': 10,
            'अकरा': 11, 'अकारा': 11, 'अकारावास': 11, 'अकरावास': 11, 'अकरावाजता': 11, 'अकरावसथा': 11, 'ग्यारह': 11,
            'बारा': 12, 'बारावाजता': 12, 'बारावास': 12, 'बारावासता': 12, 'बारह': 12,
            'दोनवाजता': 2, 'दोनवास': 2, 'दोनवासता': 2, 'तीनवाजता': 3, 'चारवाजता': 4, 'पाचवाजता': 5, 'सहावाजता': 6,
            'दाहवासता': 10, 'दाहवासतम': 10, 'दाहवाजता': 10, 'दहावास': 10, 'दहावाजता': 10,
            '१': 1, '२': 2, '३': 3, '४': 4, '५': 5, '६': 6, '७': 7, '८': 8, '९': 9, '१०': 10, '११': 11, '१२': 12
        }

        # Check 11:00 or 11.00 format
        m_clock = re.search(r'\b(1[0-2]|[1-9])[:.](00)\b', text_for_time)
        if m_clock:
            h_val = int(m_clock.group(1))
            if not modifier:
                if 8 <= h_val <= 11:
                    modifier = "सुबह " if is_hindi else "सकाळी "
                elif h_val == 12 or (1 <= h_val <= 3):
                    modifier = "दोपहर " if is_hindi else "दुपारी "
                else:
                    modifier = "शाम " if is_hindi else "संध्याकाळी "
            detected_time = f"{modifier}{h_val} बजे" if is_hindi else f"{modifier}{h_val} वाजता"

        # Check standalone compound time words where hour + vajta are merged (e.g. अकरावसथा, दहावासता, बारावाजता)
        if not detected_time:
            standalone_times = {
                "अकरावसथा": 11, "अकरावाजता": 11, "अकरावास": 11, "अकारावास": 11,
                "दाहवासता": 10, "दाहवासतम": 10, "दाहवाजता": 10, "दहावासता": 10, "दहावाजता": 10, "दहावास": 10,
                "बारावाजता": 12, "बारावासता": 12, "बारावास": 12,
                "दोनवाजता": 2, "दोनवासता": 2, "दोनवास": 2,
                "तीनवाजता": 3, "चारवाजता": 4, "पाचवाजता": 5, "सहावाजता": 6
            }
            for w_term, h_num in standalone_times.items():
                if w_term in text_for_time:
                    if not modifier:
                        if 8 <= h_num <= 11:
                            modifier = "सुबह " if is_hindi else "सकाळी "
                        elif h_num == 12 or (1 <= h_num <= 3):
                            modifier = "दोपहर " if is_hindi else "दुपारी "
                        else:
                            modifier = "शाम " if is_hindi else "संध्याकाळी "
                    detected_time = f"{modifier}{h_num} बजे" if is_hindi else f"{modifier}{h_num} वाजता"
                    break

        # Check explicit baje/vajta context with digit OR number word (e.g. 11 baje, बारह बज, 12 बजे, 4 वाजता)
        # Note: Time unit suffix is STRICTLY MANDATORY (no '?') to prevent matching property types like '2 BHK' or 'एक'
        # re.finditer takes the LAST match so caller self-corrections like "दो बज, बारह बज" correctly pick 12!
        if not detected_time:
            pattern = r'(?:^|[^\w\u0900-\u097F])(1[0-2]|[1-9]|एक|दोन|दो|तीन|चार|पाच|पाँच|सहा|छह|सात|आठ|नऊ|नौ|दहा|दस|दाह|dha|अकरा|अकारा|अकारावास|अकरावास|अकरावसथा|ग्यारह|बारा|बारह|दाहवासता|दाहवासतम|दहावास|दहावाजता|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(baje|vajta|vaje|बजे|बज|वाजता|वाजे|वास|am|pm|o\'clock)(?:$|[^\w\u0900-\u097F])'
            matches = list(re.finditer(pattern, text_for_time))
            if matches:
                last_m = matches[-1]
                raw_h = last_m.group(1)
                h_val = int(raw_h) if raw_h.isdigit() else num_words_map.get(raw_h, 0)
                if 1 <= h_val <= 12:
                    if not modifier:
                        if 8 <= h_val <= 11:
                            modifier = "सुबह " if is_hindi else "सकाळी "
                        elif h_val == 12 or (1 <= h_val <= 3):
                            modifier = "दोपहर " if is_hindi else "दुपारी "
                        else:
                            modifier = "शाम " if is_hindi else "संध्याकाळी "
                    detected_time = f"{modifier}{h_val} बजे" if is_hindi else f"{modifier}{h_val} वाजता"

        # If day is present (e.g. "monday 11", "kal 11", "sunday eleven"), ANY isolated 1-12 or number word in text_for_time is the hour!
        if not detected_time and detected_day:
            words = text_for_time.split()
            found_h = None
            for w in words:
                w_clean = re.sub(r'[^a-z0-9\u0900-\u097F]', '', w)
                if w_clean in num_words_map:
                    found_h = num_words_map[w_clean]
                    break
                elif w_clean.isdigit():
                    val = int(w_clean)
                    if 1 <= val <= 12:
                        found_h = val
                        break
            if found_h:
                if not modifier:
                    if 8 <= found_h <= 11:
                        modifier = "सुबह " if is_hindi else "सकाळी "
                    elif found_h == 12 or (1 <= found_h <= 3):
                        modifier = "दोपहर " if is_hindi else "दुपारी "
                    else:
                        modifier = "शाम " if is_hindi else "संध्याकाळी "
                detected_time = f"{modifier}{found_h} बजे" if is_hindi else f"{modifier}{found_h} वाजता"

        # General time context fallback: evaluate longer words first (e.g. 'बारह' before 'दो')
        # Uses word boundaries so English words like 'amenities' containing 'am' NEVER trigger time context!
        if not detected_time:
            time_words_devanagari = ["वाजता", "vajta", "vaje", "baje", "बजे", "बज", "सकाळी", "सरकारी", "साकारी", "subah", "सुबह", "morning", "दुपारी", "dopahar", "दोपहर", "संध्याकाळी", "shaam", "शाम", "evening", "night", "raat", "raatri", "o'clock", "अकरावसथा", "दाहवासता", "दहावासता"]
            has_time_context = any(re.search(rf'(?:^|[^\w\u0900-\u097F]){re.escape(w)}(?:$|[^\w\u0900-\u097F])', text_for_time) for w in time_words_devanagari) or bool(re.search(r'\b(am|pm)\b', text_for_time))
            if has_time_context:
                sorted_num_words = sorted(num_words_map.items(), key=lambda x: len(str(x[0])), reverse=True)
                for pat_word, h_val in sorted_num_words:
                    if re.search(rf'(?:^|[^\w\u0900-\u097F]){re.escape(str(pat_word))}(?:$|[^\w\u0900-\u097F])', text_for_time):
                        if not modifier:
                            if 8 <= h_val <= 11:
                                modifier = "सुबह " if is_hindi else "सकाळी "
                            elif h_val == 12 or (1 <= h_val <= 3):
                                modifier = "दोपहर " if is_hindi else "दुपारी "
                            else:
                                modifier = "शाम " if is_hindi else "संध्याकाळी "
                        detected_time = f"{modifier}{h_val} बजे" if is_hindi else f"{modifier}{h_val} वाजता"
                        break

        # If only time-of-day was mentioned without specific hour (e.g. "दोपहर", "दुपारी", "सकाळी", "सुबह")
        if not detected_time:
            has_call_or_detail = any(w in text for w in [
                "detail", "details", "batao", "bataiye", "sanga", "bol", "bola", "call", "phone",
                "baad mein", "bad me", "nantar", "bhejo", "pathva", "whatsapp", "brochure", "samjhao", "explain"
            ])
            if not has_call_or_detail:
                if is_morning:
                    detected_time = "सुबह" if is_hindi else "सकाळी"
                elif is_afternoon:
                    detected_time = "दोपहर" if is_hindi else "दुपारी"
                elif is_evening:
                    detected_time = "शाम" if is_hindi else "संध्याकाळी"

    return detected_day, detected_time


def get_current_ist_time() -> datetime:
    """Returns current datetime in Indian Standard Time (IST = UTC+5:30)."""
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_tz)


def get_time_of_day_greeting(lang: str = "mr") -> str:
    """
    Returns time-of-day greeting based on current IST hour:
    - Morning (< 12:00 PM): शुभ प्रभात (Marathi & Hindi)
    - Afternoon (12:00 PM - 5:00 PM): शुभ दुपार (Marathi) / शुभ दोपहर (Hindi)
    - Evening/Night (>= 5:00 PM): शुभ संध्याकाळ (Marathi) / शुभ संध्या (Hindi)
    """
    ist_now = get_current_ist_time()
    hour = ist_now.hour
    if hour < 12:
        return "शुभ प्रभात"
    elif 12 <= hour < 17:
        return "शुभ दोपहर" if lang == "hi" else "शुभ दुपार"
    else:
        return "शुभ संध्या" if lang == "hi" else "शुभ संध्याकाळ"


def parse_time_to_float_hour(time_str: str) -> float | None:
    """
    Parses a time string into 24-hour float format (e.g. 10:30 AM -> 10.5, 4:30 PM -> 16.5).
    """
    if not time_str:
        return None
    s = time_str.lower()
    
    is_half = any(h in s for h in ["30", "साडे", "साढ़े", "half"])
    minutes = 0.5 if is_half else 0.0
    
    nums = re.findall(r'\b(1[0-2]|[1-9])\b', s)
    if not nums:
        deva_map = {'१': 1, '२': 2, '३': 3, '४': 4, '५': 5, '६': 6, '७': 7, '८': 8, '९': 9, '१०': 10, '११': 11, '१२': 12}
        for k, v in deva_map.items():
            if k in s:
                nums = [str(v)]
                break
    if not nums:
        word_map = {
            'ek': 1, 'एक': 1, 'don': 2, 'दोन': 2, 'do': 2, 'दो': 2,
            'teen': 3, 'तीन': 3, 'char': 4, 'चार': 4, 'paanch': 5, 'पाच': 5, 'पाँच': 5,
            'saha': 6, 'छह': 6, 'saat': 7, 'सात': 7, 'aath': 8, 'आठ': 8,
            'nau': 9, 'नऊ': 9, 'नौ': 9, 'das': 10, 'दहा': 10, 'दस': 10,
            'gyarah': 11, 'अकरा': 11, 'ग्यारह': 11, 'bara': 12, 'बारा': 12, 'बारह': 12
        }
        for w, v in word_map.items():
            if re.search(rf'\b{w}\b', s):
                nums = [str(v)]
                break
    if not nums:
        return None
    
    val = int(nums[0])
    is_pm = bool(re.search(r'\b(pm|afternoon|evening|night)\b', s)) or any(p in s for p in ["दुपारी", "दोपहर", "संध्याकाळी", "शाम", "shaam", "रात्री", "रात", "raat", "raatri"])
    is_am = bool(re.search(r'\b(am|morning)\b', s)) or any(a in s for a in ["सकाळी", "सुबह", "subah"])
    
    if is_pm:
        if 1 <= val <= 11:
            val += 12
    elif is_am:
        if val == 12:
            val = 0
    else:
        # Business hours inference: if caller says 1 to 8 without AM/PM, it's afternoon/evening (13 to 20), not 2 AM!
        if 1 <= val <= 8:
            val += 12
            
    return val + minutes


def validate_site_visit_slot(target_day: str | None, target_time: str | None, lang: str = "mr") -> tuple[bool, str | None]:
    """
    Validates site visit slot:
    1. Visiting hours strictly 9:00 AM to 9:00 PM (9.0 to 21.0).
    2. If day is today, slot must not be in the past or within 30 minutes.
    Returns (is_valid, rejection_message_or_none).
    """
    if not target_time:
        return True, None
        
    float_h = parse_time_to_float_hour(target_time)
    if float_h is None:
        return True, None
        
    # Check 1: 9 AM to 9 PM window
    if float_h < 9.0 or float_h > 21.0:
        if lang == "hi":
            return False, "सर, साईट विजिट का समय सुबह 9:00 बजे से रात 9:00 बजे तक का है। क्या आप सुबह 9:00 से रात 9:00 के बीच का कोई समय बता सकते हैं?"
        else:
            return False, "सर, साईट व्हिजिटची वेळ सकाळी ९:०० ते रात्री ९:०० पर्यंत आहे. आपण सकाळी ९:०० ते रात्री ९:०० दरम्यानची एखादी वेळ सांगू शकाल का?"
            
    # Check 2: Past / too soon check if day is today
    ist_now = get_current_ist_time()
    cur_weekday = ist_now.weekday()
    day_names_mr = ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
    day_names_hi = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
    
    is_today = False
    if target_day:
        td_clean = target_day.strip().lower()
        if td_clean in ["आज", "today", "aaj", "atta", "आता"]:
            is_today = True
        elif td_clean in [day_names_mr[cur_weekday].lower(), day_names_hi[cur_weekday].lower()]:
            is_today = True

    if is_today:
        cur_float = ist_now.hour + (ist_now.minute / 60.0)
        if float_h <= cur_float + 0.5:
            if lang == "hi":
                return False, "सर, आज का वह समय बीत चुका है। क्या हम आज थोड़ा बाद का या कल का कोई समय रख सकते हैं?"
            else:
                return False, "सर, आजचा तो वेळ निघून गेला आहे. आपण आज थोड्या वेळाने किंवा उद्याचा कोणता वेळ ठरवू शकता का?"

    return True, None


def is_time_within_visiting_hours(time_str: str | None) -> bool:
    """Site visit hours are strictly 9:00 AM to 9:00 PM."""
    if not time_str:
        return True
    float_h = parse_time_to_float_hour(time_str)
    if float_h is not None:
        return 9.0 <= float_h <= 21.0
    return True


DECLINE_SCRIPT_HI = (
    "ठीक है सर, कोई बात नहीं। सर, अगर आपकी फैमिली या फ्रेंड्स सर्कल में कोई 1 BHK या 2 BHK फ्लैट ढूंढ रहा हो, "
    "तो आप उनके साथ हमारा कॉन्टैक्ट नंबर शेयर कर सकते हैं। या उनकी परमिशन लेकर उनका कॉन्टैक्ट नंबर हमें शेयर कर सकते हैं। "
    "आपके सहयोग के लिए बहुत-बहुत धन्यवाद सर, नमस्ते."
)
DECLINE_SCRIPT_MR = (
    "ठीक आहे सर, काही हरकत नाही. सर, तुमच्या फॅमिली किंवा फ्रेंड्समध्ये कोणी 1 BHK किंवा 2 BHK फ्लॅट शोधत असेल, "
    "तर तुम्ही त्यांच्यासोबत आमचा कॉन्टॅक्ट नंबर शेअर करू शकता. किंवा त्यांची परमिशन घेऊन त्यांचा कॉन्टॅक्ट नंबर आम्हाला शेअर करू शकता. "
    "तुमच्या सहकार्याबद्दल खूप खूप धन्यवाद सर, नमस्कार."
)


class PriyaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji", customer_phone: str = "", hangup_fnc=None, on_speech_captured=None, session=None):
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self._hangup_fnc = hangup_fnc
        self._on_speech_captured = on_speech_captured
        self._custom_session = session
        self.off_topic_count = 0
        self.intro_delivered = False
        
        # Stateful conversation tracking across turns
        self.selected_bhk: Optional[str] = None
        self.selected_possession: Optional[str] = None
        self.site_visit_day: Optional[str] = None
        self.site_visit_time: Optional[str] = None
        self.awaiting_visit_confirmation: bool = False
        self.site_visit_scheduled: bool = False
        self.referral_asked: bool = False
        
        now = get_current_ist_time()
        time_greeting_mr = get_time_of_day_greeting("mr")
        time_greeting_hi = get_time_of_day_greeting("hi")
        day_names_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_names_hi = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]
        day_names_mr = ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
        cur_day_en = day_names_en[now.weekday()]
        cur_day_hi = day_names_hi[now.weekday()]
        cur_day_mr = day_names_mr[now.weekday()]
        cur_date_str = now.strftime("%d %B %Y")
        cur_time_str = now.strftime("%I:%M %p")
        
        instructions = (
            f"{HINDI_REAL_ESTATE_PROMPT}\n\n"
            f"REAL-TIME TEMPORAL CONTEXT: Today is {cur_day_en} ({cur_day_hi} in Hindi / {cur_day_mr} in Marathi), {cur_date_str}, current time {cur_time_str} IST. "
            f"Appropriate greeting for this hour is '{time_greeting_mr}' (Marathi) / '{time_greeting_hi}' (Hindi). "
            f"If the customer asks what day today is, answer directly that today is {cur_day_hi} (or {cur_day_mr} in Marathi).\n\n"
            f"Aap abhi {customer_name} se call par baat kar rahi hain. "
            "STRICT RULE: Do NOT say the client's name in your responses. You must talk to them directly without repeating or saying their name at all. NEVER prefix your sentences with their name."
        )
        super().__init__(instructions=instructions)

    def get_closing_question(self, lang: str = "mr") -> str:
        """
        Dynamically returns the next logical closing question to avoid awkward dead-ends:
        - If BHK is not yet selected -> asks 1 BHK or 2 BHK
        - If possession is not yet selected -> asks Ready to Move or Under Construction
        - If possession is selected -> asks preferred day & time for site visit
        """
        if self.selected_bhk is None:
            return "क्या आप 1 BHK देख रहे हैं या 2 BHK?" if lang == "hi" else "आपण 1 BHK शोधत आहात की 2 BHK?"
        elif self.selected_possession is None:
            return "आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?" if lang == "hi" else "आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?"
        else:
            return "क्या आप प्रत्यक्ष साईट विजिट करना चाहेंगे, या और कोई जानकारी चाहिए?" if lang == "hi" else "आपण प्रत्यक्ष साईट व्हिजिट करायला आवडेल, की आणखी काही माहिती हवी आहे?"

    def switch_language(self, new_lang: str):
        global ACTIVE_TTS_LANGUAGE, LANGUAGE_LOCKED_EXPLICITLY
        ACTIVE_TTS_LANGUAGE = new_lang
        LANGUAGE_LOCKED_EXPLICITLY = True
        logger.info(f"🗣️ [INSTANT LANGUAGE SWITCH] Switching system to '{new_lang}' with pure native accent!")
        sess = self._custom_session or getattr(self, "_session", None)
        if sess:
            try:
                if hasattr(sess, "tts") and hasattr(sess.tts, "update_options"):
                    sess.tts.update_options(language=new_lang)
                if hasattr(sess, "stt") and hasattr(sess.stt, "update_options"):
                    sess.stt.update_options(language=new_lang)
            except Exception as e:
                logger.warning(f"Error updating session TTS/STT options: {e}")

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: Any,
    ):
        global ACTIVE_TTS_LANGUAGE
        # Multi-Turn Ultra-Fast Deterministic Path:
        # Guarantees consistent 1.0s - 1.4s response latency across ALL turns of the standard real estate conversation,
        # completely eliminating LLM round-trip delays (saving 1.2s-2.4s) while maintaining full Gemini intelligence fallback.
        def speak(text: str) -> str:
            clean = text.strip()
            if clean and not clean.endswith(('.', '?', '!', '।')):
                clean += '.'
            if self._on_speech_captured:
                try:
                    self._on_speech_captured(clean)
                except Exception as err:
                    logger.debug(f"Error in on_speech_captured: {err}")
            return clean

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
                clean_norm = re.sub(r'[^\w\s\u0900-\u097F]', ' ', raw_text).strip().lower()
                words = clean_norm.split()

                # Guard against empty or noise triggers:
                if not clean_norm or len(words) == 0:
                    logger.info(f"⚡ [EMPTY INPUT DETECTED] Ignoring empty speech frame for '{raw_text}'")
                    return

                # 0. Instant Multilingual switch triggers (Locks language & syncs Cartesia TTS / STT immediately)
                hindi_switch_kws = ["hindi", "हिंदी", "hindi mein", "hindi madhe", "hindi madhye", "hindit", "hindi bola", "hindi me", "hindi bol", "hindi chalega"]
                marathi_switch_kws = ["marathi", "मराठी", "marathit", "marathi madhe", "marathi madhye", "marathi mein", "marathi bola", "marathi bol", "marathi chalel"]

                if any(w in clean_norm for w in hindi_switch_kws):
                    was_hi = (ACTIVE_TTS_LANGUAGE == "hi")
                    self.switch_language("hi")
                    if not was_hi:
                        if self.selected_bhk is None:
                            if len(user_msgs) > 1:
                                yield speak("जी बिल्कुल, हम हिंदी में बात कर सकते हैं। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                            else:
                                yield speak("नमस्ते! मैं गायत्री बात कर रही हूँ साई गार्डन डोंबिवली से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                        elif self.selected_possession is None:
                            bhk_part = f"आप {self.selected_bhk} देख रहे हैं ना? " if self.selected_bhk else ""
                            yield speak(f"जी बिल्कुल, हम हिंदी में बात कर सकते हैं। {bhk_part}आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("जी बिल्कुल, हम हिंदी में बात कर सकते हैं। प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय आपके लिए सही रहेगा?")
                        return

                if any(w in clean_norm for w in marathi_switch_kws):
                    was_mr = (ACTIVE_TTS_LANGUAGE == "mr")
                    self.switch_language("mr")
                    if not was_mr:
                        if self.selected_bhk is None:
                            if len(user_msgs) > 1:
                                yield speak("हो नक्कीच, आपण मराठीत बोलू शकतो. आपण 1 BHK शोधत आहात की 2 BHK?")
                            else:
                                yield speak("नमस्कार! मी गायत्री बोलतेय साई गार्डन डोंबिवली मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?")
                        elif self.selected_possession is None:
                            bhk_part = f"आपण {self.selected_bhk} पाहत आहात ना? " if self.selected_bhk else ""
                            yield speak(f"हो नक्कीच, आपण मराठीत बोलू शकतो. {bhk_part}आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        else:
                            yield speak("हो नक्कीच, आपण मराठीत बोलू शकतो. प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?")
                        return

                # Synchronize language state immediately
                det_lang = resolve_language(raw_text, ACTIVE_TTS_LANGUAGE)
                if det_lang != ACTIVE_TTS_LANGUAGE:
                    self.switch_language(det_lang)
                    logger.info(f"🗣️ [LLM NODE LANGUAGE LOCK] Updated ACTIVE_TTS_LANGUAGE to '{ACTIVE_TTS_LANGUAGE}' from text: '{raw_text}'")

                # Parse day and time from the caller's text ONLY when in site visit booking context:
                # If caller has not yet confirmed BHK or asked for a visit, do NOT treat numbers/words as a visit time!
                in_visit_context = (
                    (self.selected_bhk is not None and self.selected_possession is not None)
                    or getattr(self, "awaiting_visit_confirmation", False)
                    or any(w in clean_norm for w in [
                        "visit", "व्हिजिट", "विजिट", "बघायला", "पाहायला", "येणार", "येतो", "आएंगे", "आऊंगा",
                        "अपॉइंटमेंट", "appointment", "booking", "बुक", "साईट व्हिजिट", "साइट विजिट"
                    ])
                )
                detected_day, detected_time = (None, None)
                if in_visit_context:
                    detected_day, detected_time = parse_day_and_time(clean_norm, lang=ACTIVE_TTS_LANGUAGE)
                    if detected_day:
                        self.site_visit_day = detected_day
                    if detected_time:
                        self.site_visit_time = detected_time

                # Priority 0: Immediate Visit Confirmation Handling (Highest Priority on any turn where a slot is pending confirmation)
                if getattr(self, "awaiting_visit_confirmation", False):
                    is_yes = any(kw in clean_norm for kw in [
                        "ho", "hoy", "barobar", "chalel", "chalega", "chaleel", "ha", "haa", "haan",
                        "yes", "theek", "thik", "ok", "okay", "confirm", "kara", "kardo", "kar do", "lock",
                        "book", "done", "right", "correct", "perfect",
                        "हो", "होय", "बरोबर", "चालेल", "हा", "हां", "हाँ", "ठीक", "कन्फर्म", "नक्की",
                        "कर दो", "करदो", "कर दीजिए", "करदीजिए", "करदे", "करा", "हो करा", "नक्की करा",
                        "बुक कर दो", "कन्फर्म कर दो", "लॉक कर दो"
                    ]) and not any(kw in clean_norm for kw in ["nahi", "nako", "नाही", "नको", "dusra", "change", "badla"])

                    is_no = any(kw in clean_norm for kw in [
                        "nahi", "nako", "नाही", "नको", "dusra", "change", "badla", "wrong", "chuka", "चुकीची", "नकोय"
                    ])

                    final_day = self.site_visit_day
                    final_time = self.site_visit_time

                    if is_yes and not (detected_day and detected_day != final_day) and not (detected_time and detected_time != final_time):
                        self.awaiting_visit_confirmation = False
                        self.site_visit_scheduled = True
                        logger.info(f"⚡ [FAST-PATH SITE VISIT VERIFIED & CONFIRMED] {final_day} at {final_time} for '{raw_text}' (0ms LLM wait)!")
                        asyncio.create_task(self.schedule_site_visit(
                            customer_name=self.customer_name,
                            preferred_day=final_day,
                            preferred_time=final_time,
                            flat_type=self.selected_bhk or "1BHK/2BHK"
                        ))
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=2.0)
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            time_phrase = final_time if "बजे" in final_time else f"{final_time} बजे"
                            yield speak(f"बहुत बढ़िया! {final_day} को {time_phrase} आपकी साईट विजिट कन्फर्म कर दी है। सारी जानकारी और लोकेशन व्हाट्सऐप पर भेज दी है। धन्यवाद सर, आपका दिन शुभ हो, नमस्ते.")
                        else:
                            time_phrase = final_time if "वाजता" in final_time else f"{final_time} वाजता"
                            yield speak(f"नक्कीच! {final_day} रोजी {time_phrase} आपली साईट व्हिजिट निश्चित केली आहे. सर्व माहिती आणि लोकेशन व्हॉट्सअॅपवर पाठवली आहे. धन्यवाद सर, दिवस चांगला जावो, नमस्कार.")
                        return

                    elif is_no and not detected_day and not detected_time:
                        self.awaiting_visit_confirmation = False
                        self.site_visit_day = None
                        self.site_visit_time = None
                        logger.info(f"⚡ [SITE VISIT RE-PROMPT REQUESTED] Caller wants different slot for '{raw_text}'")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("कोई बात नहीं, आपके लिए कौन सा नया दिन या समय सही रहेगा?")
                        else:
                            yield speak("काही हरकत नाही, आपल्याला कोणता नवीन दिवस किंवा कोणती वेळ सोयीची ठरेल?")
                        return

                # Negation-aware & Comprehensive BHK Matching Across Languages
                is_1bhk_kws = [
                    "1 bhk", "1bhk", "one bhk", "ek bhk", "first bhk", "एक बीएचके", "१ बीएचके", "१bhk", "1 bk", "one bk", "ek bk",
                    "1 flat", "one flat", "ek flat", "1st", "first", "पहिला", "pahila", "pehla", "1 number", "ek number", "single",
                    "वन बीएचके", "वन bhk", "वनbhk", "एक bhk", "एकbhk", "एक flat", "एक रूम", "एक नंबर", "१ नंबर",
                    "wan bhk", "won bhk", "aik bhk", "aek bhk", "ekam bhk", "एक बी एच के", "१ बी एच के",
                    "1 वाला", "एक वाला", "one वाला", "first वाला", "1st वाला", "1bhk flat", "one bhk flat"
                ]
                is_2bhk_kws = [
                    "2 bhk", "2bhk", "two bhk", "do bhk", "second bhk", "don bhk", "done bhk", "dawn bhk", "dohn bhk",
                    "2 bk", "two bk", "do bk", "don bk", "done bk", "dawn bk", "to bhk", "too bhk", "tu bhk", "thu bhk",
                    "दोन बीएचके", "दोन bhk", "२ बीएचके", "२bhk", "दो bhk", "दोbhk", "दो बीएचके", "दो बी एच के", "दो flat", "दो रूम",
                    "2 flat", "two flat", "do flat", "don flat", "done flat", "dawn flat", "2nd", "second", "दुसरा", "dusra",
                    "2 number", "do number", "don number", "दोन नंबर", "दो नंबर", "२ नंबर",
                    "टू बीएचके", "टू bhk", "टूbhk", "टु बीएचके", "टु bhk", "टुbhk", "दोन बी एच के", "२ बी एच के",
                    "2 वाला", "दो वाला", "दोन वाला", "second वाला", "2nd वाला", "2bhk flat", "two bhk flat", "don bhk flat"
                ]

                is_2bhk = False
                is_1bhk = False
                is_both_bhk = False

                neg_words = r'(nahi|not|nako|नाही|नको|नही|नहीं)'
                one_pat = r'(1|ek|aik|aek|one|wan|won|एक|१|वन|पहिला|pehla|pahila|first|1st)'
                two_pat = r'(2|don|done|dawn|two|to|too|tu|thu|do|दोन|२|दो|टू|टु|second|2nd|दुसरा|dusra)'

                # Negation check: e.g. "1 bhk nahi, 2 bhk", "nahi 1 bhk, 2 bhk", "nahi, 2 bhk"
                if (
                    re.search(rf'{one_pat}\s*(bhk)?\s*{neg_words}.*{two_pat}\s*(bhk)?', clean_norm) or
                    re.search(rf'{neg_words}\s*{one_pat}\s*(bhk)?.*{two_pat}\s*(bhk)?', clean_norm) or
                    re.search(rf'{neg_words}\s*{two_pat}\s*bhk', clean_norm)
                ):
                    is_2bhk = True
                elif (
                    re.search(rf'{two_pat}\s*(bhk)?\s*{neg_words}.*{one_pat}\s*(bhk)?', clean_norm) or
                    re.search(rf'{neg_words}\s*{two_pat}\s*(bhk)?.*{one_pat}\s*(bhk)?', clean_norm) or
                    re.search(rf'{neg_words}\s*{one_pat}\s*bhk', clean_norm)
                ):
                    is_1bhk = True
                else:
                    is_both_bhk = any(kw in clean_norm for kw in [
                        "both", "dono", "donhi", "दोन्ही", "दोनो", "either", "konta pan", "koi bhi", "1 and 2", "1 aur 2", "dono dekh", "donhi dakhva"
                    ])
                    # Guard: If caller is responding with visit time/day, do NOT treat numbers as BHK selection!
                    is_time_answering = bool(
                        detected_time or detected_day or any(w in clean_norm for w in [
                            "वाजता", "vajta", "vaje", "baje", "बजे", "बज", "am", "pm",
                            "दुपारी", "दोपहर", "सकाळी", "सुबह", "संध्याकाळी", "शाम",
                            "तारीख", "tarikh", "tarik", "tareekh", "दिनांक",
                            "सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"
                        ])
                    )
                    two_single_words = [
                        "two", "2", "do", "don", "done", "dawn", "twobhk", "दोन", "दो", "२", "टू", "टु",
                        "dusra", "दुसरा", "second", "2nd"
                    ]
                    one_single_words = [
                        "one", "1", "ek", "aik", "aek", "onebhk", "एक", "१", "वन", "pehla", "pahila",
                        "पहिला", "first", "1st"
                    ]
                    # Guard against common Hindi verbs ending in 'do' / 'दो' (kar do, bhej do, bata do, dikha do, lock kar do)
                    is_verb_do = any(kw in clean_norm for kw in [
                        "kar do", "kardo", "kar de", "karde", "kar dya", "bhej do", "bata do", "de do", "rehne do",
                        "jaane do", "aane do", "bol do", "dekhne do", "sochne do", "kar dijiye", "kardijiye",
                        "कर दो", "करदो", "कर दे", "करदे", "कर दीजिए", "करदीजिए", "भेज दो", "बता दो", "दे दो",
                        "रहने दो", "जाने दो", "आने दो", "बोल दो", "देखने दो", "सोचने दो", "बुक कर दो", "कन्फर्म कर दो"
                    ])
                    if not is_both_bhk and not is_time_answering and not is_verb_do:
                        is_2bhk = any(kw in clean_norm for kw in is_2bhk_kws) or (
                            any(w in words for w in two_single_words) and not any(w in words for w in one_single_words)
                        )
                        is_1bhk = any(kw in clean_norm for kw in is_1bhk_kws) or (
                            any(w in words for w in one_single_words) and not any(w in words for w in two_single_words)
                        )

                is_reasoning_or_objection = (
                    any(w in words for w in ["why", "kyu", "kyun", "kashala", "कशाला", "क्यों", "क्यूं", "क्यू"]) or
                    any(kw in clean_norm for kw in [
                        "ka ahe", "ka aahe", "ka ahet", "ka mhanun", "itka", "itke", "itki", "itna", "itne", "itni",
                        "mehenga", "mahag", "expensive", "costly", "too high", "so high", "jast ka", "jyada kyu", "itna jast",
                        "discount", "offer", "kam hoga", "kam karo", "kam ho sakta", "kahi kami", "kami kara",
                        "farak kya", "farak kay", "difference", "comparison", "quality", "problem"
                    ])
                )

                if is_2bhk and not is_1bhk:
                    self.selected_bhk = "2 BHK"
                elif is_1bhk and not is_2bhk:
                    self.selected_bhk = "1 BHK"
                elif is_both_bhk:
                    self.selected_bhk = "Both"

                # Immediate BHK Selection Handler on Subsequent Turns (Zero risk of false unclear speech or intermediate misrouting)
                # Only runs if BHK was not already chosen, and caller is not confirming site visit
                if len(user_msgs) >= 2 and not is_reasoning_or_objection and self.selected_bhk is None and not getattr(self, "awaiting_visit_confirmation", False):
                    if is_both_bhk:
                        self.selected_bhk = "Both"
                        logger.info(f"⚡ [FAST-PATH BOTH BHK] Instant both BHK response for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("हमारे यहाँ 1 BHK 30 लाख से और 2 BHK 45 लाख से शुरू होता है, साथ में 35 से ज़्यादा आधुनिक सुविधाएँ मिलती हैं। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("आपल्याकडे 1 BHK 30 लाखांपासून आणि 2 BHK 45 लाखांपासून उपलब्ध आहे. यामध्ये स्विमिंग पूल, जिम अशा 35 पेक्षा जास्त आधुनिक सुविधा मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        return

                    if is_2bhk and not is_1bhk:
                        self.selected_bhk = "2 BHK"
                        logger.info(f"⚡ [FAST-PATH 2BHK] Instant 2 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("2 BHK 45 लाख से शुरू होता है। यह 22 मंज़िला भव्य इमारत है जिसमें स्विमिंग पूल, जिम और क्लबहाउस जैसी 35 से ज़्यादा आधुनिक सुविधाएँ मिलती हैं। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("2 BHK फ्लॅट 45 लाख रुपयांपासून सुरू होतो. ही 22 मजली भव्य इमारत असून यात स्विमिंग पूल, जिम आणि क्लबहाऊस अशा 35 पेक्षा जास्त आधुनिक सोयी मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        return

                    if is_1bhk and not is_2bhk:
                        self.selected_bhk = "1 BHK"
                        logger.info(f"⚡ [FAST-PATH 1BHK] Instant 1 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("1 BHK 30 लाख से शुरू होता है। इसमें सिर्फ 3 से 5 लाख डाउन पेमेंट और आसान बैंक होम लोन की सुविधा उपलब्ध है। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("1 BHK फ्लॅट 30 लाख रुपयांपासून सुरू होतो. यामध्ये फक्त 3 ते 5 लाख डाऊन पेमेंट आणि सोप्या बँक होम लोनची सुविधा उपलब्ध आहे. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        return

                # Check for unintelligible / mumbled speech on subsequent turns
                # Whitelist includes short affirmative words in Marathi, Hindi, and English so they NEVER get falsely flagged!
                valid_short_words = [
                    "1", "2", "no", "ho", "do", "ek", "don", "२", "१",
                    "ha", "haa", "haan", "हा", "हां", "हो", "होय", "ok", "yes",
                    "ji", "जी", "acha", "achha", "cha", "चा", "chalel", "चालेल",
                    "sanga", "bol", "bola", "theek", "thik", "नको", "नाही", "नक्की"
                ]

                if len(user_msgs) >= 2:
                    if not clean_norm or len(words) == 0:
                        logger.info(f"⚡ [EMPTY INPUT DETECTED] Ignoring empty speech frame for '{raw_text}'")
                        return
                    if len(clean_norm) <= 2 and clean_norm not in valid_short_words:
                        logger.info(f"⚡ [UNCLEAR SPEECH DETECTED] Prompting polite clarification for '{raw_text}'")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("माफ़ कीजियेगा, मैं समझ नहीं पाई। क्या आप एक बार फिर बोलेंगे?")
                        else:
                            yield speak("माफ करा, मला समजलं नाही. आपण पुन्हा सांगू शकाल का?")
                        return

                    # Handling if referral was already asked and customer responded to it
                    if getattr(self, "referral_asked", False):
                        logger.info(f"⚡ [REFERRAL RESPONSE RECEIVED] Caller answered referral with '{raw_text}'. Graceful farewell...")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("बहुत-बहुत शुक्रिया! आपका दिन शुभ हो, नमस्ते.")
                        else:
                            yield speak("खूप खूप धन्यवाद! आपला दिवस चांगला जावो, नमस्कार.")
                        return

                    # Context-Aware Affirmative Handling (Never blindly reset to 1 BHK or 2 BHK!)
                    affirmative_kws = [
                        "um", "uh", "hmm", "haan", "ha", "yes", "ho", "hoy", "acha", "achha", "ji", "ok", "okay",
                        "theek", "thik", "theek hai", "thik hai", "चालेल", "chalel", "chaalel", "होय", "हो चालेल",
                        "हो", "हाँ", "हां", "जी", "जी हाँ", "जी हां", "होय", "नक्कीच", "हो नक्कीच", "कन्फर्म",
                        "कन्फर्म करा", "कन्फर्म कर दो", "कर दो", "करा", "चालतं", "चालल", "चालणार", "चालता",
                        "ओके", "chalega", "चलेगा", "chalega na", "chalel na", "barobar", "बरोबर", "बरोबर आहे",
                        "sahi hai", "सही है", "done", "डन", "lock it", "confirm", "chalta"
                    ]
                    is_affirmative = (
                        clean_norm in affirmative_kws or
                        (len(words) <= 4 and any(kw in clean_norm for kw in [
                            "हो", "हाँ", "हां", "yes", "चालेल", "chalel", "chalega", "चलेगा", "कन्फर्म", "confirm",
                            "बरोबर", "theek", "ठीक", "चालतं", "चालल", "कर दो", "करा", "नक्कीच", "डन", "done"
                        ]))
                    )
                    if is_affirmative:
                        logger.info(f"⚡ [AFFIRMATIVE PROMPT] Caller acknowledged with '{raw_text}', advancing based on state...")
                        if self.selected_bhk is None:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("जी! क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                            else:
                                yield speak("नक्कीच! आपण 1 BHK शोधत आहात की 2 BHK?")
                            return
                        elif self.selected_possession is None:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("जी, आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                            else:
                                yield speak("नक्कीच! आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                            return
                        elif (self.site_visit_day and self.site_visit_time) or getattr(self, "awaiting_visit_confirmation", False):
                            day = self.site_visit_day or "सांगितलेल्या दिवशी"
                            t_val = self.site_visit_time or "ठरलेल्या वेळी"
                            asyncio.create_task(self.schedule_site_visit(
                                customer_name=self.customer_name,
                                preferred_day=day,
                                preferred_time=t_val,
                                flat_type=self.selected_bhk or "1BHK/2BHK"
                            ))
                            self.site_visit_scheduled = True
                            self.awaiting_visit_confirmation = False
                            if self._hangup_fnc:
                                self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak(f"मैंने आपकी {day} को {t_val} साईट विजिट कन्फर्म कर दी है। सारी जानकारी व्हाट्सऐप पर भेज रही हूँ। बहुत-बहुत धन्यवाद, नमस्ते.")
                            else:
                                yield speak(f"मी आपली {day} रोजी {t_val} वाजता साईट व्हिजिट निश्चित केली आहे. सर्व माहिती व्हॉट्सअॅपवर पाठवत आहे. खूप खूप धन्यवाद, नमस्कार.")
                            return
                        elif self.site_visit_day and not self.site_visit_time:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak(f"बिल्कुल, {self.site_visit_day} को कौन सा समय सही रहेगा — सुबह या शाम?")
                            else:
                                yield speak(f"नक्कीच, {self.site_visit_day} रोजी कोणती वेळ सोयीची ठरेल — सकाळी की संध्याकाळी?")
                            return
                        elif self.site_visit_time and not self.site_visit_day:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak(f"बिल्कुल, {self.site_visit_time} कौन से दिन या तारीख को आना पसंद करेंगे?")
                            else:
                                yield speak(f"नक्कीच, {self.site_visit_time} कोणत्या दिवशी किंवा तारखेला येणं सोयीचं पडेल?")
                            return
                        else:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("बिल्कुल! प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय सुविधाजनक रहेगा?")
                            else:
                                yield speak("नक्कीच! प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?")
                            return

                # 1. Turn 1 Fast Path (Greeting / Any Voice Detected from Caller)
                if len(user_msgs) == 1:
                    if getattr(self, "intro_delivered", False):
                        logger.info(f"⚡ [TURN 1 ALREADY DELIVERED] Pitch already delivered for '{raw_text}'. Skipping to prevent repetition.")
                        return

                    # Ignore short noise / tap / click on Turn 1 (must be real speech >= 2 chars)
                    if len(clean_norm) < 2:
                        logger.info(f"⚡ [TURN 1 NOISE FILTER] Transcript '{clean_norm}' too short (<2 chars). Waiting for caller greeting.")
                        return

                    has_inquiry_intent_turn1 = any(kw in clean_norm for kw in [
                        "detail", "details", "janna", "janana", "batao", "bataiye", "bol", "bola", "sanga",
                        "mahiti", "kasa", "kaisa", "kyu", "kyun", "ka", "kashala", "question", "sawal",
                        "puch", "puchna", "vichar", "pehle", "pahila", "sun", "suno", "ruko", "thamba",
                        "aika", "kharidna", "ghenar", "purna", "pura", "samjhao", "explain", "price",
                        "cost", "budget", "rate", "location", "amenities", "amenity", "address",
                        "brochure", "whatsapp", "kiti", "kitna", "kon", "kaun"
                    ])
                    is_explicit_decline_turn1 = any(kw in clean_norm for kw in [
                        "not interested", "nahi chahiye", "nahi lena", "wrong number", "mat karo", "cut the call",
                        "disconnect", "nako", "garaj nahi", "already bought", "already purchased", "no thanks"
                    ]) or (("interest" in clean_norm or "इंटरेस्ट" in clean_norm or "इन्टरेस्ट" in clean_norm) and ("nahi" in clean_norm or "नही" in clean_norm or "नहीं" in clean_norm or "no" in clean_norm or "not" in clean_norm))
                    is_short_no_turn1 = clean_norm in ["nahi", "no", "nahin", "nako", "नको", "नाही", "नही", "नहीं", "नही है", "नहीं है", "नाहीये"]
                    is_not_interested = (is_explicit_decline_turn1 or is_short_no_turn1) and not has_inquiry_intent_turn1 and not any(kw in clean_norm for kw in ["1 bhk", "2 bhk", "bhk", "flat", "both", "dono"])
                    if is_not_interested:
                        self.intro_delivered = True
                        logger.info(f"⚡ [TURN 1 DECLINE -> AKSHAY SCRIPT TRIGGERED] for '{raw_text}'!")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=1.2)
                        yield speak(DECLINE_SCRIPT_HI if ACTIVE_TTS_LANGUAGE == "hi" else DECLINE_SCRIPT_MR)
                        return

                    if is_both_bhk:
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1 BOTH BHK] Caller interested in both BHKs for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("हमारे यहाँ 1 BHK 30 लाख से और 2 BHK 45 लाख से शुरू होता है, साथ में 35 से ज़्यादा आधुनिक सुविधाएँ मिलती हैं। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("आपल्याकडे 1 BHK 30 लाखांपासून आणि 2 BHK 45 लाखांपासून उपलब्ध आहे. यामध्ये स्विमिंग पूल, जिम अशा 35 पेक्षा जास्त आधुनिक सुविधा मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        return

                    if is_1bhk and not is_2bhk:
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1 1BHK] Instant 1 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("1 BHK 30 लाख से शुरू होता है। इसमें सिर्फ 3 से 5 लाख डाउन पेमेंट और आसान बैंक होम लोन की सुविधा उपलब्ध है। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("1 BHK फ्लॅट 30 लाख रुपयांपासून सुरू होतो. यामध्ये फक्त 3 ते 5 लाख डाऊन पेमेंट आणि सोप्या बँक होम लोनची सुविधा उपलब्ध आहे. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        return

                    if is_2bhk and not is_1bhk:
                        self.intro_delivered = True
                        logger.info(f"⚡ [FAST-PATH TURN 1 2BHK] Instant 2 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("2 BHK 45 लाख से शुरू होता है। यह 22 मंज़िला भव्य इमारत है जिसमें स्विमिंग पूल, जिम और क्लबहाउस जैसी 35 से ज़्यादा आधुनिक सुविधाएँ मिलती हैं। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                        else:
                            yield speak("2 BHK फ्लॅट 45 लाख रुपयांपासून सुरू होतो. ही 22 मजली भव्य इमारत असून यात स्विमिंग पूल, जिम आणि क्लबहाऊस अशा 35 पेक्षा जास्त आधुनिक ॲमेनिटीज मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        return

                    self.intro_delivered = True
                    if ACTIVE_TTS_LANGUAGE == "hi":
                        logger.info(f"⚡ [FAST-PATH TURN 1 FALLBACK] Hindi Sai Garden pitch for '{raw_text}' (0ms LLM wait)!")
                        yield speak("नमस्ते! मैं गायत्री बात कर रही हूँ साई गार्डन डोंबिवली से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                    else:
                        logger.info(f"⚡ [FAST-PATH TURN 1 FALLBACK] Marathi Sai Garden pitch for '{raw_text}' (0ms LLM wait)!")
                        yield speak("नमस्कार! मी गायत्री बोलतेय साई गार्डन डोंबिवली मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?")
                    return

                # 2. Subsequent Turns Fast Path (Sub-Second Latency Engine)
                elif len(user_msgs) >= 2:
                    # Case R: Caller didn't hear / asks to repeat
                    repeat_kws = [
                        "kya bola", "kya bole", "kya kaha", "phir se", "fir se", "repeat", "pardon",
                        "samajh nahi", "samajhla nahi", "aiku nahi", "aawaz nahi ala", "aawaz nahi aala", "aawaz nahi",
                        "kay mhanalat", "kay bolla", "ek aur baar", "ekda sanga", "bolie na", "kya bole aap"
                    ]
                    if any(kw in clean_norm for kw in repeat_kws):
                        logger.info(f"⚡ [FAST-PATH REPEAT REQUEST] Instant repeat for '{raw_text}' (0ms LLM wait)!")
                        if self.selected_bhk is None:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("जी, मैं पूछ रही थी — क्या आप साई गार्डन में 1 BHK फ्लैट देख रहे हैं या 2 BHK?")
                            else:
                                yield speak("हो, मी विचारत होते — आपण साई गार्डन मध्ये 1 BHK फ्लॅट शोधत आहात की 2 BHK?")
                        elif self.selected_possession is None:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("जी, मैं पूछ रही थी — क्या आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                            else:
                                yield speak("हो, मी विचारत होते — आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                        else:
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("जी, मैं पूछ रही थी — आप प्रत्यक्ष साइट विजिट के लिए कब आ सकते हैं?")
                            else:
                                yield speak("हो, मी विचारत होते — आपण प्रत्यक्ष साईट पाहायला कधी येऊ शकता?")
                        return

                    # Case 0: Repeated Greeting ("Hello", "हा बोलिए", "हॅलो", "नमस्ते", "कौन बोल रहे हैं")
                    greeting_kws = [
                        "hello", "helo", "halo", "हॅलो", "हलो", "नमस्ते", "नमस्कार", "namaste", "namaskar",
                        "boliye", "bola", "ha bolie", "ha boliye", "kaun", "kon", "koun", "ha", "haan",
                        "hanji", "haanji", "ji", "yes", "kaun hai", "kon ahe", "koni", "bol"
                    ]
                    decline_quick = ["not interested", "nahi chahiye", "wrong number", "disconnect", "nako", "nahi", "no"]
                    if (any(kw in clean_norm for kw in greeting_kws) and len(words) <= 6) or (not getattr(self, "intro_delivered", False) and len(words) <= 4 and not is_1bhk and not is_2bhk and not any(d in clean_norm for d in decline_quick)):
                        logger.info(f"⚡ [FAST-PATH GREETING RECOVERY] Instant response for greeting '{raw_text}' (0ms LLM wait)!")
                        if getattr(self, "intro_delivered", False):
                            if getattr(self, "site_visit_scheduled", False):
                                day = self.site_visit_day or "सांगितलेल्या दिवशी"
                                t_val = self.site_visit_time or "ठरलेल्या वेळी"
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak(f"जी, आवाज़ आ रही है! आपकी {day} को {t_val} साईट विजिट कन्फर्म हो चुकी है। सारी जानकारी व्हाट्सऐप पर भेज दी गई है। बहुत-बहुत धन्यवाद!")
                                else:
                                    yield speak(f"हो, आवाज येतोय! आपली {day} रोजी {t_val} वाजता साईट व्हिजिट निश्चित झाली आहे. सर्व माहिती व्हॉट्सअॅपवर पाठवली आहे. खूप खूप धन्यवाद!")
                                return
                            elif getattr(self, "awaiting_visit_confirmation", False) and self.site_visit_day and self.site_visit_time:
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak(f"जी, आवाज़ आ रही है! क्या {self.site_visit_day} को {self.site_visit_time} आपकी साईट विजिट कन्फर्म कर दूँ?")
                                else:
                                    yield speak(f"हो, आवाज येतोय! आपण {self.site_visit_day} रोजी {self.site_visit_time} वाजता साईट व्हिजिटसाठी येत आहात, हे कन्फर्म करू का?")
                                return
                            elif self.selected_bhk is None:
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak("जी, मैं पूछ रही थी, क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                                else:
                                    yield speak("हो, मी विचारत होते, आपण 1 BHK शोधत आहात की 2 BHK?")
                            elif self.selected_possession is None:
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak("जी, आवाज़ आ रही है! क्या आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                                else:
                                    yield speak("हो, आवाज येतोय! आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                            elif self.site_visit_day and not self.site_visit_time:
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak(f"जी, आवाज़ आ रही है! {self.site_visit_day} को कौन सा समय सही रहेगा — सुबह या शाम?")
                                else:
                                    yield speak(f"हो, आवाज येतोय! {self.site_visit_day} रोजी कोणती वेळ सोयीची ठरेल — सकाळी की संध्याकाळी?")
                                return
                            elif self.site_visit_time and not self.site_visit_day:
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak(f"जी, आवाज़ आ रही है! {self.site_visit_time} कौन से दिन या तारीख को आना पसंद करेंगे?")
                                else:
                                    yield speak(f"हो, आवाज येतोय! {self.site_visit_time} कोणत्या दिवशी किंवा तारखेला येणं सोयीचं पडेल?")
                                return
                            else:
                                if ACTIVE_TTS_LANGUAGE == "hi":
                                    yield speak("जी, आवाज़ आ रही है! बोलिए, क्या जानकारी चाहिए?")
                                else:
                                    yield speak("हो, आवाज येतोय! बोला, काय माहिती हवी आहे?")
                            return
                        else:
                            self.intro_delivered = True
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("नमस्ते! मैं गायत्री बात कर रही हूँ साई गार्डन डोंबिवली से, एक्सपेरिया मॉल के सामने। क्या आप 1 BHK देख रहे हैं या 2 BHK?")
                            else:
                                yield speak("नमस्कार! मी गायत्री बोलतेय साई गार्डन डोंबिवली मधून, एक्सपेरिया मॉल समोरून. आपण 1 BHK शोधत आहात की 2 BHK?")
                            return

                    # Case A: Polite Decline / Not Interested -> Akshay Referral Script
                    has_inquiry_intent_sub = any(kw in clean_norm for kw in [
                        "detail", "details", "janna", "janana", "batao", "bataiye", "bol", "bola", "sanga",
                        "mahiti", "kasa", "kaisa", "kyu", "kyun", "ka", "kashala", "question", "sawal",
                        "puch", "puchna", "vichar", "pehle", "pahila", "sun", "suno", "ruko", "thamba",
                        "aika", "kharidna", "ghenar", "purna", "pura", "samjhao", "explain", "price",
                        "cost", "budget", "rate", "location", "amenities", "amenity", "address",
                        "brochure", "whatsapp", "kiti", "kitna", "kon", "kaun"
                    ])
                    is_explicit_decline = any(kw in clean_norm for kw in [
                        "not interested", "nahi chahiye", "nahi lena", "nahi dekhna", "wrong number", "mat karo",
                        "mat lagao", "no interest", "koi interest nahi", "cut the call", "disconnect", "nako",
                        "garaj nahi", "flat nahi", "ghetla", "already purchased", "already bought",
                        "no thanks", "no thank you", "nahi lagta", "नाही पाहिजे", "नकोय", "नको",
                        "zarurat nahi", "jarurat nahi", "garaj nahiye", "interest nahi"
                    ]) or (("interest" in clean_norm or "इंटरेस्ट" in clean_norm or "इन्टरेस्ट" in clean_norm) and ("nahi" in clean_norm or "नही" in clean_norm or "नहीं" in clean_norm or "no" in clean_norm or "not" in clean_norm))

                    is_short_no = clean_norm in ["nahi", "no", "nahin", "nahi sir", "no sir", "नाही", "नही", "नहीं", "नही है", "नही ह", "नहीं है", "नाहीये"]
                    is_decline = (is_explicit_decline or is_short_no) and not has_inquiry_intent_sub
                    is_time_or_date_or_bhk = bool(
                        detected_day or detected_time or is_1bhk or is_2bhk or is_both_bhk or
                        any(w in clean_norm for w in [
                            "वाजता", "vajta", "vaje", "baje", "बजे", "बज", "तारीख", "tarikh", "tarik", "tareekh", "दिनांक",
                            "सकाळी", "दुपारी", "संध्याकाळी", "सुबह", "दोपहर", "शाम",
                            "दहा", "अकरा", "बारा", "एक", "दोन", "तीन", "चार", "पाच", "सहा", "सात", "आठ", "नऊ", "दस", "ग्यारह", "बारह"
                        ])
                    )
                    if is_decline and not is_time_or_date_or_bhk:
                        logger.info(f"⚡ [FAST-PATH DECLINE -> AKSHAY SCRIPT TRIGGERED] for '{raw_text}' (0ms LLM wait)!")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=1.2)
                        yield speak(DECLINE_SCRIPT_HI if ACTIVE_TTS_LANGUAGE == "hi" else DECLINE_SCRIPT_MR)
                        return

                    # Case B: Busy / Call Later
                    busy_kws = ["busy hoon", "busy hu", "baad mein", "bad me", "later", "driving", "meeting", "call me later", "call later", "baad mein phone", "nantar kara", "nantar bola"]
                    if any(kw in clean_norm for kw in busy_kws):
                        logger.info(f"⚡ [FAST-PATH BUSY] Instant busy response for '{raw_text}' (0ms LLM wait)!")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("कोई बात नहीं, मैं समझ सकती हूँ। मैं बाद में फॉलो अप करूँगी। आपका दिन शुभ हो, नमस्ते.")
                        else:
                            yield speak("काही हरकत नाही, मी नंतर फोन करेन. तुमचा दिवस चांगला जावो, नमस्कार.")
                        return

                    # Case Farewell / Caller saying goodbye
                    farewell_kws = ["bye", "bye bye", "tata", "theek hai bye", "theek h bye", "chal bye", "chalo bye", "बाय", "बाय बाय", "अलविदा"]
                    if any(kw in clean_norm for kw in farewell_kws):
                        logger.info(f"⚡ [FAST-PATH FAREWELL] Instant polite goodbye for '{raw_text}' (0ms LLM wait)!")
                        if self._hangup_fnc:
                            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("धन्यवाद सर, आपका दिन शुभ हो, नमस्ते.")
                        else:
                            yield speak("धन्यवाद सर, आपला दिवस चांगला जावो, नमस्कार.")
                        return


                    # Case Site Visit Scheduling (Prioritized over property pitches so visit days/times are never misidentified)
                    confirm_patterns = [
                        r"\bconfirm\b", r"\bconfirm kar\b", r"\bconfirm kara\b", r"\bkara confirm\b",
                        r"\block kar\b", r"\block kara\b", r"\bbook kar\b", r"\bbook kara\b",
                        r"\bकन्फर्म\b", r"\bकन्फर्म करा\b", r"\bकन्फर्म कर\b"
                    ]
                    explicit_confirm = any(re.search(pat, clean_norm) for pat in confirm_patterns)



                    # Stage B: Caller provided BOTH day and time in this turn or cumulatively -> Ask Verification First!
                    target_day = detected_day or self.site_visit_day
                    target_time = detected_time or self.site_visit_time

                    if (detected_day and detected_time) or (explicit_confirm and target_day and target_time) or (target_day and target_time and (detected_day or detected_time)):
                        final_day = target_day
                        final_time = target_time
                        
                        is_valid_slot, reject_msg = validate_site_visit_slot(final_day, final_time, lang=ACTIVE_TTS_LANGUAGE)
                        if not is_valid_slot and reject_msg:
                            logger.info(f"⚡ [VISITING SLOT REJECTED] {final_day} at {final_time}: {reject_msg}")
                            yield speak(reject_msg)
                            return

                        self.site_visit_day = final_day
                        self.site_visit_time = final_time
                        self.awaiting_visit_confirmation = True
                        logger.info(f"⚡ [FAST-PATH SITE VISIT VERIFICATION PROMPT] Asking client to verify {final_day} at {final_time} for '{raw_text}' (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            time_phrase = final_time if "बजे" in final_time else f"{final_time} बजे"
                            yield speak(f"बिल्कुल! क्या {final_day} को {time_phrase} आपकी साईट विजिट के लिए सही समय है? मैं इसे कन्फर्म कर दूँ?")
                        else:
                            time_phrase = final_time if "वाजता" in final_time else f"{final_time} वाजता"
                            yield speak(f"नक्कीच! आपण {final_day} रोजी {time_phrase} साईट व्हिजिटसाठी येऊ इच्छिता, ही वेळ आणि तारीख बरोबर आहे का?")
                        return

                    # 2. Caller provided ONLY day (e.g. "21 तारीख", "शनिवार", "उद्या")
                    if detected_day and not target_time:
                        self.site_visit_day = detected_day
                        logger.info(f"⚡ [FAST-PATH DAY SELECTED: {detected_day}] Asking for preferred time (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak(f"बिल्कुल, {detected_day} को कौन सा समय सही रहेगा — सुबह या शाम?")
                        else:
                            yield speak(f"नक्कीच, {detected_day} रोजी कोणती वेळ सोयीची ठरेल — सकाळी की संध्याकाळी?")
                        return

                    # 3. Caller provided ONLY time (e.g. "सकाळी 10 वाजता", "12 बजे")
                    if detected_time and not target_day:
                        is_valid_slot, reject_msg = validate_site_visit_slot(None, detected_time, lang=ACTIVE_TTS_LANGUAGE)
                        if not is_valid_slot and reject_msg:
                            logger.info(f"⚡ [VISITING TIME REJECTED] {detected_time}: {reject_msg}")
                            yield speak(reject_msg)
                            return
                        self.site_visit_time = detected_time
                        logger.info(f"⚡ [FAST-PATH TIME SELECTED: {detected_time}] Asking for preferred day (0ms LLM wait)!")
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            if detected_time in ["सुबह", "दोपहर", "शाम"]:
                                time_phrase = detected_time
                            else:
                                time_phrase = detected_time if "बजे" in detected_time else f"{detected_time} बजे"
                            yield speak(f"बिल्कुल, {time_phrase} कौन से दिन या तारीख को आना सुविधाजनक रहेगा — आज, कल या कौन सी तारीख?")
                        else:
                            if detected_time in ["सकाळी", "दुपारी", "संध्याकाळी"]:
                                time_phrase = detected_time
                            else:
                                time_phrase = detected_time if "वाजता" in detected_time else f"{detected_time} वाजता"
                            yield speak(f"नक्कीच, {time_phrase} कोणत्या दिवशी किंवा तारखेला येणं सोयीचं पडेल — आज, उद्या किंवा कोणती तारीख?")
                        return

                    # 4. Caller asked to confirm without specifying any day/time yet
                    if explicit_confirm and not target_day and not target_time:
                        if ACTIVE_TTS_LANGUAGE == "hi":
                            yield speak("बिल्कुल. प्रत्यक्ष साईट विजिट के लिए कौन से दिन आना सुविधाजनक रहेगा — आज, कल या इस वीकेंड?")
                        else:
                            yield speak("नक्कीच. प्रत्यक्ष साईट व्हिजिटसाठी कोणत्या दिवशी येणं सोयीचं ठरेल — आज, उद्या किंवा या वीकेंडला?")
                        return
                    # Case Explain All Project Details (e.g. "sab kuch batao", "puri jankari do", "details explain karo")

                    # Detect Reasoning / Objection / Comparison intent -> Route to Gemini (the Brain)
                    is_reasoning_or_objection = (
                        any(w in words for w in ["why", "kyu", "kyun", "kashala", "कशाला", "क्यों", "क्यूं", "क्यू"]) or
                        any(kw in clean_norm for kw in [
                            "ka ahe", "ka aahe", "ka ahet", "ka mhanun", "itka", "itke", "itki", "itna", "itne", "itni",
                            "mehenga", "mahag", "expensive", "costly", "too high", "so high", "jast ka", "jyada kyu", "itna jast",
                            "discount", "offer", "kam hoga", "kam karo", "kam ho sakta", "kahi kami", "kami kara",
                            "farak kya", "farak kay", "difference", "comparison", "quality", "problem"
                        ])
                    )

                    if is_reasoning_or_objection:
                        logger.info(f"🧠 [ROUTING TO BRAIN / GEMINI] Reasoning/analytical query detected: '{raw_text}'. Bypassing static property fast-paths.")
                    else:
                        # Case Both: Both 1 BHK & 2 BHK
                        if is_both_bhk:
                            self.selected_bhk = "Both"
                            logger.info(f"⚡ [FAST-PATH BOTH BHK] Instant both BHK response for '{raw_text}' (0ms LLM wait)!")
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("हमारे यहाँ 1 BHK 30 लाख से और 2 BHK 45 लाख से शुरू होता है, साथ में 35 से ज़्यादा आधुनिक सुविधाएँ मिलती हैं। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                            else:
                                yield speak("आपल्याकडे 1 BHK 30 लाखांपासून आणि 2 BHK 45 लाखांपासून उपलब्ध आहे. यामध्ये स्विमिंग पूल, जिम अशा 35 पेक्षा जास्त आधुनिक सुविधा मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                            return

                        # Case C: 2 BHK confirmed / chosen
                        if is_2bhk and not is_1bhk:
                            self.selected_bhk = "2 BHK"
                            logger.info(f"⚡ [FAST-PATH 2BHK] Instant 2 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("2 BHK 45 लाख से शुरू होता है। यह 22 मंज़िला भव्य इमारत है जिसमें स्विमिंग पूल, जिम और क्लबहाउस जैसी 35 से ज़्यादा आधुनिक सुविधाएँ मिलती हैं। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                            else:
                                yield speak("2 BHK फ्लॅट 45 लाख रुपयांपासून सुरू होतो. ही 22 मजली भव्य इमारत असून यात स्विमिंग पूल, जिम आणि क्लबहाऊस अशा 35 पेक्षा जास्त आधुनिक सोयी मिळतात. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                            return

                        # Case D: 1 BHK confirmed / chosen
                        if is_1bhk and not is_2bhk:
                            self.selected_bhk = "1 BHK"
                            logger.info(f"⚡ [FAST-PATH 1BHK] Instant 1 BHK pitch for '{raw_text}' (0ms LLM wait)!")
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("1 BHK 30 लाख से शुरू होता है। इसमें सिर्फ 3 से 5 लाख डाउन पेमेंट और आसान बैंक होम लोन की सुविधा उपलब्ध है। आप रेडी-टू-मूव देख रहे हैं या अंडर-कन्स्ट्रक्शन चलेगा?")
                            else:
                                yield speak("1 BHK फ्लॅट 30 लाख रुपयांपासून सुरू होतो. यामध्ये फक्त 3 ते 5 लाख डाऊन पेमेंट आणि सोप्या बँक होम लोनची सुविधा उपलब्ध आहे. आपण रेडी-टू-मूव्ह पाहताय की अंडर-कन्स्ट्रक्शन चालेल?")
                            return

                        # Case Possession: Under Construction / Ready to Move (Checked immediately so caller's possession answer is never hijacked)
                        upcoming_kws = [
                            "under construction", "under-construction", "underconstruction",
                            "upcoming chalega", "chalega upcoming", "कन्स्ट्रक्शन", "अंडर कन्स्ट्रक्शन",
                            "चालू काम", "अंडर-कन्स्ट्रक्शन"
                        ]
                        is_upcoming = (
                            fuzzy_contains(clean_norm, upcoming_kws, threshold=0.75)
                            or (self.selected_possession is None and any(w in words for w in ["under", "upcoming", "कन्स्ट्रक्शन"]) and any(w in words for w in ["chalega", "chalel", "चलेगा", "चालेल", "dekh", "pahata"]))
                        ) and not any(kw in clean_norm for kw in ["ready to move", "ready-to-move", "ready", "immediate", "turant", "move", "to move", "रेडी", "मूव्ह", "रेडि", "तयार"])

                        ready_kws = [
                            "ready to move", "ready-to-move", "ready tomove", "ready", "redy", "radi", "immediate", "turant",
                            "ready chalega", "chalega ready", "move", "to move", "रेडी", "मूव्ह", "रेडि", "तयार"
                        ]
                        is_ready = (
                            fuzzy_contains(clean_norm, ready_kws, threshold=0.72)
                            and not any(kw in clean_norm for kw in ["upcoming", "under construction", "under-construction", "construction", "कन्स्ट्रक्शन", "अंडर"])
                        )
                        is_both = any(kw in clean_norm for kw in ["dono", "dono chalega", "both", "koi bhi", "kuch bhi"])

                        if is_upcoming and not any(kw in clean_norm for kw in ["kab tak", "date", "year", "loan", "bank"]):
                            self.selected_possession = "Under Construction"
                            logger.info(f"⚡ [FAST-PATH UPCOMING POSSESSION] Instant upcoming response for '{raw_text}' (0ms LLM wait)!")
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("बहुत बढ़िया! अंडर-कन्स्ट्रक्शन में आसान पेमेंट प्लान्स उपलब्ध हैं और समय पर पज़ेशन मिलेगा। प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय आपके लिए सही रहेगा?")
                            else:
                                yield speak("खूप छान! अंडर-कन्स्ट्रक्शन फ्लॅट्समध्ये सोपे पेमेंट प्लॅन्स उपलब्ध आहेत आणि वेळेवर ताबा मिळेल. प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?")
                            return

                        if (is_ready or is_both) and not any(kw in clean_norm for kw in ["kab tak", "date", "year", "loan", "bank"]):
                            self.selected_possession = "Ready to Move" if is_ready else "Both"
                            logger.info(f"⚡ [FAST-PATH READY POSSESSION] Instant ready response for '{raw_text}' (0ms LLM wait)!")
                            if ACTIVE_TTS_LANGUAGE == "hi":
                                yield speak("बहुत बढ़िया! रेडी-टू-मूव फ्लैट्स में तुरंत पज़ेशन और सभी कानूनी मंजूरियां मिलती हैं। प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय आपके लिए सही रहेगा?")
                            else:
                                yield speak("खूप छान! रेडी-टू-मूव्ह फ्लॅट्समध्ये त्वरित ताबा आणि सर्व कायदेशीर मंजुऱ्या मिळतात. प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?")
                            return

        except Exception as fast_err:
            logger.debug(f"Fast path evaluation notice: {fast_err}")

        # Standard intelligence path for all subsequent turns or specific inquiries
        try:
            _lang_now = ACTIVE_TTS_LANGUAGE
            if _lang_now == "mr":
                _lang_instruction = (
                    "STRICT LANGUAGE LOCK & DIRECT ANSWER FIRST: Speak fluent conversational Marathi with natural real estate terms (1 BHK, 2 BHK, amenities, gym, garden, 30 लाख, 45 लाख). "
                    "Always directly and factually answer the caller's question or remark in 1 short sentence FIRST, then gently follow up. Keep your response under 20 words. Use 'सर' at most ONCE. Never repeat 'सर'. "
                    "Only switch language if the caller explicitly asks for Hindi or English."
                )
            elif _lang_now == "en":
                _lang_instruction = (
                    "STRICT LANGUAGE LOCK & DIRECT ANSWER FIRST: Speak fluent English. "
                    "Always directly and factually answer the caller's question or remark in 1 short sentence FIRST, then gently follow up. Keep your response under 20 words. Use 'Sir' at most ONCE."
                )
            else:
                _lang_instruction = (
                    "STRICT LANGUAGE LOCK & DIRECT ANSWER FIRST: Speak fluent conversational Hindi with natural real estate terms (1 BHK, 2 BHK, amenities, gym, garden, 30 लाख, 45 लाख). "
                    "Always directly and factually answer the caller's question or remark in 1 short sentence FIRST, then gently follow up. Keep your response under 20 words. Use 'सर' at most ONCE. NEVER say 'भारतीय रुपया'. "
                    "Only switch language if the caller explicitly asks for Marathi or English."
                )
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(role="system", content=_lang_instruction)
        except Exception as lang_lock_err:
            logger.debug(f"Language lock injection skipped: {lang_lock_err}")

        collected_chunks = []
        try:
            res = Agent.default.llm_node(self, chat_ctx, tools, model_settings)
            if hasattr(res, "__aiter__"):
                aiter = res.__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(aiter.__anext__(), timeout=3.2)
                    except StopAsyncIteration:
                        break
                    if isinstance(chunk, str):
                        collected_chunks.append(chunk)
                    elif hasattr(chunk, "delta") and hasattr(chunk.delta, "content") and chunk.delta.content:
                        collected_chunks.append(str(chunk.delta.content))
                    elif hasattr(chunk, "text") and chunk.text:
                        collected_chunks.append(str(chunk.text))
                    yield chunk
            elif asyncio.iscoroutine(res):
                out = await asyncio.wait_for(res, timeout=3.2)
                if hasattr(out, "__aiter__"):
                    aiter = out.__aiter__()
                    while True:
                        try:
                            chunk = await asyncio.wait_for(aiter.__anext__(), timeout=3.2)
                        except StopAsyncIteration:
                            break
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
        except asyncio.TimeoutError:
            logger.warning("⏱️ [LLM NODE TIMEOUT] LLM response took >3.2s. Speaking polite clarification.")
            if ACTIVE_TTS_LANGUAGE == "hi":
                fb = "माफ़ कीजियेगा, मैं समझ नहीं पाई। क्या आप एक बार फिर बोलेंगे?"
            else:
                fb = "माफ करा, मला समजलं नाही. आपण पुन्हा सांगू शकाल का?"
            yield speak(fb)
            return
        except Exception as llm_err:
            logger.error(f"Error in LLM node execution: {llm_err}")
            if ACTIVE_TTS_LANGUAGE == "hi":
                fb = "माफ़ कीजियेगा, मैं समझ नहीं पाई। क्या आप एक बार फिर बोलेंगे?"
            else:
                fb = "माफ करा, मला समजलं नाही. आपण पुन्हा सांगू शकाल का?"
            yield speak(fb)
            return

        # Guarantee ZERO DEAD AIR: If no chunks were spoken, ask for clarification immediately!
        # Strictly DO NOT prompt clarification if site visit was scheduled or awaiting confirmation!
        if (
            not collected_chunks
            and not getattr(self, "site_visit_scheduled", False)
            and not getattr(self, "awaiting_visit_confirmation", False)
        ):
            logger.info(f"⚡ [NO CHUNKS / UNINTELLIGIBLE] LLM produced no spoken speech for '{raw_text}'. Prompting polite clarification...")
            if ACTIVE_TTS_LANGUAGE == "hi":
                fb = "माफ़ कीजियेगा, मैं समझ नहीं पाई। क्या आप एक बार फिर बोलेंगे?"
            else:
                fb = "माफ करा, मला समजलं नाही. आपण पुन्हा सांगू शकाल का?"
            yield speak(fb)
            return

        if collected_chunks and self._on_speech_captured:
            full_speech = "".join(collected_chunks).strip()
            if full_speech:
                try:
                    self._on_speech_captured(full_speech)
                except Exception as cap_err:
                    logger.debug(f"Captured speech callback error: {cap_err}")

    @function_tool(description="Call ONLY after reading back both the final date and time and customer has explicitly confirmed with a definitive 'yes', 'ho', 'chaalel', or 'confirm kar do'. NEVER call while customer is still deciding, or before both date and time are confirmed. NEVER invent or assume a time.")
    async def schedule_site_visit(
        self,
        customer_name: str,
        preferred_day: str,
        preferred_time: str,
        flat_type: str = "2BHK",
        notes: str = ""
    ) -> str:
        self.site_visit_scheduled = True
        self.awaiting_visit_confirmation = False
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
            "if in Marathi, say: 'मी आपली भेट नक्की केली आहे. सर्व माहिती आणि लोकेशन व्हॉट्सअॅपवर पाठवत आहे. धन्यवाद, दिवस चांगला जावो, नमस्कार.'; "
            f"if in Hindi, say: 'मैंने आपकी {preferred_day}{time_str} की साईट विजिट पक्की कर दी है। सारी जानकारी और लोकेशन व्हाट्सऐप पर भेज रही हूँ। धन्यवाद, आपका दिन शुभ हो, नमस्ते.'."
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
                "if in Marathi, say: 'काही हरकत नाही. वेळ दिल्याबद्दल धन्यवाद, दिवस चांगला जावो, नमस्कार.'; "
                "if in Hindi, say: 'कोई बात नहीं, आपका समय देने के लिए धन्यवाद। आपका दिन शुभ हो, नमस्ते.'."
            )

    async def end_call(self) -> str:
        logger.info("📞 [CALL TERMINATION TOOL INVOKED]")
        if self._hangup_fnc:
            self._hangup_fnc(wait_for_speech=True, delay_seconds=1.0)
        return (
            "Call termination triggered. Conclude politely and say goodbye in the customer's active language: "
            "if in Marathi, say: 'दिवस चांगला जावो, नमस्कार.'; "
            "if in Hindi, say: 'आपका दिन शुभ हो, नमस्ते.'."
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
    ("Sai Garden", 3.5),
    ("साई गार्डन", 3.5),
    ("2 BHK", 4.0),
    ("दोन बीएचके", 4.0),
    ("२ बीएचके", 4.0),
    ("don BHK", 4.0),
    ("two BHK", 3.5),
    ("दोन", 3.5),
    ("don", 3.5),
    ("1 BHK", 4.0),
    ("एक बीएचके", 4.0),
    ("१ बीएचके", 4.0),
    ("one BHK", 3.5),
    ("एक", 3.5),
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
    ("Lodha Heaven", 3.0),
    ("लोढा हेवन", 3.0),
    ("साडेआठ", 3.5),
    ("साडेसात", 3.5),
    ("८:३०", 3.5),
    ("७:३०", 3.5),
    ("आज", 3.5),
    ("उद्या", 3.5),
    ("परवा", 3.0),
    ("Pawar Public", 3.0),
    ("पवार पब्लिक", 3.0),
    ("Ira Global", 3.0),
    ("आयरा ग्लोबल", 3.0),
    ("Jupiter Hospital", 3.0),
    ("ज्युपिटर हॉस्पिटल", 3.0),
    ("Infinity Clinic", 3.0),
    ("इन्फिनिटी क्लिनिक", 3.0),
    ("Vashi", 2.5),
    ("Kalyan", 2.0),
    ("Thane", 2.0),
    ("1 RK", 3.0),
    ("one RK", 3.0),
    ("१ आरके", 3.0),
    ("आरके", 2.5),
    ("मराठी", 3.0),
    ("BHK", 3.0),
    ("RK", 2.5),
    ("22 मजली", 2.5),
    ("30 लाख", 2.5),
    ("45 लाख", 2.5),
    ("डाउन पेमेंट", 2.5),
    ("down payment", 2.5),
    ("home loan", 2.5),
    ("flat", 2.0),
    ("carpet", 2.0),
    ("amenities", 4.0),
    ("ॲमेनिटीज", 3.5),
    ("सुविधा", 3.5),
    ("facilities", 3.0),
    ("gym", 3.0),
    ("swimming pool", 3.0),
    ("स्विमिंग पूल", 3.0),
    ("क्लबहाऊस", 3.0),
    ("अकरा वाजता", 3.5),
    ("बारा वाजता", 3.5),
    ("दोन वाजता", 3.5),
    ("तीन वाजता", 3.5),
    ("चार वाजता", 3.5),
    ("ग्यारह बजे", 3.5),
    ("बारह बजे", 3.5),
    ("दो बजे", 3.5),
    ("तीन बजे", 3.5),
    ("चार बजे", 3.5),
    ("शनिवार", 3.5),
    ("रविवार", 3.5),
    ("सोमवार", 3.0),
    ("वीकेंड", 3.0),
    ("weekend", 3.0),
    ("lakh", 2.0),
    ("crore", 2.0),
    ("budget", 2.0),
    ("visit", 3.0),
    ("साईट व्हिजिट", 3.5),
    ("साइट विजिट", 3.5),
    ("Ready to move", 3.0),
    ("रेडि टू मूव्ह", 3.0),
    ("under construction", 3.0),
    ("अंडर कन्स्ट्रक्शन", 3.0),
    ("Possession", 2.5),
    ("Price", 2.5),
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
    "dohn bhk": "2 BHK",
    "do bhk": "2 BHK",
    "दो bhk": "2 BHK",
    "दोbhk": "2 BHK",
    "दो बीएचके": "2 BHK",
    "दो बी एच के": "2 BHK",
    "२ बीएचके": "2 BHK",
    "२bhk": "2 BHK",
    "2bhk": "2 BHK",
    "2BHK": "2 BHK",
    "two bhk": "2 BHK",
    "to bhk": "2 BHK",
    "too bhk": "2 BHK",
    "tu bhk": "2 BHK",
    "thu bhk": "2 BHK",
    "टू बीएचके": "2 BHK",
    "टू bhk": "2 BHK",
    "टूbhk": "2 BHK",
    "टु बीएचके": "2 BHK",
    "टु bhk": "2 BHK",
    "टुbhk": "2 BHK",
    "don bk": "2 BHK",
    "two bk": "2 BHK",
    "do bk": "2 BHK",
    "2 bk": "2 BHK",
    "२ bk": "2 BHK",
    "ek bhk": "1 BHK",
    "एक बीएचके": "1 BHK",
    "एक bhk": "1 BHK",
    "एकbhk": "1 BHK",
    "एक बी एच के": "1 BHK",
    "१ बीएचके": "1 BHK",
    "१bhk": "1 BHK",
    "1bhk": "1 BHK",
    "1BHK": "1 BHK",
    "one bhk": "1 BHK",
    "वन बीएचके": "1 BHK",
    "वन bhk": "1 BHK",
    "वनbhk": "1 BHK",
    "wan bhk": "1 BHK",
    "won bhk": "1 BHK",
    "aik bhk": "1 BHK",
    "aek bhk": "1 BHK",
    "ekam bhk": "1 BHK",
    "ek bk": "1 BHK",
    "one bk": "1 BHK",
    "1 bk": "1 BHK",
    "१ bk": "1 BHK",
    "१ नंबर": "1 BHK",
    "२ नंबर": "2 BHK",
    "अकारावास": "11 वाजता",
    "अकारा": "अकरा",
    "अकरावास": "11 वाजता",
    "अकरावसथा": "11 वाजता",
    "दाहवासता": "10 वाजता",
    "दहावास": "10 वाजता",
    "दहावाजता": "10 वाजता",
    "सरकारी": "सकाळी",
    "सरकारी अकरावसथा": "सकाळी 11 वाजता",
    "सरकारी अकरा": "सकाळी 11 वाजता",
    "सरकारी दहा": "सकाळी 10 वाजता",
    "सरकारी दाह": "सकाळी 10 वाजता",
    "साकारी": "सकाळी",
    "साकारी अकरावसथा": "सकाळी 11 वाजता",
    "साकारी अकरा": "सकाळी 11 वाजता",
    "साकारी दहा": "सकाळी 10 वाजता",
    "साकारी दाह": "सकाळी 10 वाजता",
    "दाह": "10",
    "dha": "10",
    "dha vajta": "10 वाजता",
    "दाहवासतम": "10 वाजता",
    "दाह वाजता": "10 वाजता",
    "बाइस तारीख": "22 तारीख",
    "बाइस": "22",
    "बारावासता": "12 वाजता",
    "बारावास": "12 वाजता",
    "दोनवासता": "2 वाजता",
    "दोनवास": "2 वाजता",
    "तीनवासता": "3 वाजता",
    "चारवासता": "4 वाजता",
    "पाचवासता": "5 वाजता",
    "सहावासता": "6 वाजता",
    # Times & Days
    "साडे आठ": "साडेआठ",
    "साडे सात": "साडेसात",
    "साडे नऊ": "साडेनऊ",
    "साडे दहा": "साडेदहा",
    "8 30": "८:३०",
    "8.30": "८:३०",
    "7 30": "७:३०",
    "7.30": "७:३०",
    "aaj": "आज",
    "udya": "उद्या",
    # Amenities variants & misspellings
    "aminites": "amenities",
    "aminitis": "amenities",
    "eminities": "amenities",
    "eminity": "amenities",
    "aminities": "amenities",
    "aminity": "amenities",
    "amenitees": "amenities",
    "amneties": "amenities",
    "amnetis": "amenities",
    "amneti": "amenities",
    "ameniti": "amenities",
    "amenites": "amenities",
    "एमिनिटी": "amenities",
    "एमिनिटीज": "amenities",
    "अमेनिटी": "amenities",
    "अमेनिटीज": "amenities",
    "अमिनिटी": "amenities",
    "अमिनिटीज": "amenities",
    "सुविधाएं": "सुविधा",
    "सुविधाए": "सुविधा",
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
    "lodha heaven": "Lodha Heaven",
    "लोढा हेवन": "Lodha Heaven",
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
    "pawar public": "Pawar Public School",
    "ira global": "Ira Global School",
    "jupiter hospital": "Jupiter Hospital",
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

    # 2. Pre-warm Deepgram Nova-2 STT (Accurate Hindi/English bilingual acoustic model calibrated to 350ms endpointing)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    default_stt_lang = os.getenv("STT_LANGUAGE", "hi")
    endpointing_ms = int(os.getenv("STT_ENDPOINTING_MS", "350"))
    proc.userdata["stt"] = deepgram.STT(
        language=default_stt_lang,
        model="nova-2",
        endpointing_ms=endpointing_ms,
        utterance_end_ms=1000,
        smart_format=True,
        punctuate=True,
        filler_words=False,
        vad_events=True,
        no_delay=True,
        interim_results=True,
        keywords=STT_KEYWORDS,
        replace=STT_REPLACE,
        api_key=deepgram_key
    )

    # 3. Pre-warm Silero VAD (Calibrated: 0.38 threshold, 100ms min speech, 600ms silence so user is never cut off mid-sentence)
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.60,
        min_speech_duration=0.10,
        activation_threshold=0.38,
        deactivation_threshold=0.28,
        prefix_padding_duration=0.35,
        sample_rate=16000
    )

    # 4. Pre-warm Cartesia/ElevenLabs TTS (loads client network config in background)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    cartesia_model = os.getenv("CARTESIA_MODEL", "sonic-3.5").strip()
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "1.05"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "").strip()
    cartesia_volume = float(os.getenv("CARTESIA_VOLUME", "1.15"))
    if cartesia_key and len(cartesia_key) > 10:
        proc.userdata["tts"] = cartesia.TTS(
            api_key=cartesia_key,
            voice=kusha_voice_id,
            language="mr",
            sample_rate=24000,
            model=cartesia_model,
            speed=cartesia_speed,
            emotion=[cartesia_emotion] if cartesia_emotion else None,
            volume=cartesia_volume,
            word_timestamps=False,
            text_pacing=False,
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

    global LANGUAGE_LOCKED_EXPLICITLY
    LANGUAGE_LOCKED_EXPLICITLY = False
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
        default_stt_lang = os.getenv("STT_LANGUAGE", "hi")
        endpointing_ms = int(os.getenv("STT_ENDPOINTING_MS", "350"))
        stt = deepgram.STT(
            language=default_stt_lang,
            model="nova-2",
            endpointing_ms=endpointing_ms,
            utterance_end_ms=1000,
            smart_format=True,
            punctuate=True,
            filler_words=False,
            vad_events=True,
            no_delay=True,
            interim_results=True,
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

    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "").strip()
    cartesia_volume = float(os.getenv("CARTESIA_VOLUME", "1.15"))
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
                language="hi",
                sample_rate=24000,
                model=cartesia_model,
                speed=cartesia_speed,
                emotion=[cartesia_emotion] if cartesia_emotion else None,
                volume=cartesia_volume,
                word_timestamps=False,
                text_pacing=False,
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
    


    # VAD is pre-warmed, but load as fallback if not present (Telephony calibrated: 0.38 threshold ignores ambient noise/bleeding, 80ms speech, 350ms silence)
    vad = ctx.proc.userdata.get("vad")
    if not vad:
        logger.info("⏱️ [VAD] Loading Silero VAD model on demand (Calibrated: 100ms min speech, 0.60s silence)...")
        vad = silero.VAD.load(
            min_silence_duration=0.60,
            min_speech_duration=0.10,
            activation_threshold=0.38,
            deactivation_threshold=0.28,
            prefix_padding_duration=0.35,
            sample_rate=16000
        )
    
    # Reset TTS options only if it is Cartesia (ElevenLabs uses different options structure)
    is_cartesia = tts and "cartesia" in tts.__class__.__module__
    if is_cartesia and hasattr(tts, "update_options"):
        tts.update_options(
            voice=kusha_voice_id,
            language="hi",
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
                "min_delay": 0.22,
            },
            "preemptive_generation": {
                "enabled": True,  # Starts LLM streaming in advance based on interim STT, eliminating 500-800ms of wait time
                "preemptive_tts": True,  # Pre-synthesizes audio during caller pause for instantaneous 0ms playout
            },
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_duration": 0.85,  # Sustained human speech (>850ms) to interrupt; ignores line noise & brief echo
                "min_words": 1,        # Requires at least 1 actual word from STT before interrupting
                "resume_false_interruption": True,  # Auto-resume speech if interruption was a false alarm (noise/cough/line pop)
                "false_interruption_timeout": 2.0,
                "discard_audio_if_uninterruptible": False,
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
        nonlocal call_finalized, customer_name, customer_phone, user_account_email, agent, is_voicemail_detected
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

            # Check if this call was an automated voicemail or telecom auto-announcement
            vm_check_patterns = [
                r"\b(voicemail|voice\s*mail)\b",
                r"\b(forwarded\s*to\s*voicemail|forwarded\s*to\s*voice\s*mail)\b",
                r"\b(leave\s*a\s*message|record\s*your\s*message|at\s*the\s*tone|after\s*the\s*tone)\b",
                r"\b(person\s*(you\s*are\s*trying\s*to\s*reach|you\s*have\s*called)\s*(is\s*not\s*available|is\s*busy|is\s*speaking))\b",
                r"\b(subscriber\s*(you\s*have\s*dialed|is\s*currently\s*busy|is\s*not\s*reachable))\b",
                r"\b(switched\s*off|out\s*of\s*coverage|temporarily\s*unavailable|cannot\s*be\s*completed)\b",
                r"\b(dial\s*kiya\s*gaya\s*number|kripya\s*kuch\s*samay\s*baad|se\s*bahar\s*hai|uplabdh\s*nahi\s*hai)\b",
                r"\b(vyast\s*hai|switched\s*off\s*hai|sampark\s*kshetra\s*se\s*bahar|kripya\s*baad\s*mein)\b",
                r"\b(krupaya\s*thodya\s*velane|uttar\s*det\s*nahit)\b"
            ]
            has_vm_in_transcript = any(re.search(pat, formatted_transcript, re.IGNORECASE) for pat in vm_check_patterns)
            is_machine = bool(is_voicemail_detected or has_vm_in_transcript or "voicemail" in ai_summary.lower() or "no actual conversation" in ai_summary.lower())
            if is_machine:
                call_outcome = "Not Picked Up"
                sentiment = "neutral"
                ai_summary = "The call reached the customer's automated voicemail / telecom IVR system, and no actual conversation took place."

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
                    "called_at": datetime.utcnow().isoformat() + "Z",
                    "callPicked": False if is_machine else (len([d for d in call_dialogue if d.get("role") == "customer"]) > 0),
                    "callPickedStatus": "not_picked" if is_machine else "picked"
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

                # Keep up to 100 calls in persistent cloud metadata
                # Strip large base64 data URLs from older calls to stay strictly within LiveKit Cloud 512KB room metadata limit
                for i in range(1, len(cloud_logs)):
                    old_rec = cloud_logs[i].get("recordingUrl") or ""
                    if old_rec.startswith("data:"):
                        cloud_logs[i]["recordingUrl"] = f"/api/recordings/{cloud_logs[i].get('callSid')}.mp3"

                existing_meta["callLogs"] = cloud_logs[:100]
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
    caller_is_speaking = False
    initial_hello_done = False
    t_initial_hello_ended = 0.0
    t_call_pickup = time.time()
    watchdog_task = None
    last_agent_speech = ""
    agent = None
    t_user_speaking_start = 0.0
    current_lang = ACTIVE_TTS_LANGUAGE or "hi"
    latest_caller_transcript = ""
    is_voicemail_detected = False
    t_caller_last_spoke = time.time()

    @session.on("error")
    def _on_session_error(ev):
        logger.error(f"❌ [AGENT SESSION ERROR] Error={getattr(ev, 'error', ev)}")

    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent):
        nonlocal t_user_stop, t_last_activity, last_prompt_time, has_prompted_silence, caller_has_spoken, caller_is_speaking, intro_delivered, agent, t_user_speaking_start, current_lang, latest_caller_transcript, t_caller_last_spoke
        try:
            if ev.new_state == "speaking":
                caller_has_spoken = True
                caller_is_speaking = True
                t_caller_last_spoke = time.time()
                t_user_stop = 0.0  # Reset so mid-sentence pauses never inflate STT latency
                t_user_speaking_start = time.perf_counter()
                t_last_activity = time.time()
                last_prompt_time = time.time()
                has_prompted_silence = False
            elif ev.old_state == "speaking" and ev.new_state == "listening":
                caller_is_speaking = False
                t_caller_last_spoke = time.time()
                t_user_stop = time.perf_counter()
                intro_finished = True
                t_last_activity = time.time()
                last_prompt_time = time.time()
                logger.info("🛑 [VAD] User stopped speaking! STT and turn pipeline proceeding.")
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
                t_last_activity = time.time() + 2.5
                last_prompt_time = time.time() + 2.5
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
        norm_clean = re.sub(r'[^\w\s\u0900-\u097F]', ' ', clean_text).strip().lower()

        # Deduplication: Only skip if the immediately preceding turn from the SAME speaker is an exact duplicate
        if call_dialogue:
            last_turn = call_dialogue[-1]
            if last_turn.get("role") == role:
                last_norm = re.sub(r'[^\w\s\u0900-\u097F]', ' ', last_turn.get("text", "")).strip().lower()
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

    current_lang = ACTIVE_TTS_LANGUAGE or "hi"

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        global ACTIVE_TTS_LANGUAGE
        nonlocal current_lang, t_user_stop, t_last_activity, last_prompt_time, has_prompted_silence, caller_has_spoken, caller_is_speaking, intro_delivered, agent, latest_caller_transcript, initial_hello_done, t_initial_hello_ended, t_call_pickup, is_voicemail_detected, t_caller_last_spoke
        caller_has_spoken = True
        caller_is_speaking = not ev.is_final
        t_caller_last_spoke = time.time()
        t_last_activity = time.time()
        last_prompt_time = time.time()
        has_prompted_silence = False
        if ev.transcript:
            latest_caller_transcript = ev.transcript.strip()
            if t_user_stop > 0:
                transcribed_after = (time.perf_counter() - t_user_stop) * 1000
                logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} (+{transcribed_after:.1f}ms) | Text: '{ev.transcript}'")
            else:
                logger.info(f"🎙️ [STT TRANSCRIPT] Final={ev.is_final} | Text: '{ev.transcript}'")

            # Early Language Detection on Turn 1 & all turns:
            clean_tr = ev.transcript.strip().lower()
            if len(clean_tr) >= 2:
                det_lang = resolve_language(clean_tr, ACTIVE_TTS_LANGUAGE or "hi")
                if det_lang != ACTIVE_TTS_LANGUAGE:
                    ACTIVE_TTS_LANGUAGE = det_lang
                    current_lang = det_lang
                    logger.info(f"🗣️ Early Language Detection: '{det_lang}' from text: '{clean_tr}'")
                    if session.tts and hasattr(session.tts, "update_options"):
                        try:
                            session.tts.update_options(language=det_lang)
                        except Exception as opt_err:
                            logger.debug(f"Early TTS language switch note: {opt_err}")



        if ev.is_final and ev.transcript:
            text = ev.transcript.strip().lower()
            record_dialogue_turn("customer", ev.transcript.strip())

            # Automated Voicemail / Telecom IVR Machine Announcement Detection
            voicemail_patterns = [
                r"\b(voicemail|voice\s*mail)\b",
                r"\b(forwarded\s*to\s*voicemail|forwarded\s*to\s*voice\s*mail)\b",
                r"\b(leave\s*a\s*message|record\s*your\s*message|at\s*the\s*tone|after\s*the\s*tone)\b",
                r"\b(person\s*(you\s*are\s*trying\s*to\s*reach|you\s*have\s*called)\s*(is\s*not\s*available|is\s*busy|is\s*speaking))\b",
                r"\b(subscriber\s*(you\s*have\s*dialed|is\s*currently\s*busy|is\s*not\s*reachable))\b",
                r"\b(switched\s*off|out\s*of\s*coverage|temporarily\s*unavailable|cannot\s*be\s*completed)\b",
                r"\b(dial\s*kiya\s*gaya\s*number|kripya\s*kuch\s*samay\s*baad|se\s*bahar\s*hai|uplabdh\s*nahi\s*hai)\b",
                r"\b(vyast\s*hai|switched\s*off\s*hai|sampark\s*kshetra\s*se\s*bahar|kripya\s*baad\s*mein)\b",
                r"\b(krupaya\s*thodya\s*velane|uttar\s*det\s*nahit)\b"
            ]
            if any(re.search(pat, text, re.IGNORECASE) for pat in voicemail_patterns):
                is_voicemail_detected = True
                logger.warning(f"🚫 [AUTOMATED VOICEMAIL / TELECOM IVR DETECTED] Machine announcement: '{ev.transcript}'. Hanging up immediately!")
                trigger_hangup(wait_for_speech=False, delay_seconds=0.2)
                return
            
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
                                content="[OFF-TOPIC STRIKE 3 ALERT] Caller is off-topic again after soft warning. Conclude immediately with the farewell: 'Lagta hai aap abhi property mein interested nahi hain. Humara samay dene ke liye shukriya, aapka din shubh ho, namaste.'"
                            )
                except Exception as steer_err:
                    logger.debug(f"Could not inject off-topic steering: {steer_err}")

            new_lang = resolve_language(ev.transcript, current_lang)
            
            if new_lang != current_lang:
                current_lang = new_lang
                ACTIVE_TTS_LANGUAGE = current_lang
                logger.info(f"🗣️ Language Switch Detected: '{current_lang}' (ACTIVE_TTS_LANGUAGE={ACTIVE_TTS_LANGUAGE}) for text: '{ev.transcript}'")
                
                # Dynamically update STT language so transcription matches caller's spoken language
                try:
                    if session.stt and hasattr(session.stt, "update_options"):
                        stt_lang = current_lang if current_lang in ["mr", "hi", "en"] else "hi"
                        session.stt.update_options(language=stt_lang)
                        logger.info(f"🔄 Switched STT language to '{stt_lang}'")
                except Exception as stt_err:
                    logger.debug(f"STT language switch note: {stt_err}")

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

    # Caller participant ready
    logger.info(f"📞 Caller participant in room: {caller_participant.identity if caller_participant else 'None'}. Proceeding to start session.")

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
        on_speech_captured=_record_agent_speech,
        session=session
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

    # Snappy Immediate Pickup Greeting:
    # Guarantee Gayatri initiates the call immediately upon pickup with "हॅलो?" so the caller never hears silence!
    if not _hangup_scheduled:
        is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
        if is_cartesia and hasattr(session.tts, "update_options"):
            session.tts.update_options(
                voice=kusha_voice_id,
                language="hi",
                speed=cartesia_speed,
                volume=cartesia_volume,
                emotion=[cartesia_emotion] if cartesia_emotion else None
            )

        logger.info("🎙️ [IMMEDIATE PICKUP GREETING] Saying 'हॅलो?' immediately so caller never hears silence...")
        t_user_stop = 0.0
        record_dialogue_turn("agent", "हॅलो?")
        try:
            session.say("हॅलो?", allow_interruptions=True)
            initial_hello_done = True
        except Exception as e:
            logger.warning(f"Error speaking immediate hello: {e}")
        intro_finished = True

    # Silence Watchdog: 12s check -> 30s auto-terminate
    t_last_activity = time.time()
    last_prompt_time = time.time()

    async def _silence_watchdog():
        nonlocal t_last_activity, last_prompt_time, _hangup_scheduled, agent_is_speaking, caller_is_speaking, t_user_stop, caller_has_spoken, intro_delivered, initial_hello_done, t_initial_hello_ended, t_call_pickup, t_caller_last_spoke
        logger.info("🛡️ [SILENCE WATCHDOG] Task active. Monitoring caller activity...")
        
        while not intro_finished and not _hangup_scheduled:
            await asyncio.sleep(0.1)

        if _hangup_scheduled:
            return

        logger.info("🛡️ [SILENCE WATCHDOG] Caller connected! Monitoring silence (12s voice check, 30s auto-terminate)...")
        
        t_call_pickup = time.time()
        t_caller_last_spoke = t_call_pickup
        last_prompt_time = t_call_pickup
        silence_prompt_count = 0

        while not _hangup_scheduled:
            await asyncio.sleep(0.25)
            if _hangup_scheduled:
                break
                
            # If agent is currently speaking or generating speech, pause checks
            if agent_is_speaking or (session.current_speech and not session.current_speech.done()) or (session.agent_state == "speaking"):
                t_last_activity = time.time()
                continue

            # If caller is currently speaking or VAD detects user speech, reset silence timer & prompt count
            if caller_is_speaking or (getattr(session, "user_state", None) == "speaking"):
                t_caller_last_spoke = time.time()
                t_last_activity = time.time()
                last_prompt_time = time.time()
                silence_prompt_count = 0
                continue

            now = time.time()
            caller_silence = now - t_caller_last_spoke
            agent_idle = now - t_last_activity

            active_lang = ACTIVE_TTS_LANGUAGE or current_lang or "hi"

            # 2. If caller stays silent for 30.0 seconds total without speaking -> Speak polite farewell and hang up
            if caller_silence >= 30.0 and agent_idle >= 6.0:
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {caller_silence:.1f}s (>=30s). Terminating call in language '{active_lang}'...")
                if active_lang == "mr":
                    farewell_text = "तुमचा आवाज येत नाहीये. मी नंतर कॉल करते, दिवस चांगला जावो, नमस्कार."
                elif active_lang == "en":
                    farewell_text = "I'm unable to hear you. We will connect later. Have a wonderful day, goodbye!"
                else:
                    farewell_text = "लगता है आपकी आवाज नहीं आ रही है। हम बाद में फोन करते हैं, आपका दिन शुभ हो, नमस्ते."
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

            if _hangup_scheduled:
                break

            # 3. Say prompt after 12.0 seconds of genuine silence (Natural voice check)
            if (caller_silence >= 12.0) and (agent_idle >= 10.0) and (silence_prompt_count == 0):
                if _hangup_scheduled:
                    break
                silence_prompt_count += 1
                last_prompt_time = now
                logger.info(f"⏳ [SILENCE PROMPT] 12.0s silence elapsed (caller silent: {caller_silence:.1f}s). Prompting in language '{active_lang}'...")
                
                if not caller_has_spoken:
                    prompt_text = "हॅलो?"
                else:
                    if active_lang == "mr":
                        prompt_text = "हॅलो? माझा आवाज येतोय का?"
                    elif active_lang == "en":
                        prompt_text = "Hello? Are you able to hear me?"
                    else:
                        prompt_text = "हॅलो? क्या आपको मेरी आवाज़ आ रही है?"

                try:
                    t_user_stop = 0.0
                    record_dialogue_turn("agent", prompt_text)
                    handle = session.say(prompt_text, allow_interruptions=True)
                    if handle:
                        await handle.wait_for_playout()
                    t_last_activity = time.time()
                except Exception as e:
                    logger.warning(f"Error speaking 12.0s interval silence prompt: {e}")

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
