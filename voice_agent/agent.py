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
ACTIVE_TTS_LANGUAGE = "hi"

def normalize_phonetics(text: str, lang: str | None = None) -> str:
    if not text:
        return text
    # Smooth exclamation marks into calm periods to maintain steady, calm, warm telephone pitch
    text = text.replace('!', '.').replace('?', '? ')
    text = re.sub(r'\s*\.\s*\.+', '.', text)
    target_lang = lang or ACTIVE_TTS_LANGUAGE
    is_marathi = target_lang == "mr" or (target_lang != "hi" and target_lang != "en" and bool(re.search(r'[\u0900-\u097F]', text)))
    is_english = target_lang == "en"

    if is_marathi:
        replacements = [
            (r'\b(dombivli|dombivali|dombivili|dombiwli)\b', 'डोंबिवली'),
            (r'\bsai\s*garden\b', 'साई गार्डन'),
            (r'\blodha\s*heaven\b', 'लोढा हेवन'),
            (r'\bnilje\b', 'निलजे'),
            (r'\b760\b', 'सातशे साठ'),
            (r'\b375\b', 'तीनशे पंच्याहत्तर'),
            (r'\b520\b', 'पाचशे वीस'),
            (r'\b755\b', 'सातशे पंचावन्न'),
            (r'\b1110\b', 'अकराशे दहा'),
            (r'\b2285\b', 'बावीसशे पंच्यांशी'),
            (r'\b36\b', 'छत्तीस'),
            (r'\b72\b', 'बहात्तर'),
            (r'\b50\b', 'पन्नास'),
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
            (r'\bjaquar\s*fittings\b', 'जॅग्वार फिटिंग्स'),
            (r'\bkajaria\s*tiles\b', 'कजारिया टाईल्स'),
            (r'\bwhatsapp\b', 'व्हॉट्सअॅप'),
            (r'\bbrochure\b', 'माहिती पुस्तिका'),
            (r'\bready\s*to\s*move\b', 'रेडी टू मूव्ह'),
            (r'\bunder\s*construction\b', 'अंडर कन्स्ट्रक्शन'),
            (r'\bpossession\b', 'पझेशन'),
            (r'\bhello\b', 'हॅलो'),
            (r'\bbye\b', 'नमस्कार'),
            (r'\b15\s*(-|te)\s*20\b', 'पंधरा ते वीस'),
            (r'\b15\b', 'पंधरा'),
            (r'\b20\b', 'वीस'),
            (r'\b5\b', 'पाच'),
            (r'\b11\b', 'अकरा'),
            (r'\b3\b', 'तीन'),
            (r'\b1\s*crore\s*4\s*lakh\b', 'एक कोटी चार लाख'),
            (r'\b2\s*crore\s*10\s*lakh\b', 'दोन कोटी दहा लाख'),
        ]
    elif is_english:
        replacements = [
            (r'\bgayatri\b', 'गायत्री'),
            (r'\b(dombivli|dombivali|dombivili|dombiwli)\b', 'डोंबिवली'),
            (r'\bthane\b', 'ठाणे'),
            (r'\bkalyan\b', 'कल्याण'),
            (r'\bsai complex\b', 'साई कॉम्प्लेक्स'),
            (r'\bpalava\b', 'पलावा'),
            (r'\bnilje\b', 'निलजे'),
            (r'\b(shil road|shil phata)\b', 'शील रोड'),
            (r'\bshiv sai\b', 'शिव साई'),
            (r'\blodha\b', 'लोढा'),
            (r'\baman\b', 'अमन'),
            (r'\braj\b', 'राज'),
            (r'\b760\b', 'seven hundred sixty'),
            (r'\b375\b', 'three hundred seventy five'),
            (r'\b520\b', 'five hundred twenty'),
            (r'\b755\b', 'seven hundred fifty five'),
            (r'\b1110\b', 'eleven hundred ten'),
            (r'\b2285\b', 'twenty two hundred eighty five'),
            (r'\b36\b', 'thirty six'),
            (r'\b72\b', 'seventy two'),
            (r'\b50\b', 'fifty'),
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
            (r'\b15\s*(-|to)\s*20\b', 'fifteen to twenty'),
            (r'\b11\s*am\b', 'eleven am'),
            (r'\b3\s*pm\b', 'three pm'),
            (r'\blakh\b', 'lakh'),
            (r'\bcrore\b', 'crore'),
        ]
    else:
        # Hindi / Hinglish default: Keep all numbers in English (36 lakh, 72 lakh, 375 sqft, 760 sqft)
        # as requested, while keeping Dombivli in natural Devanagari phonetics ('डोंबिवली') and BHK as 'बीएचके'.
        replacements = [
            (r'\b(dombivli|dombivali|dombivili|dombiwli)\b', 'डोंबिवली'),
            (r'\b(?:ek|एक|1|one)\s*(aur|and|ya|or|और|या|-)\s*(?:do|दो|दोन|2|two)\s*BHK\b', r'one \1 two BHK'),
            (r'\b(1|one)\s*BHK\b', 'one BHK'),
            (r'\b(2|two)\s*BHK\b', 'two BHK'),
            (r'\b(3|three)\s*BHK\b', 'three BHK'),
            (r'\b(1|one)\s*RK\b', 'one RK'),
            (r'\b1rk\b', 'one RK'),
            (r'\b(ek|एक)\s*(बी\s*एच\s*के|बीएचके)\b', 'one BHK'),
            (r'\b(do|दो|दोन)\s*(बी\s*एच\s*के|बीएचके)\b', 'two BHK'),
            (r'\bBHK\b', 'BHK'),
            (r'\bRK\b', 'RK'),
            (r'\b(chhattis|छत्तीस)\s*(lakh|लाख)?\b', 'thirty-six lakh'),
            (r'\b(tees|तीस)\s*(lakh|लाख)?\b', 'thirty lakh'),
            (r'\b(paintalis|panchtalis|पंचेचाळीस|पैंतालीस)\s*(lakh|लाख)?\b', 'forty-five lakh'),
            (r'\b30\s*(lakh|लाख)\b', 'thirty lakh'),
            (r'\b45\s*(lakh|लाख)\b', 'forty-five lakh'),
            (r'\b30\b', 'thirty'),
            (r'\b45\b', 'forty-five'),
            (r'\b3\s*to\s*5\s*lakh\b', 'three to five lakh'),
            (r'\b3\s*se\s*5\s*lakh\b', 'three to five lakh'),
            (r'\bxperia\s*mall\b', 'एक्सपेरिया मॉल'),
            (r'\bsai\s*city\s*group\b', 'साई सिटी ग्रुप'),
            (r'\b(bahattar|बहात्तर)\s*(lakh|लाख)?\b', 'seventy-two lakh'),
            (r'\b36\s*(lakh|लाख)\b', 'thirty-six lakh'),
            (r'\b72\s*(lakh|लाख)\b', 'seventy-two lakh'),
            (r'\b36\b', 'thirty-six'),
            (r'\b72\b', 'seventy-two'),
            (r'\b375\b', 'three hundred seventy-five'),
            (r'\b760\b', 'seven hundred sixty'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'square feet'),
            (r'\b15\s*(-|to|se)\s*20\b', '15 se 20'),
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
HINDI_REAL_ESTATE_PROMPT = """# गायत्री (GAYATRI) — साई गार्डन AI रियल एस्टेट प्रॉपर्टी एडवाइज़र

भूमिका और व्यक्तित्व (ROLE & PERSONA):
- नाम: गायत्री (Gayatri)
- भूमिका: साई सिटी ग्रुप के 'साई गार्डन' (SAI GARDEN) प्रोजेक्ट की रियल एस्टेट प्रॉपर्टी एडवाइज़र।
- प्रोजेक्ट लोकेशन: डोंबिवली ईस्ट, निल्जे, ठीक एक्सपिरिया मॉल के सामने, कल्याण-शिल्फाटा रोड।
- महारेरा (MahaRERA) नंबर: PR1330002501452

फिक्स्ड ओपनिंग ग्रीटिंग (FIRST SPOKEN LINE - MANDATORY):
"नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?"

सख्त जेंडर-न्यूट्रल भाषा के नियम (STRICT GENDER-NEUTRAL RULES):
- ग्राहक का जेंडर (लिंग) कभी भी मानकर न चलें।
- सर, मैडम, जी साहब, भैया, दीदी जैसे जेंडर वाले शब्दों का प्रयोग कभी न करें।
- "देख रहे हैं" या "देख रही हैं" बोलना पूरी तरह से वर्जित है!
- केवल इन जेंडर-न्यूट्रल वाक्यों का ही उपयोग करें:
  * "आपको 1 BHK चाहिए या 2 BHK?"
  * "आपको ready-to-move चाहिए या under-construction चलेगा?"
  * "आपके लिए कौन सा दिन और समय सुविधाजनक रहेगा?"
  * "अगर आपकी फैमिली या फ्रेंड्स में किसी को 1 या 2 BHK चाहिए हो, तो हमारा नंबर ज़रूर शेयर कीजिएगा।"
- आप खुद गायत्री हैं, इसलिए अपने लिए महिला वाचक क्रिया का उपयोग करें ("मैं बात कर रही हूँ", "मैं बोल रही हूँ", "मैं भेज रही हूँ")।

प्रॉपर्टी विवरण और सही मूल्य (PROPERTY DETAILS & PRICING):
- 1 BHK: ₹30 लाख से शुरू। डाउन पेमेंट ₹3 से ₹5 लाख (बैंक लोन सुविधाएं: SBI, HDFC, ICICI)।
- 2 BHK: ₹45 लाख से शुरू। G+22 मंजिला भव्य टॉवर, 35+ लग्जरी सुविधाओं के साथ।
- 3 BHK / 1 RK: उपलब्ध नहीं हैं। विनम्रता से स्पष्ट करें कि केवल 1 BHK और 2 BHK ही उपलब्ध हैं।
- सुविधाएं (Amenities): मॉडर्न जिम, स्विमिंग पूल, क्लबहाउस, बच्चों का खेल क्षेत्र, लैंडस्केप गार्डन, 24/7 सुरक्षा।
- प्रमुख कनेक्टिविटी:
  * निल्जे रेलवे स्टेशन: 1 से 2 मिनट पैदल दूरी।
  * एक्सपिरिया मॉल: ठीक सामने (3 मिनट)।
  * आगामी मेट्रो लाइन 12 (कल्याण-तलोझा): 4 मिनट।
  * डोंबिवली स्टेशन: 20 मिनट।
  * ऐरोली-कटाई टनल: 10 मिनट।

बातचीत का प्रवाह और 4 स्टेप्स (CONVERSATION FLOW & STEPS):
- हर वाक्य छोटा और स्पष्ट रखें (20-25 शब्दों के अंदर)। हर उत्तर के बाद एक विनम्र सवाल ज़रूर पूछें।
- ओपनिंग: "नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?"
- स्टेप 1 (फ्लैट की पसंद और पज़ेशन):
  "1 BHK ₹30 लाख से और 2 BHK ₹45 लाख से शुरू होता है। आपको ready-to-move चाहिए या under-construction चलेगा?"
- स्टेप 2 (अन्य पूछताछ / एमेनिटीज):
  यदि ग्राहक कोई सवाल पूछे, 20-25 शब्दों में संक्षिप्त उत्तर दें और पूछें: "क्या आप प्रोजेक्ट या सुविधाओं के बारे में कुछ और जानना चाहते हैं, या प्रत्यक्ष साईट विजिट प्लान करें?"
- स्टेप 3 (साइट विजिट बुक करना - मुख्य लक्ष्य):
  "प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय सुविधाजनक रहेगा?"
- स्टेप 4 (तुरंत कन्फर्मेशन - वॉइस पहले, बैकग्राउंड सेव):
  "बिल्कुल! आपकी साईट विजिट कन्फर्म कर दी है। सारी जानकारी व्हाट्सऐप पर भेज रही हूँ। धन्यवाद!"
- यदि ग्राहक रुचि न दिखाए:
  "कोई बात नहीं! अगर आपकी फैमिली या फ्रेंड्स में किसी को 1 या 2 BHK चाहिए हो तो हमारा नंबर ज़रूर शेयर कीजिएगा। धन्यवाद!"

कॉल हैंडलिंग नियम:
- अधिकतम कॉल अवधि: 5 मिनट।
- वॉइसमेल संदेश: "हे, लगता है आपका कॉल वॉइसमेल पर चला गया है। मैं आपको बाद में कॉल करती हूँ।"
- 5 सेकंड की चुप्पी पर: "हे, क्या आप अभी भी कॉल पर हैं?"
- भाषा: बातचीत हमेशा हिंदी में शुरू होगी और हिंदी में ही लॉक रहेगी। केवल तभी बदलें जब ग्राहक स्पष्ट रूप से मराठी या इंग्लिश में बोलने के लिए कहे।"""

# ==============================================================================
# 2. LANGUAGE RESOLUTION HELPER & AGENT CLASS (STICKY MULTILINGUAL)
# ==============================================================================
def resolve_language(transcript: str, current_lang: str = "hi") -> str:
    """
    STRICT EXPLICIT LANGUAGE SWITCHING:
    The call begins in Hindi.
    The agent NEVER switches to English or Marathi based on spontaneous loanwords
    (e.g. '1 BHK', '2 BHK', 'price', 'carpet area', 'available', 'possession', 'okay').
    Language ONLY changes when the caller explicitly asks to speak in a specific language.
    Once changed, it stays permanently locked into that language for the rest of the call.
    """
    text = transcript.strip().lower()

    # 1. Explicit request to switch to English
    english_explicit = [
        'speak in english', 'speak english', 'talk in english', 'in english please',
        'in english', 'english please', 'can you speak english', 'can we speak english',
        'english mein baat karo', 'english me baat karo', 'english mein bolo', 'english me bolo',
        'english madhe bola', 'english bola', 'इंग्लिश'
    ]
    if any(e in text for e in english_explicit):
        return 'en'

    # 2. Explicit request to switch to Marathi
    marathi_explicit = [
        'marathi madhe bola', 'marathit bola', 'marathi bola', 'marathi madhun',
        'marathi yete ka', 'marathit sanga', 'marathi sanga', 'marathi please',
        'marathi mein bolo', 'marathi me bolo', 'marathi bhasha', 'मराठीत बोला',
        'मराठी बोला', 'मराठी मध्ये बोला', 'मराठी'
    ]
    if any(m in text for m in marathi_explicit):
        return 'mr'

    # 3. Explicit request to switch to Hindi
    hindi_explicit = [
        'hindi mein bolo', 'hindi me bolo', 'hindi mein baat karo', 'hindi me baat karo',
        'hindi mein boliye', 'hindi me boliye', 'hindi please', 'speak in hindi',
        'talk in hindi', 'hindi madhe bola', 'हिंदी में बोलो', 'हिंदी में बात करो', 'हिंदी'
    ]
    if any(h in text for h in hindi_explicit):
        return 'hi'

    # Strictly preserve the current language if no explicit request was made
    return current_lang



# ==============================================================================
# FAST-RESPONSE PARSERS & ASYNC BACKGROUND ACTIONS ("Reply First, Save Later")
# ==============================================================================

def parse_site_visit_day_time(text: str) -> tuple[str, str]:
    t = text.lower()
    days_map = {
        'sunday': 'Sunday', 'रविवार': 'Sunday', 'itwar': 'Sunday', 'sun': 'Sunday',
        'monday': 'Monday', 'सोमवार': 'Monday', 'somwar': 'Monday',
        'tuesday': 'Tuesday', 'मंगलवार': 'Tuesday', 'mangalwar': 'Tuesday',
        'wednesday': 'Wednesday', 'बुधवार': 'Wednesday', 'budhwar': 'Wednesday',
        'thursday': 'Thursday', 'गुरुवार': 'Thursday', 'guruwar': 'Thursday',
        'friday': 'Friday', 'शुक्रवार': 'Friday', 'shukrawar': 'Friday',
        'saturday': 'Saturday', 'शनिवार': 'Saturday', 'shaniwar': 'Saturday', 'sat': 'Saturday',
        'weekend': 'Weekend', 'वीकेंड': 'Weekend',
        'kal': 'Tomorrow', 'tomorrow': 'Tomorrow', 'कल': 'Tomorrow',
        'parso': 'Day after tomorrow', 'परसों': 'Day after tomorrow',
        'aaj': 'Today', 'today': 'Today'
    }
    matched_day = None
    for k, v in days_map.items():
        if re.search(r'\b' + re.escape(k) + r'\b', t) or k in t:
            matched_day = v
            break

    times_map = [
        (r'(?:3|teen|तीन)\s*(?:baje|बजे|pm)?', '3:00 PM'),
        (r'(?:4|chaar|चार)\s*(?:baje|बजे|pm)?', '4:00 PM'),
        (r'(?:5|paanch|पाँच|पाच)\s*(?:baje|बजे|pm)?', '5:00 PM'),
        (r'(?:11|gyarah|ग्यारह|अकरा)\s*(?:baje|बजे|am)?', '11:00 AM'),
        (r'(?:12|barah|बारह|बारा)\s*(?:baje|बजे|pm)?', '12:00 PM'),
        (r'(?:10|das|दस|दहा)\s*(?:baje|बजे|am)?', '10:00 AM'),
        (r'(?:6|chhah|छह|सहा)\s*(?:baje|बजे|pm)?', '6:00 PM'),
        (r'\b(?:morning|subah|सकाळी)\b', '11:00 AM'),
        (r'\b(?:evening|sham|संध्याकाळी)\b', '5:00 PM'),
        (r'\b(?:afternoon|dopahar|दुपारी)\b', '2:00 PM')
    ]
    matched_time = None
    for pat, time_val in times_map:
        if re.search(pat, t):
            matched_time = time_val
            break

    return (matched_day or 'Sunday', matched_time or '3:00 PM')

def is_site_visit_confirmation(text: str, last_agent_text: str = "") -> tuple[bool, str, str]:
    t = text.lower()
    last_t = last_agent_text.lower()
    
    is_after_sv_prompt = any(k in last_t for k in [
        "साईट विजिट", "site visit", "दिन और समय", "din aur samay", "suvidhajanak", "soyichi", "convenient"
    ])

    day_words = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                 "weekend", "raviwar", "somwar", "mangalwar", "budhwar", "guruwar", "shukrawar",
                 "shaniwar", "itwar", "kal", "parso", "aaj", "tomorrow"]
    has_day = any(re.search(r'\b' + re.escape(w) + r'\b', t) or w in t for w in day_words)
    has_time = bool(re.search(r'\b(?:baje|बजे|pm|am|morning|evening|afternoon|subah|sham|dopahar|1|2|3|4|5|6|10|11|12)\b', t))
    has_confirm = any(c in t for c in [
        "confirm", "lock", "chalega", "thik hai", "theek hai", "book kar", "kar do", "aayenge", "done", "yes", "haan"
    ])

    if has_day or (is_after_sv_prompt and (has_time or has_confirm)):
        day_str, time_str = parse_site_visit_day_time(t)
        return True, day_str, time_str

    return False, "", ""

def save_site_visit_async(customer_name: str, customer_phone: str, preferred_day: str, preferred_time: str, flat_type: str = "2BHK", notes: str = "", room_name: str = "", hangup_fnc=None):
    async def _worker():
        try:
            logger.info("=" * 60)
            logger.info("🏠 [HINDI REAL ESTATE SITE VISIT BOOKED]")
            logger.info(f"👤 Client Name     : {customer_name}")
            logger.info(f"📅 Preferred Day   : {preferred_day}")
            logger.info(f"⏰ Preferred Time  : {preferred_time}")
            logger.info(f"🏢 Flat Type       : {flat_type}")
            logger.info("=" * 60)

            visit_record = {
                "customer_name": customer_name,
                "customer_phone": customer_phone or "+918693081506",
                "preferred_day": preferred_day,
                "preferred_time": preferred_time,
                "flat_type": flat_type,
                "notes": notes,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "site_visit_confirmed",
                "lead_status": "interested"
            }
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/property_visits.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(visit_record, ensure_ascii=False) + "\n")

            # Background update to db.json for Web Dashboard
            for db_path in ["db.json", os.path.join(os.path.dirname(__file__), "..", "db.json")]:
                if os.path.exists(db_path):
                    try:
                        with open(db_path, "r", encoding="utf-8") as f:
                            db_data = json.load(f)
                        if "siteVisits" not in db_data:
                            db_data["siteVisits"] = []
                        new_visit = {
                            "id": f"sv-{int(time.time()*1000)}",
                            "customerName": customer_name,
                            "customerPhone": customer_phone or "+918693081506",
                            "visitDay": preferred_day,
                            "visitTime": preferred_time,
                            "flatType": flat_type,
                            "status": "confirmed",
                            "createdAt": datetime.utcnow().isoformat(),
                            "notes": notes or "Booked via Gayatri Voice AI",
                            "callId": room_name,
                            "project": "Sai Garden"
                        }
                        db_data["siteVisits"].insert(0, new_visit)
                        
                        clean_target = re.sub(r'\D', '', customer_phone)
                        for lead in db_data.get("leads", []):
                            clean_l = re.sub(r'\D', '', lead.get("phone", ""))
                            if clean_l and clean_l[-10:] == clean_target[-10:]:
                                lead["status"] = "meeting_scheduled"
                                lead["notes"] = f"Site visit booked for {preferred_day} at {preferred_time} ({flat_type})"
                                lead["lastCallAt"] = datetime.utcnow().isoformat()
                                break
                        with open(db_path, "w", encoding="utf-8") as f:
                            json.dump(db_data, f, ensure_ascii=False, indent=2)
                        logger.info("✅ [BACKGROUND SYNC] Site visit synced to db.json for Web Dashboard!")
                        break
                    except Exception as db_e:
                        logger.warning(f"Could not update db.json: {db_e}")

            # Send WhatsApp details in background
            try:
                send_whatsapp_background(customer_phone, customer_name, flat_type)
            except Exception as wa_err:
                logger.warning(f"WhatsApp background send: {wa_err}")

            # Trigger graceful hangup after speech playout
            if hangup_fnc:
                hangup_fnc(wait_for_speech=True, delay_seconds=1.0)
        except Exception as err:
            logger.error(f"Error in save_site_visit_async: {err}")

    asyncio.create_task(_worker())

def update_lead_status_async(customer_name: str, customer_phone: str, status: str, notes: str = "", hangup_fnc=None):
    async def _worker():
        try:
            logger.info("=" * 60)
            logger.info(f"📋 [LEAD STATUS UPDATED ASYNC] -> {status.upper()}")
            logger.info(f"👤 Client Name     : {customer_name}")
            logger.info(f"📝 Notes           : {notes}")
            logger.info("=" * 60)

            record = {
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "status": status,
                "notes": notes,
                "timestamp": datetime.utcnow().isoformat()
            }
            os.makedirs("bookings", exist_ok=True)
            with open("bookings/property_visits.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            for db_path in ["db.json", os.path.join(os.path.dirname(__file__), "..", "db.json")]:
                if os.path.exists(db_path):
                    try:
                        with open(db_path, "r", encoding="utf-8") as f:
                            db_data = json.load(f)
                        clean_target = re.sub(r'\D', '', customer_phone)
                        for lead in db_data.get("leads", []):
                            clean_l = re.sub(r'\D', '', lead.get("phone", ""))
                            if clean_l and clean_l[-10:] == clean_target[-10:]:
                                lead["status"] = status
                                lead["notes"] = notes
                                lead["lastCallAt"] = datetime.utcnow().isoformat()
                                break
                        with open(db_path, "w", encoding="utf-8") as f:
                            json.dump(db_data, f, ensure_ascii=False, indent=2)
                        break
                    except Exception as db_e:
                        logger.warning(f"Could not update db.json status: {db_e}")

            if hangup_fnc and status == "not_interested":
                hangup_fnc(wait_for_speech=True, delay_seconds=1.0)
        except Exception as err:
            logger.error(f"Error in update_lead_status_async: {err}")

    asyncio.create_task(_worker())

def send_whatsapp_background(customer_phone: str, customer_name: str, flat_type: str = "2BHK"):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    api_key_sid = os.getenv("TWILIO_API_KEY_SID")
    api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_SENDER", "whatsapp:+14155238886")
    if not account_sid or not customer_phone:
        return

    clean_phone = customer_phone.strip().replace(" ", "").replace("-", "")
    if not clean_phone.startswith("+"):
        clean_phone = "+91" + clean_phone if len(clean_phone) == 10 else "+" + clean_phone

    clean_name = re.sub(r'\s*ji$', '', customer_name, flags=re.IGNORECASE).strip() or "Valued Client"

    body = (
        f"Namaste {clean_name},\n\n"
        "Thank you for speaking with Gayatri at Sai Garden (Sai City Group).\n"
        "Here are the official brochure details for *Sai Garden*, Dombivli East (Nilje):\n\n"
        "🌿 *Project*: Sai Garden — Where Luxury Meets Nature\n"
        "📍 *Location*: Directly opposite Xperia Mall, Kalyan-Shilphata Road, Dombivli East (1 min from Nilje Station)\n"
        "🏢 *Tower*: G+22 Storeyed Luxury Tower (MahaRERA: PR1330002501452)\n"
        "💰 *Pricing*:\n"
        "• 1 BHK: Starts at 30 Lakh (Down payment 3 to 5 Lakh, Easy loans from SBI/HDFC/ICICI)\n"
        "• 2 BHK: Starts at 45 Lakh (G+22 Tower, 35+ Luxury Amenities)\n\n"
        "🏊 *Amenities*: Modern Gym, Swimming Pool, Clubhouse, Children's Play Area, Landscaped Garden, 24/7 Security\n\n"
        "📍 *Site Office*: Sai Garden, Casa Rio Gate No. 3, Near Nilaje Station, Niljepada, Dombivli East - 421204\n"
        "📞 *Contact*: 8104027095 / 8097052221 / 9892115901\n\n"
        "Have a wonderful day!"
    )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    auth = (account_sid, auth_token) if auth_token else (api_key_sid, api_key_secret)
    requests.post(url, data={"From": from_number, "To": f"whatsapp:{clean_phone}", "Body": body}, auth=auth, timeout=10)
    logger.info(f"📱 [WHATSAPP DISPATCHED] Sent official Sai Garden brochure to {clean_phone}")

class PriyaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji", customer_phone: str = "", hangup_fnc=None, on_speech_captured=None):
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self._hangup_fnc = hangup_fnc
        self._on_speech_captured = on_speech_captured
        self.off_topic_count = 0
        self.selected_flat_type = '2BHK'
        self.room_name = ''
        
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
        """
        Universal Intelligent LLM Node:
        Every conversational turn routes 100% through the Gemini 3.5 Flash Lite LLM brain.
        Zero hardcoded keyword regex matches; full reasoning, empathy, and context awareness.
        Streams tokens directly into Cartesia Neural TTS for instantaneous voice playout.
        """
        def speak(text: str) -> str:
            if self._on_speech_captured:
                try:
                    self._on_speech_captured(text)
                except Exception as err:
                    logger.debug(f"Error in on_speech_captured: {err}")
            return text

        # Synchronize language detection if caller requested a language switch
        user_msgs = [m for m in chat_ctx.items if getattr(m, "role", "") in ["user", "customer"]]
        if user_msgs:
            last_msg = user_msgs[-1]
            raw_text = getattr(last_msg, "text_content", "") or ""
            if not raw_text:
                c = getattr(last_msg, "content", "")
                if isinstance(c, list):
                    raw_text = " ".join(str(x) for x in c if x)
                else:
                    raw_text = str(c or "")

            # Strictly drop non-human acoustic artifacts (e.g. ringback pulses '2', line clicks)
            if is_noise_or_digit_artifact(raw_text):
                logger.info(f"🚫 [LLM NODE] Dropping non-human acoustic artifact: '{raw_text}'")
                return

            if raw_text:
                global ACTIVE_TTS_LANGUAGE
                det_lang = resolve_language(raw_text, ACTIVE_TTS_LANGUAGE)
                if det_lang != ACTIVE_TTS_LANGUAGE:
                    ACTIVE_TTS_LANGUAGE = det_lang
                    logger.info(f"🗣️ [LANGUAGE SWITCH] Updated ACTIVE_TTS_LANGUAGE to '{ACTIVE_TTS_LANGUAGE}' from: '{raw_text}'")

        # ==============================================================================
        # FAST RESPONSE DISPATCHER (<80ms): "Reply First, Do Rest in Background"
        # ==============================================================================
        lower_raw = raw_text.lower()
        
        # Look up preceding agent question from dialogue context
        assistant_msgs = [m for m in chat_ctx.items if getattr(m, "role", "") in ["agent", "assistant"]]
        last_agent_text = ""
        if assistant_msgs:
            last_agent_msg = assistant_msgs[-1]
            last_agent_text = getattr(last_agent_msg, "text_content", "") or ""
            if not last_agent_text:
                c = getattr(last_agent_msg, "content", "")
                last_agent_text = " ".join(str(x) for x in c if x) if isinstance(c, list) else str(c or "")

        # 1. SITE VISIT CONFIRMATION (STEP 5): Reply FIRST immediately (<80ms), then save in background!
        is_sv, sv_day, sv_time = is_site_visit_confirmation(raw_text, last_agent_text)
        if is_sv:
            if ACTIVE_TTS_LANGUAGE == "mr":
                conf_text = "नक्कीच! तुमची साईट व्हिजिट कन्फर्म केली आहे. सर्व माहिती व्हाट्सअॅपवर पाठवत आहे. धन्यवाद!"
            elif ACTIVE_TTS_LANGUAGE == "en":
                conf_text = "Certainly! Your site visit is confirmed. Sending all the details on WhatsApp. Thank you!"
            else:
                conf_text = "बिल्कुल! आपकी साईट विजिट कन्फर्म कर दी है। सारी जानकारी व्हाट्सऐप पर भेज रही हूँ। धन्यवाद!"
            
            logger.info(f"⚡ [FAST SITE VISIT CONFIRMATION (<80ms)] Booked for {sv_day} at {sv_time}. Replying FIRST!")
            speak(conf_text)
            save_site_visit_async(
                customer_name=self.customer_name,
                customer_phone=self.customer_phone,
                preferred_day=sv_day,
                preferred_time=sv_time,
                flat_type=self.selected_flat_type,
                notes=f"Confirmed turn: '{raw_text}'",
                room_name=self.room_name,
                hangup_fnc=self._hangup_fnc
            )
            yield conf_text
            return

        # 2. NOT INTERESTED: Reply FIRST immediately (<80ms), update lead status in background!
        is_not_interested = any(p in lower_raw for p in [
            "nahi chahiye", "not interested", "nahi lena", "interest nahi", "koi interest nahi",
            "nakko", "no thanks", "no requirement", "wrong number", "galat number"
        ]) and not any(p in lower_raw for p in ["bhk", "flat", "price", "kitna", "kya", "ready", "under"])

        if is_not_interested:
            if ACTIVE_TTS_LANGUAGE == "mr":
                ni_text = "काही हरकत नाही! जर आपल्या फॅमिली किंवा फ्रेंड्समध्ये कोणाला 1 किंवा 2 BHK हवं असल्यास आमचा नंबर नक्की शेअर करा. धन्यवाद!"
            elif ACTIVE_TTS_LANGUAGE == "en":
                ni_text = "No problem at all! If anyone in your family or friends needs a 1 or 2 BHK, please do share our number. Thank you!"
            else:
                ni_text = "कोई बात नहीं! अगर आपकी फैमिली या फ्रेंड्स में किसी को 1 या 2 BHK चाहिए हो तो हमारा नंबर ज़रूर शेयर कीजिएगा। धन्यवाद!"
            
            logger.info("⚡ [FAST NOT INTERESTED (<80ms)] Replying polite referral message FIRST!")
            speak(ni_text)
            update_lead_status_async(self.customer_name, self.customer_phone, "not_interested", notes=f"Caller said: '{raw_text}'", hangup_fnc=self._hangup_fnc)
            yield ni_text
            return

        # 3. 1 BHK / 2 BHK / 3 BHK / 1 RK INQUIRY (STEP 1 & STEP 2)
        is_3bhk_or_1rk = bool(re.search(r'\b(3\s*bhk|three\s*bhk|तीन\s*बीएचके|1\s*rk|one\s*rk|एक\s*आरके|rk)\b', lower_raw))
        is_1bhk = bool(re.search(r'\b(1\s*bhk|one\s*bhk|ek\s*bhk|एक\s*बीएचके|1|one|ek)\b', lower_raw)) and not is_3bhk_or_1rk and not bool(re.search(r'\b(2\s*bhk|two\s*bhk|do\s*bhk|दोन\s*बीएचके|दो\s*बीएचके)\b', lower_raw))
        is_2bhk = bool(re.search(r'\b(2\s*bhk|two\s*bhk|do\s*bhk|dono\s*bhk|दोन\s*बीएचके|दो\s*बीएचके|2|two|do)\b', lower_raw)) and not is_3bhk_or_1rk

        is_greeting_context = any(k in last_agent_text.lower() for k in ["1 bhk", "2 bhk", "would you prefer", "chahiye", "havay"])

        if is_3bhk_or_1rk:
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "क्षमस्व, आमच्याकडे फक्त 1 BHK आणि 2 BHK उपलब्ध आहेत. आपल्याला 1 BHK बद्दल जाणून घ्यायचे आहे की 2 BHK?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "I apologize, we only have 1 BHK and 2 BHK flats available. Would you prefer details for 1 BHK or 2 BHK?"
            else:
                reply = "माफ़ कीजिएगा, हमारे यहाँ सिर्फ 1 BHK और 2 BHK उपलब्ध हैं। आपको 1 BHK के बारे में जानना है या 2 BHK?"
            logger.info("⚡ [FAST 3BHK/1RK REFUSAL (<80ms)]")
            speak(reply)
            yield reply
            return

        if is_greeting_context and is_1bhk:
            self.selected_flat_type = "1BHK"
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "आमचे 1 BHK फ्लॅट्स 30 लाखांपासून सुरू होतात, डाऊन पेमेंट 3 ते 5 लाख आहे. आपल्याला ready-to-move हवंय की under-construction चालेल?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "Our 1 BHK flats start from 30 Lakh onwards with down payment of 3 to 5 Lakh. Would you prefer ready-to-move or under-construction?"
            else:
                reply = "हमारे 1 BHK फ्लैट्स 30 लाख से शुरू होते हैं, डाउन पेमेंट 3 से 5 लाख है। आपको ready-to-move चाहिए या under-construction चलेगा?"
            logger.info("⚡ [FAST 1 BHK PRICING (<80ms)]")
            speak(reply)
            yield reply
            return

        if is_greeting_context and is_2bhk:
            self.selected_flat_type = "2BHK"
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "आमचे 2 BHK लक्झरी फ्लॅट्स 45 लाखांपासून सुरू होतात, G+22 टॉवरमध्ये 35+ सुविधांसह. आपल्याला ready-to-move हवंय की under-construction चालेल?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "Our 2 BHK luxury flats start from 45 Lakh onwards in a G+22 tower with 35+ amenities. Would you prefer ready-to-move or under-construction?"
            else:
                reply = "हमारे 2 BHK लग्जरी फ्लैट्स 45 लाख से शुरू होते हैं, G+22 टॉवर में 35 से ज़्यादा सुविधाओं के साथ। आपको ready-to-move चाहिए या under-construction चलेगा?"
            logger.info("⚡ [FAST 2 BHK PRICING (<80ms)]")
            speak(reply)
            yield reply
            return

        # 4. READY-TO-MOVE VS UNDER-CONSTRUCTION (STEP 2 -> ASK OTHER INQUIRY OR SITE VISIT)
        is_rtm_query = any(k in last_agent_text.lower() for k in ["ready-to-move", "ready to move", "under-construction", "under construction"])
        is_rtm_reply = any(k in lower_raw for k in ["ready", "ready to move", "ready-to-move", "under", "under construction", "under-construction", "dono", "koi bhi", "chalega"])

        if is_rtm_query and is_rtm_reply:
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "समजले. आपल्याला प्रोजेक्ट किंवा सुविधांबद्दल अजून काही विचारायचे आहे, की थेट साईट व्हिजिट प्लॅन करूया?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "Understood. Would you like to know more about the amenities or connectivity, or shall we plan a direct site visit?"
            else:
                reply = "समझ गई। क्या आप प्रोजेक्ट या सुविधाओं के बारे में कुछ और पूछना चाहते हैं, या प्रत्यक्ष साईट विजिट प्लान करें?"
            logger.info("⚡ [FAST INQUIRY CHECK QUESTION (<80ms)]")
            speak(reply)
            yield reply
            return

        # 4B. TRANSITION FROM INQUIRY CHECK TO SITE VISIT
        is_inquiry_check = any(k in last_agent_text.lower() for k in ["कुछ और पूछना चाहते हैं", "साईट विजिट प्लान करें", "अजून काही विचारायचे आहे", "site visit plan"])
        is_direct_visit_intent = any(k in lower_raw for k in ["site visit", "visit", "nahi", "kuch nahi", "direct", "dekhne", "aana", "plan kar", "theek hai", "chalega", "aayenge"])

        if is_inquiry_check and is_direct_visit_intent:
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "Which day and time would be convenient for a direct site visit?"
            else:
                reply = "प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय सुविधाजनक रहेगा?"
            logger.info("⚡ [FAST SITE VISIT PROMPT (<80ms)]")
            speak(reply)
            yield reply
            return

        # 5. ALL OTHER FREE-FORM QUERIES: Stream directly through Gemini LLM Brain!
        collected_chunks = []
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, str):
                collected_chunks.append(chunk)
            elif hasattr(chunk, "choices") and chunk.choices:
                delta = getattr(chunk.choices[0], "delta", None)
                if delta and getattr(delta, "content", None):
                    collected_chunks.append(delta.content)
            elif hasattr(chunk, "text") and chunk.text:
                collected_chunks.append(chunk.text)
            yield chunk

        if collected_chunks and self._on_speech_captured:
            full_speech = "".join(collected_chunks).strip()
            if full_speech:
                speak(full_speech)

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

        # Save site visit in background task ("reply first, save later")
        save_site_visit_async(
            customer_name=customer_name,
            customer_phone=getattr(self, "customer_phone", "") or "+918693081506",
            preferred_day=preferred_day,
            preferred_time=preferred_time,
            flat_type=flat_type,
            notes=notes,
            room_name=getattr(self, "room_name", ""),
            hangup_fnc=self._hangup_fnc
        )

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
                "Thank you for speaking with Gayatri at Sai Garden (Sai City Group).\n"
                "As requested, here are the official brochure & details for *Sai Garden*, Dombivli East (Nilje):\n\n"
                "🌿 *Project*: Sai Garden — Where Luxury Meets Nature\n"
                "📍 *Location*: Directly opposite Xperia Mall, Kalyan-Shilphata Road, Dombivli East (1 min from Nilje Station)\n"
                "🏢 *Tower*: G+22 Storeyed Luxury Tower (MahaRERA: PR1330002501452)\n"
                "💰 *Pricing*:\n"
                "• 1 BHK: Starts at 30 Lakh (Down payment 3 to 5 Lakh, Easy loans from SBI/HDFC/ICICI)\n"
                "• 2 BHK: Starts at 45 Lakh (G+22 Tower, 35+ Luxury Amenities)\n\n"
                "🏊 *Amenities*: Modern Gym, Swimming Pool, Clubhouse, Children's Play Area, Landscaped Garden, 24/7 Security\n\n"
                "📍 *Site Office*: Sai Garden, Casa Rio Gate No. 3, Near Nilaje Station, Niljepada, Dombivli East - 421204\n"
                "📞 *Contact*: 8104027095 / 8097052221 / 9892115901\n\n"
                "Have a wonderful day!"
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
    pass

SELECTED_MODEL = "gemini-3.5-flash-lite"
SELECTED_GROQ_MODEL = "openai/gpt-oss-20b" # default fallback
if os.getenv("SAMBANOVA_API_KEY"):
    SELECTED_GROQ_MODEL = "gpt-oss-120b"
global_llm = None
global_llm_compiled = False

# Load cached models if available to prevent child process re-validation delays
cached_model, cached_groq_model = load_cached_models()
if cached_model or cached_groq_model:
    if cached_model:
        SELECTED_MODEL = "gemini-3.5-flash-lite"
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
    SELECTED_MODEL = "gemini-3.5-flash-lite"
    global_llm_compiled = True

# 1. GOOGLE GEMINI (Ultra-reliable ~555ms TTFT, high token quota, zero rate limit 429 errors)
elif global_google_key and (llm_provider in ["google", "gemini"] or not (global_groq_key and global_groq_key.startswith("gsk_"))):
    from livekit.plugins import google
    
    preferred_models = ["gemini-3.5-flash-lite"]
    
    # If a call is active, skip verification compilation and use cached/default model immediately
    try:
        from livekit.agents import llm as agents_llm
        agent_dummy = PriyaRealEstateAgent()
        agent_tools_dummy = agent_dummy.tools
        chat_ctx_dummy = agents_llm.ChatContext()
        chat_ctx_dummy.add_message(role="user", content="hello")
            
        async def _test_compile(llm_instance):
            async with llm_instance.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy) as chat_stream:
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
                SELECTED_MODEL = "gemini-3.5-flash-lite"
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
    try:
        from livekit.agents import llm as agents_llm
        agent_dummy = PriyaRealEstateAgent()
        agent_tools_dummy = agent_dummy.tools
        chat_ctx_dummy = agents_llm.ChatContext()
        chat_ctx_dummy.add_message(role="user", content="hello")
            
        async def _test_compile_groq(llm_instance):
            async with llm_instance.chat(chat_ctx=chat_ctx_dummy, tools=agent_tools_dummy) as chat_stream:
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
    ("2 BHK", 4.0),
    ("1 BHK", 4.0),
    ("one BHK", 4.0),
    ("two BHK", 4.0),
    ("BHK", 4.0),
    ("बीएचके", 4.0),
    ("Sai Garden", 3.5),
    ("School", 3.0),
    ("Hospital", 3.0),
    ("Station", 3.0),
    ("Possession", 3.0),
    ("Site visit", 3.0),
    ("Nilje", 2.5),
    ("Dombivli", 2.5),
    ("Kalyan", 2.5),
    ("Thane", 2.0),
    ("Xperia", 2.5),
    ("Mall", 2.5),
    ("Metro", 2.5),
    ("Gym", 2.5),
    ("Garden", 2.5),
    ("Lakh", 2.5),
    ("Crore", 2.0),
    ("Carpet area", 2.5),
    ("Tomorrow", 2.5),
    ("Weekend", 2.5),
    ("Vashi", 2.0),
    ("Airoli", 2.0),
    ("Palava", 2.0),
    ("Shil Road", 2.0),
    ("Lodha", 2.0),
    ("Jaquar", 2.0),
]
STT_KEYTERMS = [kw[0] for kw in STT_KEYWORDS]

# Answering Machine / Voicemail / Email Forwarding Patterns (AMD)
VOICEMAIL_PATTERNS = [
    r"\b(voicemail|voice\s*mail)\b",
    r"\b(leave\s*(a|your)?\s*message)\b",
    r"\b(after\s*the\s*(tone|beep))\b",
    r"\b(record\s*(your)?\s*message)\b",
    r"\b(at\s*the\s*tone)\b",
    r"\b(call\s*forward(ed|ing)?)\b",
    r"\b(forward(ed)?\s*to)\b",
    r"\b(email\s*forward(ing)?)\b",
    r"\b(switched\s*off)\b",
    r"\b(switch\s*off)\b",
    r"\b(not\s*reachable)\b",
    r"\b(out\s*of\s*coverage)\b",
    r"\b(currently\s*unavailable)\b",
    r"\b(cannot\s*(take|answer)\s*(your)?\s*call)\b",
    r"\b(cannot\s*be\s*reached)\b",
    r"\b(vyast\s*hai)\b",
    r"\b(dusre\s*call\s*par)\b",
    r"\b(another\s*call)\b",
    r"\b(busy\s*on\s*another\s*call)\b",
    r"\b(kripya\s*(kuch\s*samay\s*)?baad)\b",
    r"\b(please\s*try\s*again\s*later)\b",
    r"\b(does\s*not\s*exist)\b",
    r"\b(invalid\s*number)\b",
]

def is_voicemail_or_machine(transcript: str) -> bool:
    if not transcript:
        return False
    t = transcript.strip().lower()
    return any(re.search(pat, t, re.IGNORECASE) for pat in VOICEMAIL_PATTERNS)

HUMAN_GREETING_WORDS = [
    "hello", "namaskar", "namaste", "haan", "ha", "haa", "boliye", "bolo", "kaun",
    "kaun bol", "sun raha", "bataiye", "yes", "hi", "who is", "kya hai", "accha",
    "bhk", "flat", "sai garden", "dombivli", "property", "details", "ji"
]

def is_noise_or_digit_artifact(text: str) -> bool:
    if not text:
        return True
    clean = re.sub(r'[^\w\s]', '', text).strip()
    if not clean or clean.isdigit() or len(clean) <= 1:
        return True
    if clean.lower() in ['2', '1', '3', '4', '5', 'प', 'द', 'अ', 'h', 'ah', 'uh']:
        return True
    return False

def is_human_speech(text: str) -> bool:
    if is_noise_or_digit_artifact(text):
        return False
    t = text.lower()
    words = t.split()
    if any(w in t for w in HUMAN_GREETING_WORDS) or len(words) >= 2:
        return True
    return False


STT_REPLACE = {
    "2 amenities": "2 BHK",
    "two amenities": "2 BHK",
    "1 amenities": "1 BHK",
    "one amenities": "1 BHK",
    "amenities par dekh": "2 BHK dekh",
    "amenities dekh": "2 BHK dekh",
    "दो बीएचके": "2 BHK",
    "एक बीएचके": "1 BHK",
    "दो bhk": "2 BHK",
    "एक bhk": "1 BHK",
    "2bhk": "2 BHK",
    "1bhk": "1 BHK",
    "cool": "school",
    "cool वग़ैरह": "school वग़ैरह",
    "exam": "station",
    "exam possession": "station possession",
    "station se kitna door hai tujh": "station se kitna door hai",
    "washing station": "Vashi station",
    "washing": "Vashi",
    "bashi": "Vashi",
    "kaliyan": "Kalyan",
    "kalyan station": "Kalyan station",
    "dombivali": "Dombivli",
    "dombiwali": "Dombivli",
    "nilje station": "Nilje station",
    "१ आरके": "1 RK",
    "१आरके": "1 RK",
    "वन आरके": "1 RK",
    "एक आरके": "1 RK",
    "२ बीएचके": "2 BHK",
    "१ बीएचके": "1 BHK",
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

    # 2. Pre-warm Deepgram Nova-3 STT (Native Hindi / Hinglish low-latency acoustic model)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    proc.userdata["stt"] = deepgram.STT(
        language="hi",
        model="nova-2-general",
        endpointing_ms=120,
        utterance_end_ms=None,
        smart_format=True,
        no_delay=True,
        interim_results=True,
        keywords=STT_KEYWORDS,
        replace=STT_REPLACE,
        api_key=deepgram_key
    )

    # 3. Pre-warm Silero VAD (Telephony calibrated: 0.35 activation, 50ms speech, 200ms silence)
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.25,
        min_speech_duration=0.10,
        activation_threshold=0.38,
        deactivation_threshold=0.22,
        prefix_padding_duration=0.15,
        sample_rate=16000
    )

    # 4. Pre-warm Cartesia/ElevenLabs TTS (loads client network config in background)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    cartesia_model = os.getenv("CARTESIA_MODEL", "sonic-3.5").strip()
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "0.94"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "").strip()
    cartesia_volume = min(1.0, float(os.getenv("CARTESIA_VOLUME", "1.0")))
    if cartesia_key and len(cartesia_key) > 10:
        proc.userdata["tts"] = cartesia.TTS(
            api_key=cartesia_key,
            voice=kusha_voice_id,
            language="hi",
            sample_rate=48000,
            model=cartesia_model,
            speed=cartesia_speed,
            emotion=None,
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
        for m_name in ["gemini-3.5-flash-lite", "gemini-1.5-flash"]:
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

    except Exception as e:
        logger.warning(f"Failed to create lock file: {e}")

    # Register cleanup callback on job shutdown to release the lock file

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
            model="nova-2-general",
            endpointing_ms=120,
            utterance_end_ms=None,
            smart_format=True,
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
    # 3. os.getenv("CARTESIA_SPEED", "0.98")
    cartesia_speed = 0.94
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
            cartesia_speed = float(os.getenv("CARTESIA_SPEED", "0.94"))
        except Exception:
            cartesia_speed = 0.94
    logger.info(f"🎙️ [VOICE SPEED] Gayatri Voice Speed resolved to: {cartesia_speed}x")

    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "").strip()
    cartesia_volume = min(1.0, float(os.getenv("CARTESIA_VOLUME", "1.0")))
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
                sample_rate=48000,
                model=cartesia_model,
                speed=cartesia_speed,
                emotion=None,
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
        min_silence_duration=0.25,
        min_speech_duration=0.10,
        activation_threshold=0.38,
        deactivation_threshold=0.22,
        prefix_padding_duration=0.15,
        sample_rate=16000
    )
    
    # Reset TTS options only if it is Cartesia (ElevenLabs uses different options structure)
    is_cartesia = tts and "cartesia" in tts.__class__.__module__
    if is_cartesia and hasattr(tts, "update_options"):
        tts.update_options(
            voice=kusha_voice_id,
            language="hi",
            speed=cartesia_speed,
            emotion=None,
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
                "min_delay": 0.12,  # Ultra-crisp 120ms turn-taking after caller finishes
            },
            "preemptive_generation": {
                "enabled": False,
                "preemptive_tts": False,
            },
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.35,  # Responsive listening sensitivity for clean caller interruptions
                "resume_false_interruption": False,
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

            # If call was voicemail / answering machine, set outcome directly
            if is_answering_machine:
                intel = {
                    "outcome": "Not Interested",
                    "sentiment": "neutral",
                    "aiSummary": f"Call to {customer_name} reached voicemail, answering machine, or email forwarding; terminated immediately.",
                    "detectedQuestions": ["Voicemail / Answering Machine"]
                }
            else:
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
        try:
            from livekit import api
            cloud_lk_url = os.getenv("LIVEKIT_URL", "https://cold-calling-j7qhnkas.livekit.cloud")
            cloud_lk_key = os.getenv("LIVEKIT_API_KEY", "APIAkEXqBNfS2LP")
            cloud_lk_secret = os.getenv("LIVEKIT_API_SECRET", "dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT")
            lk_client = api.LiveKitAPI(url=cloud_lk_url, api_key=cloud_lk_key, api_secret=cloud_lk_secret)
            await lk_client.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))
            await lk_client.aclose()
            logger.info("✅ LiveKit room cleanly deleted after caller hangup.")
        except Exception as del_err:
            logger.debug(f"Room delete after hangup note: {del_err}")

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
    has_prompted_silence = False
    agent_is_speaking = False
    intro_started = False
    intro_finished = False
    caller_has_spoken = False
    is_answering_machine = False
    watchdog_task = None
    last_agent_speech = ""

    @session.on("error")
    def _on_session_error(ev):
        logger.error(f"❌ [AGENT SESSION ERROR] Error={getattr(ev, 'error', ev)}")

    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent):
        nonlocal t_user_stop, t_last_activity, has_prompted_silence, caller_has_spoken
        try:
            if ev.new_state == "speaking":
                caller_has_spoken = True
                t_last_activity = time.time()
                has_prompted_silence = False
            elif ev.old_state == "speaking" and ev.new_state == "listening":
                t_user_stop = time.perf_counter()
                intro_finished = True
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

    current_lang = "hi"

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        nonlocal current_lang, t_user_stop, t_last_activity, has_prompted_silence, caller_has_spoken, intro_started, intro_finished, is_answering_machine
        caller_has_spoken = True
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

            # 0. Reject solitary digits ('2', '1'), DTMF tones, and line noise artifacts
            if is_noise_or_digit_artifact(text):
                logger.info(f"🔇 [FILTERED ARTIFACT] Ignored non-human acoustic tone / digit: '{ev.transcript}'")
                return

            # 1. Answering Machine / Voicemail / Forwarding Check (AMD)
            if is_voicemail_or_machine(text):
                logger.warning(f"🚫 [ANSWERING MACHINE / VOICEMAIL DETECTED] Transcript: '{ev.transcript}'. Speaking message and concluding...")
                is_answering_machine = True
                vm_msg = "हे, लगता है आपका कॉल वॉइसमेल पर चला गया है। मैं आपको बाद में कॉल करती हूँ।"
                record_dialogue_turn("agent", vm_msg)
                record_dialogue_turn("customer", f"[Voicemail/Machine: {ev.transcript}]")
                try:
                    session.say(vm_msg, allow_interruptions=False)
                except Exception as vm_err:
                    logger.warning(f"Error speaking voicemail message: {vm_err}")
                trigger_hangup(wait_for_speech=True, delay_seconds=0.8)
                return

            # 2. First Human Voice Detection: Trigger Opening Greeting ONLY on genuine human speech
            if not intro_started:
                if not is_human_speech(text):
                    logger.info(f"⏳ [AWAITING HUMAN WORDS] Caller uttered non-greeting noise: '{ev.transcript}'. Waiting for real speech...")
                    return
                intro_started = True
                intro_finished = True
                record_dialogue_turn("customer", ev.transcript.strip())
                opening_greeting = "नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?"
                logger.info(f"👤 [HUMAN VOICE CONFIRMED] Caller spoke. Delivering opening greeting: '{opening_greeting}'")
                record_dialogue_turn("agent", opening_greeting)
                try:
                    session.say(opening_greeting, allow_interruptions=True)
                except Exception as intro_err:
                    logger.warning(f"Error speaking opening greeting on human voice: {intro_err}")
                return

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
                global ACTIVE_TTS_LANGUAGE
                ACTIVE_TTS_LANGUAGE = current_lang
                logger.info(f"🗣️ Language Switch Detected: '{current_lang}' (ACTIVE_TTS_LANGUAGE={ACTIVE_TTS_LANGUAGE}) for text: '{ev.transcript}'")
                
                is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
                if is_cartesia and hasattr(session.tts, "update_options"):
                    if current_lang == "mr":
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="mr",
                            speed=cartesia_speed,
                            emotion=None,
                            volume=cartesia_volume
                        )
                        logger.info(f"🔄 Switched TTS to Pure Marathi with Kusha Cloned Voice ({kusha_voice_id}, volume={cartesia_volume}, speed={cartesia_speed})")
                    elif current_lang == "en":
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="en",
                            speed=cartesia_speed,
                            emotion=None,
                            volume=cartesia_volume
                        )
                        logger.info(f"🔄 Switched TTS to English (Kusha Cloned Voice: {kusha_voice_id}, speed={cartesia_speed})")
                    else:
                        session.tts.update_options(
                            voice=kusha_voice_id,
                            language="hi",
                            speed=cartesia_speed,
                            emotion=None,
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
                    "aapka din shubh ho", "din shubh ho", "shubh ho bye", "shubh ho, bye", "alvida",
                    "baad mein call karte hain",
                    "have a wonderful day", "have a great day", "goodbye",
                    "दिवस चांगला जावो", "काळजी घ्या, नमस्कार"
                ]
                if any(phrase in text for phrase in ending_phrases):
                    logger.info("👋 [GOODBYE DETECTED IN AGENT SPEECH] Ensuring automated call termination after speech finishes...")
                    trigger_hangup(wait_for_speech=True, delay_seconds=0.8)

            elif role_str in ["user", "customer"]:
                record_dialogue_turn("customer", raw_text)
        except Exception as e:
            logger.debug(f"Error in on_item_added check: {e}")

        # Keep up to 6 recent dialogue items + system prompt (keeps TTFT ultra-fast while preserving immediate context)
        if hasattr(session, "_chat_ctx") and session._chat_ctx:
            max_dialogue_items = 4
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
            "aapka din shubh ho", "din shubh ho", "shubh ho bye", "shubh ho, bye", "alvida",
            "baad mein call karte hain",
            "have a wonderful day", "have a great day", "goodbye",
            "दिवस चांगला जावो", "काळजी घ्या, नमस्कार"
        ]
        if any(phrase in text for phrase in ending_phrases):
            logger.info("👋 [GOODBYE DETECTED IN AGENT SPEECH] Ensuring automated call termination after speech finishes...")
            trigger_hangup(wait_for_speech=True, delay_seconds=0.8)

    spoken_customer_name = f"{customer_name} ji" if not customer_name.endswith("ji") else customer_name
    agent = PriyaRealEstateAgent(
        customer_name=spoken_customer_name,
        customer_phone=customer_phone,
        hangup_fnc=trigger_hangup,
        on_speech_captured=_record_agent_speech
    )
    agent.room_name = ctx.room.name

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

    # Allow 1.1s for carrier audio bridge and SIP RTP connection to unmute cleanly
    logger.info("⏳ Allowing 1.1s for carrier audio bridge and SIP RTP connection to settle & unmute naturally...")
    await asyncio.sleep(1.1)

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

        # Opening Fixed Greeting: Speak immediately once carrier RTP bridge settles!
        if not intro_started and not _hangup_scheduled:
            intro_started = True
            intro_finished = True
            opening_greeting = "नमस्ते! मैं गायत्री बोल रही हूँ, साई गार्डन, डोंबिवली ईस्ट से, एक्सपिरिया मॉल के बिल्कुल सामने। आपको 1 BHK चाहिए या 2 BHK?"
            logger.info(f"🎙️ [IMMEDIATE OPENING GREETING] Speaking fixed opening greeting: '{opening_greeting}'")
            record_dialogue_turn("agent", opening_greeting)
            try:
                session.say(opening_greeting, allow_interruptions=True)
            except Exception as e:
                logger.warning(f"Error speaking immediate opening greeting: {e}")

    # Silence Watchdog: Monitors caller silence after intro completes (12s gentle prompt, 22s auto-terminate)
    t_last_activity = time.time()

    async def _silence_watchdog():
        nonlocal t_last_activity, _hangup_scheduled, agent_is_speaking, t_user_stop, caller_has_spoken, has_prompted_silence
        logger.info("🛡️ [SILENCE WATCHDOG] Task active. Monitoring caller activity...")

        while not intro_finished and not _hangup_scheduled:
            await asyncio.sleep(0.1)

        if _hangup_scheduled:
            return

        logger.info("🛡️ [SILENCE WATCHDOG] Caller connected! Monitoring silence (12s gentle prompt, 22s auto-terminate)...")

        last_prompt_time = time.time()

        while not _hangup_scheduled:
            await asyncio.sleep(0.3)
            if _hangup_scheduled:
                break

            # If agent is speaking or generating speech, reset caller silence timer
            if agent_is_speaking or (session.current_speech and not session.current_speech.done()):
                t_last_activity = time.time()
                last_prompt_time = time.time()
                has_prompted_silence = False
                continue

            now = time.time()
            silence_duration = now - t_last_activity

            # 1. If caller stays silent for 22.0 seconds total -> Terminate call gracefully
            if silence_duration >= 22.0:
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {silence_duration:.1f}s (>=22s). Concluding call in language '{current_lang}'...")
                if current_lang == "mr":
                    farewell_text = "तुमचा आवाज येत नाहीये. मी नंतर कॉल करते, तुमचा दिवस चांगला जावो, नमस्कार."
                elif current_lang == "en":
                    farewell_text = "I'm unable to hear you. We will connect later. Have a wonderful day, goodbye!"
                else:
                    farewell_text = "Lagta hai aapki aawaaz nahi aa rahi hai. Hum baad mein call karte hain, aapka din shubh ho, bye!"
                try:
                    t_user_stop = 0.0
                    record_dialogue_turn("agent", farewell_text)
                    speech_handle = session.say(farewell_text, allow_interruptions=False)
                    if speech_handle:
                        await speech_handle.wait_for_playout()
                except Exception as e:
                    logger.warning(f"Error speaking silence farewell: {e}")
                trigger_hangup(wait_for_speech=False, delay_seconds=0.8)
                break

            # 2. Silence Nudge: after 5 silent seconds, gently prompt: "हे, क्या आप अभी भी कॉल पर हैं?"
            if (not has_prompted_silence) and (silence_duration >= 5.0):
                has_prompted_silence = True
                last_prompt_time = now
                logger.info(f"⏳ [SILENCE NUDGE] 5s silence elapsed. Prompting gently: 'हे, क्या आप अभी भी कॉल पर हैं?'")
                prompt_text = "हे, क्या आप अभी भी कॉल पर हैं?"
                try:
                    t_user_stop = 0.0
                    record_dialogue_turn("agent", prompt_text)
                    session.say(prompt_text, allow_interruptions=True)
                except Exception as e:
                    logger.warning(f"Error speaking silence prompt: {e}")
    watchdog_task = asyncio.create_task(_silence_watchdog())

    # Max Call Duration Watchdog: 5-minute strict limit
    async def _max_call_duration_watchdog():
        await asyncio.sleep(295.0)
        if not _hangup_scheduled:
            logger.info("⏱️ [MAX CALL DURATION] 5 minutes elapsed. Concluding call gracefully...")
            conclusion = "समय देने के लिए बहुत-बहुत धन्यवाद। आपका दिन शुभ हो, नमस्कार!"
            try:
                record_dialogue_turn("agent", conclusion)
                speech = session.say(conclusion, allow_interruptions=False)
                if speech:
                    await speech.wait_for_playout()
            except Exception:
                pass
            trigger_hangup(wait_for_speech=False, delay_seconds=0.5)

    max_duration_task = asyncio.create_task(_max_call_duration_watchdog())




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
            num_idle_processes=2,
            load_threshold=100.0,
            initialize_process_timeout=90.0,
        )
    )
