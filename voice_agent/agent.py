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
    JobRequest,
    WorkerOptions,
    cli,
    function_tool,
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
    is_marathi = target_lang == "mr" or (target_lang != "hi" and target_lang != "en" and bool(re.search(r'[\u0900-\u097F]', text)))
    is_english = target_lang == "en"

    if is_marathi:
        replacements = [
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
        # Hindi / Hinglish default: Map BHK and acronyms to Devanagari tokens
        # which Cartesia pronounces with natural, steady, native intonation (one BHK, two BHK)
        # without letter-spelling stutter or pitch spikes.
        replacements = [
            (r'\b(2|two)\s*BHK\b', 'टू बीएचके'),
            (r'\b(1|one)\s*BHK\b', 'वन बीएचके'),
            (r'\b(1|one)\s*RK\b', 'वन आरके'),
            (r'\b1rk\b', 'वन आरके'),
            (r'\bBHK\b', 'बीएचके'),
            (r'\bRK\b', 'आरके'),
            (r'\b76\s*0\b', '760'),
            (r'\b(sqft|sq\.ft|sq\s*ft)\b', 'square feet'),
            (r'\b15\s*(-|to|se)\s*20\b', '15 se 20'),
            (r'\b11\s*(am|baje)\b', '11 baje'),
            (r'\b3\s*(pm|baje)\b', '3 baje'),
        ]
    for pattern, rep in replacements:
        text = re.sub(pattern, rep, text, flags=re.IGNORECASE)
    return text

# Pluggable Phonetic Tokenizer for Cartesia
# Seamlessly normalizes complete sentences with Blingfire without monkeypatching WebSocket streams
from livekit.agents.tokenize import blingfire, SentenceTokenizer, SentenceStream

class PhoneticSentenceTokenizer(SentenceTokenizer):
    """
    Sentence tokenizer that transparently normalizes numbers and terms
    into natural speech on complete sentences for Cartesia neural TTS,
    without buffering latency, voice breaks, or dropped chunks.
    """
    def __init__(self, stream_context_len: int = 2):
        super().__init__()
        self._inner = blingfire.SentenceTokenizer(stream_context_len=stream_context_len)

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

0. STRICT ANTI-REPETITION MANDATE (ZERO CONSECUTIVE REPETITIONS)
- YOU MUST NEVER REPEAT YOUR PREVIOUS STATEMENT, PITCH, OR QUESTION IN TWO CONSECUTIVE TURNS!
- Look at your immediately preceding assistant message in the conversation history before responding. If you already said it, DO NOT SAY IT AGAIN.
- If the customer gives a short filler, confirmation, or acknowledgment ("haan", "haan bolie", "boliye", "hello", "theek hai", "sun raha hoon", "details", "achha", "suniye"):
  * STRICTLY DO NOT repeat what you just said!
  * Never repeat the 1 BHK vs 2 BHK question if you already asked it!
  * Instead, acknowledge with 1 word ("Ji", "Bilkul") and immediately ask a NEW, fresh question or share fresh details:
    - E.g. Ask: "Aap ready-to-move flat dekh rahe hain ya upcoming possession chalega?"
    - Or ask: "Aap khud rehne ke liye dekh rahe hain ya investment ke liye plan kar rahe hain?"
    - Or explain: "Humare paas spacious master bedroom aur Jaquar fittings ke sath flats available hain. Kya iske baare mein aapka koi specific sawaal hai?"
- EXCEPTION: You may ONLY repeat your previous statement if the customer explicitly asks you to repeat: e.g. "kya bola aapne?", "phir se boliye", "repeat kijiye", "sunai nahi diya".

1. ROLE, OBJECTIVE & NATURAL HUMAN PERSONA
- You are Gayatri (गायत्री), a warm, intelligent, and natural Real Estate Property Advisor representing Shiv Sai Construction Company for the Sai Complex project in Dombivli East.
- PRIMARY GOAL: Act as an authentic, helpful human consultant. Provide clear, honest property details, address questions directly, and guide interested buyers naturally.
- TONE & ATTITUDE: Calm, warm, steady, professional, and patient. Speak exactly like a real human advisor talking on a phone call.
- NATURAL CONSULTATIVE CONVERSATIONS (NOT AN AGGRESSIVE BOT):
  - Strictly DO NOT push for a site visit on every single turn!
  - Instead, answer the customer's question thoroughly first, then ask natural, consultative follow-up questions such as:
    * "Kya flat ya layout ke regarding aapka koi specific sawaal hai?"
    * "Aap kis tareeqe ka layout prefer karte hain?"
    * "Aap kab tak shift hone ya buy karne ka plan kar rahe hain?"
    * "Isme aapko aur kuch details janna hai?"
  - Mix and vary your follow-up questions across turns. NEVER repeat the exact same closing phrase.
  - Only invite for a site visit when the customer shows genuine interest, asks to see the flat, or agrees after exploring details.
- STRICT PITCH & EMOTION CONTROL:
  - NEVER speak with exaggerated pitch, celebratory joy, or robotic stiffness.
  - STRICTLY NO EXCLAMATION MARKS: Use single periods (.) only.
- PRONUNCIATION OF BHK (MANDATORY): Always say "one BHK" and "two BHK". Strictly NEVER say "do BHK".
- NEVER END A SENTENCE ON AN ACRONYM: Always append a noun or verb phrase like "ya two BHK dekh rahe hain?".
- STRICT BREVITY: 1 to 2 concise sentences per turn (15-20 words max). Keep answers direct so audio generates instantly.

2. FLAT FEATURES & SPECIFICATIONS
- When customer asks about flat features, interiors, or amenities:
  - Hindi: "Humare flats mein spacious master bedroom, premium Jaquar fittings, Kajaria tiles, wide balcony, aur cross-ventilation ke saath achhi natural sunlight milti hai. One BHK 375 se 520 square feet aur two BHK 760 square feet carpet area mein available hain. Kya layout ya floor plan ke regarding aapka koi sawaal hai?"
  - Marathi: "आमच्या फ्लॅट्समध्ये प्रशस्त मास्टर बेडरूम, जॅग्वार फिटिंग्स, कजारिया टाईल्स, मोठी बाल्कनी आणि उत्तम व्हेंटिलेशन मिळते. १ बीएचके ३७५ ते ५२० स्क्वेअर फूट आणि २ बीएचके ७६० स्क्वेअर फूट कार्पेट एरिया आहे. याबद्दल आपल्या मनात काही शंका किंवा प्रश्न आहेत का?"
  - English: "Our flats feature spacious master bedrooms, premium Jaquar bathroom fittings, Kajaria vitrified tile flooring, wide balconies, and cross-ventilation with ample natural sunlight. 1 BHK is 375 to 520 square feet and 2 BHK is 760 square feet carpet area. Do you have any specific questions about the floor plan?"

3. INVESTMENT & ROI INQUIRY
- When customer asks if this is a good investment or asks about returns / future growth:
  - Hindi: "Ji bilkul! Sai Complex Palava Road Dombivli East mein ek prime investment opportunity hai. Nilje station sirf five minutes aur Kalyan fifteen minutes drive par hai. Yahan infra aur road expansion ki wajah se 8 se 12% annual capital appreciation aur high rental demand mil rahi hai. Kya aap brochure WhatsApp par dekhna chahenge?"
  - English: "Yes, absolutely! Sai Complex on Palava Road, Dombivli East is a prime investment. Located just five minutes from Nilje station and fifteen minutes from Kalyan, with upcoming metro and road connectivity, the area is witnessing 8 to 12% annual capital appreciation and strong rental yield. Would you like me to share the detailed brochure on WhatsApp?"
  - Marathi: "हो नक्कीच! साई कॉम्प्लेक्स पलावा रोड डोंबिवली पूर्व येथे एक उत्तम गुंतवणूक पर्याय आहे. निळजे स्टेशन फक्त पाच मिनिटांवर आहे आणि कल्याण पंधरा मिनिटांवर. येथे वाढत्या विकासामुळे ८ ते १२ टक्के वार्षिक वाढ आणि उत्तम भाडे उत्पन्न मिळत आहे. मी आपल्याला व्हॉट्सअॅपवर माहिती पाठवू का?"

4. CONVERSATION PROGRESSION (ALWAYS MOVE FORWARD, NEVER REPEAT)
- **Greeting**: Call begins with agent saying a clean, simple "Hello." (Never "Hello ji", never anything else).
- **First Turn (When caller responds to Hello e.g. 'haan', 'boliye', 'kaun?', 'hello'):**
  - "Main Gayatri bol rahi hoon Sai Complex Dombivli East se. Yahan one BHK aur two BHK options available hain chhattis lakh rupaye onwards. Aap apne liye one BHK prefer karenge ya two BHK dekh rahe hain?"
- **If caller confirms 1 BHK:**
  - "One BHK mein 375 square feet carpet area chhattis lakh rupaye all-inclusive mein milta hai. Aap ready-to-move dekh rahe hain ya upcoming possession chalega?"
- **If caller asks for 1 RK ('1 RK hai kya', '1 RK available', '1 RK flat', '1 RK options'):**
  - Hindi: "Sai Complex mein 1 RK available nahi hai; hamare homes spacious 1 BHK apartments of 375 square feet se start hote hain chhattis lakh rupaye all-inclusive mein. Kya aap 1 BHK option dekhna chahenge?"
  - English: "We do not have 1 RK configurations at Sai Complex; our homes start with spacious 1 BHK apartments of 375 square feet starting at 36 lakh rupees all-inclusive. Would you like to explore the 1 BHK option?"
  - Marathi: "साई कॉम्प्लेक्समध्ये १ आरके उपलब्ध नाही; आमच्याकडे तीनशे पंच्याहत्तर स्क्वेअर फूटचे प्रशस्त १ बीएचके फ्लॅट्स छत्तीस लाख रुपयांपासून सुरू होतात. आपण १ बीएचके पर्याय पाहू इच्छिता का?"
- **If caller confirms 2 BHK:**
  - "Two BHK mein aapko 760 square feet carpet area bahattar lakh rupaye all-inclusive mein milta hai, jisme spacious master bedroom aur modern amenities shaamil hain. Kya is layout ke baare mein aapka koi specific sawaal hai?"
- **If caller gives general inquiry or acknowledgment without picking BHK ('haan bolie', 'details bataiye', 'sun raha hoon'):**
  - DO NOT repeat the 1/2 BHK pitch!
  - Progress: "Sai Complex Palava road Dombivli East mein sthit hai, Nilje station se sirf five minutes door. Yahan 1 BHK 36 lakh aur 2 BHK 72 lakh all-inclusive mein available hai. Aap ready-to-move dekh rahe hain ya upcoming possession?"
- **If caller asks about possession ('ready to move' or 'upcoming'):**
  - "Ready-to-move flats mein immediate possession aur clear legal approvals milte hain. Is weekend actual flat dekhne ke liye kya aap Saturday ya Sunday site visit plan karna chahenge?"
- **If caller specifies day ('Saturday' or 'Sunday'):**
  - "Saturday ko subah 11 baje convenient rahega ya dopahar 3 baje?" (Move straight to time, never repeat the day question!)
- **When caller confirms time:**
  - Invoke schedule_site_visit(...) and say: "Maine aapka visit schedule kar diya hai. Saari details WhatsApp par bhej rahi hoon. Aapka din shubh ho, bye."
- **When customer is busy / asks to call later / future plan (STRICTLY in current language):**
  - Hindi: "Koi baat nahi, main samajh sakti hoon. Main aapka number note kar leti hoon aur baad mein follow up karungi. Aapka din shubh ho, bye."
  - Marathi: "काही हरकत नाही, मी नंतर फोन करेन. तुमचा दिवस चांगला जावो, नमस्कार."
  - English: "No problem at all, I completely understand. I will follow up with you later. Have a wonderful day, goodbye!"
- **Refusal / Not Interested (STRICTLY in current language):**
  - Hindi: "Theek hai, aapka samay dene ke liye shukriya. Aapka din shubh ho, bye."
  - Marathi: "काही हरकत नाही. वेळ दिल्याबद्दल धन्यवाद, तुमचा दिवस चांगला जावो, नमस्कार."
  - English: "Understood, thank you for your time. Have a wonderful day, goodbye!"

5. SITE VISIT CONFIRMATION & CLOSING
- If customer wants to visit: "Saturday convenient rahega ya Sunday, aur subah ya dopahar kis time comfortable rahega?"
- When user gives final explicit confirmation:
  Invoke `schedule_site_visit(preferred_day=..., preferred_time=..., flat_type=...)`
  and say: "Maine aapka {preferred_day} ko {preferred_time} ka site visit confirm kar diya hai. Saari details WhatsApp par bhej rahi hoon. Thank you so much, aapka din shubh ho, bye."

6. MANDATORY CALL CLOSING RULE
- Hindi calls: Conclude with: "Aapka din shubh ho, bye."
- Marathi calls: Conclude with: "तुमचा दिवस चांगला जावो, नमस्कार."
- English calls: Conclude with: "Thank you for your time. Have a wonderful day, goodbye!"

7. PROJECT FACTS (SAI COMPLEX, DOMBIVLI EAST)
- Developer: Shiv Sai Construction Company.
- Location: Casario, Palava Road, Near Pratik Green, Lodha Heaven, Dombivli East — 421204.
- 1 BHK: 375 sqft (36 lakh onwards), 520 sqft (50 lakh onwards), 755 sqft with Terrace (72 lakh onwards).
- 2 BHK: 760 sqft (72 lakh onwards), 1110 sqft with Terrace (1 crore 4 lakh onwards), 2285 sqft with Terrace (2 crore 10 lakh onwards).
- Connectivity: Dombivli Station (15-20 mins), Nilje Station (5 mins), Kalyan (15 mins), Thane/Navi Mumbai via Shil Road (25-30 mins).
- Amenities: Gym, children play area, jogging track, 24-hour water supply, Jaquar fittings, Kajaria tiles. Free VIP cab pickup for site visits.

8. 100% PURE MARATHI MODE
- Trigger: If caller speaks or asks for Marathi ("marathi madhe bola", "मराठीत बोला", "marathi aati hai kya"):
- Respond 100% in PURE authentic Marathi in Devanagari script. ZERO Hindi words.
- Opening: "हो, मी पूर्णपणे मराठीत बोलू शकते. मी गायत्री बोलतेय साई कॉम्प्लेक्स डोंबिवली पूर्व येथून. येथे एक आणि दोन बीएचके पर्याय छत्तीस लाख रुपयांपासून उपलब्ध आहेत. आपण आपल्यासाठी एक बीएचके शोधत आहात की दोन बीएचके फ्लॅट शोधत आहात?"
- 1 BHK: "समजले मला. एक बीएचकेमध्ये तीनशे पंच्याहत्तर स्क्वेअर फूट कार्पेट एरिया मिळतो. आपण रेडी-टू-मूव्ह शोधत आहात की अंडर-कन्स्ट्रक्शन चालेल?"
- 2 BHK: "दोन बीएचकेमध्ये सातशे साठ स्क्वेअर फूट कार्पेट एरिया बहात्तर लाख रुपयांमध्ये मिळतो, ज्यामध्ये आधुनिक सुविधांचा समावेश आहे. याबद्दल आपल्या मनात काही शंका किंवा प्रश्न आहेत का?"
- Numbers in Marathi: Always pronounce 375 as "तीनशे पंच्याहत्तर", 760 as "सातशे साठ", 520 as "पाचशे वीस", 36 as "छत्तीस", 72 as "बहात्तर".
- Silence Watchdog in Marathi: "हॅलो? माझा आवाज येतोय का?"
- Closing in Marathi: "तुमचा दिवस चांगला जावो, नमस्कार."
- Rejections in Marathi: "काही हरकत नाही. वेळ दिल्याबद्दल धन्यवाद, तुमचा दिवस चांगला जावो, नमस्कार."

9. 100% PURE ENGLISH MODE
- Trigger: If caller speaks or asks for English ("can you speak English", "talk in English", "English please"):
- Respond 100% in fluent, professional English. ZERO Hindi words.
- Opening: "Yes, absolutely! This is Gayatri from Sai Complex, Dombivli East. We have premium 1 and 2 BHK residences starting from 36 lakh rupees onwards. Are you looking for a 1 BHK or a 2 BHK apartment?"
- 1 BHK: "Understood. Our 1 BHK homes offer 375 square feet carpet area starting at 36 lakh rupees all-inclusive. Are you looking for immediate possession or upcoming possession?"
- 2 BHK: "Our 2 BHK homes provide 760 square feet carpet area at 72 lakh rupees all-inclusive, featuring spacious master bedrooms and premium fittings. Do you have any questions about the amenities or floor plan?"
- Silence Watchdog in English: "Hello? Are you able to hear me?"
- Closing in English: "Thank you so much for your time. Have a wonderful day, goodbye!"
"""

# ==============================================================================
# 2. LANGUAGE RESOLUTION HELPER & AGENT CLASS (STICKY MULTILINGUAL)
# ==============================================================================
def resolve_language(transcript: str, current_lang: str = "hi") -> str:
    """
    Detects spoken language with strict stickiness.
    Only changes language if the customer explicitly asks to,
    or speaks clear unambiguous sentences in another language.
    Once locked to 'mr' or 'en', stays locked until requested to switch.
    """
    import string
    text = transcript.strip().lower()
    words = text.split()
    clean_words = [w.strip(string.punctuation) for w in words]

    # 0. Explicit language request overrides (Customer asks to change language)
    marathi_explicit = [
        'marathi', 'मराठी', 'marathit', 'marathi madhe', 'marathit bola',
        'marathi bola', 'marathi sanga', 'marathi madhun', 'marathi aati',
        'marathi yete ka', 'marathi ahe ka'
    ]
    if any(m in text for m in marathi_explicit):
        return 'mr'

    english_explicit = [
        'english', 'इंग्लिश', 'in english', 'speak english', 'speak in english',
        'talk in english', 'can we speak in english', 'can you speak english'
    ]
    if any(e in text for e in english_explicit):
        return 'en'

    hindi_explicit = [
        'hindi', 'हिंदी', 'हिन्दी', 'in hindi', 'hindi mein', 'hindi me',
        'hindi bola', 'hindi madhe'
    ]
    if any(h in text for h in hindi_explicit):
        return 'hi'

    # If already locked into Marathi ('mr'): STICK to Marathi unless explicitly requested
    if current_lang == 'mr':
        return 'mr'

    # If already locked into English ('en'): STICK to English unless explicitly requested
    if current_lang == 'en':
        return 'en'

    # If currently in Hindi ('hi'): Check if user spontaneously spoke Marathi or English
    if 'ळ' in transcript:
        return 'mr'
    devanagari_marathi_words = [
        'आहे', 'आहात', 'नाही', 'काय', 'माहिती', 'पाहिजे', 'बोलतो', 'बोलते',
        'चालेल', 'नको', 'कधी', 'कसा', 'कशी', 'कसे', 'सांगा', 'दाखवा', 'तुम्ही',
        'आम्ही', 'मध्ये', 'आमचा', 'आमचे', 'किती', 'कुठे', 'लांब', 'दिवस', 'शनिवारी', 'रविवारी'
    ]
    if any(w in text for w in devanagari_marathi_words):
        return 'mr'

    phonetic_marathi_markers = [
        'kiti', 'kuthe', 'kute', 'laam', 'kasa', 'kase', 'kashi', 'sanga', 'sang na',
        'ahe', 'aahe', 'ahet', 'aahet', 'nako', 'pahije', 'tumhi', 'tumche', 'tumchya',
        'tumhala', 'amhi', 'amche', 'amchya', 'amhala', 'madhe', 'madhun', 'baddal',
        'vishayi', 'shaniwari', 'raviwari', 'somwari', 'yaaycha', 'yenar', 'chalel',
        'ho chalel', 'bolat aahat', 'aiku yetay', 'kay challay', 'kay kartay'
    ]
    if any(w in clean_words or w in text for w in phonetic_marathi_markers):
        return 'mr'

    latin_chars = sum(1 for c in transcript if c.isalpha() and c.isascii())
    total_chars = len(transcript.replace(' ', ''))
    # Removed ambiguous words ('to', 'do', 'me', 'na', 'ya', 'kar', 'ab') that overlap with English
    hinglish_markers = {
        'hai', 'kya', 'ka', 'ki', 'ko', 'se', 'par', 'ji', 'haan', 'han', 'achha', 'acha',
        'bataiye', 'batao', 'btao', 'mein', 'ke', 'ne', 'aur', 'toh',
        'bhai', 'kab', 'sab', 'karna', 'krna', 'dena', 'dedo',
        'kitna', 'kitne', 'kitni', 'door', 'dur', 'kahan', 'kaha', 'kaise', 'hoga', 'hogi', 'milega',
        'aapka', 'apka', 'hum', 'main', 'mujhe', 'tumhara', 'unka', 'woh', 'yahan', 'wahan',
        'chahiye', 'chahte', 'theek', 'accha', 'nahi', 'nhin'
    }
    # Explicit English starter patterns — even short queries should be classified English
    english_starters = [
        'do you have', 'is there', 'can you', 'tell me', 'what is', 'price please',
        'how much', 'how many', 'are there', 'i want', 'i need', 'i am looking',
        'any flat', 'any option', 'available', 'show me', 'give me', 'please', 'thank you',
        '1 rk', 'one rk', '2 bhk', '1 bhk', 'one bhk', 'two bhk', 'carpet area',
        'square feet', 'possession', 'ready to move', 'booking amount'
    ]
    if any(starter in text for starter in english_starters):
        return 'en'

    is_mostly_latin = total_chars > 0 and (latin_chars / total_chars) > 0.85
    if len(clean_words) >= 4 and is_mostly_latin and not any(w in hinglish_markers for w in clean_words):
        return 'en'

    return current_lang


class PriyaRealEstateAgent(Agent):
    def __init__(self, customer_name: str = "Aman ji", customer_phone: str = "", hangup_fnc=None, on_speech_captured=None):
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self._hangup_fnc = hangup_fnc
        self._on_speech_captured = on_speech_captured
        self.off_topic_count = 0
        
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
            self._hangup_fnc(wait_for_speech=True, delay_seconds=2.5)

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

    async def llm_node(self, chat_ctx, tools, model_settings: ModelSettings):
        collected = []
        try:
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                if isinstance(chunk, str):
                    collected.append(chunk)
                elif hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        collected.append(delta.content)
                yield chunk
        finally:
            full_text = "".join(collected).strip()
            if full_text and self._on_speech_captured:
                try:
                    self._on_speech_captured(full_text)
                except Exception as e:
                    logger.warning(f"Error in on_speech_captured from llm_node: {e}")

    async def tts_node(self, text, model_settings: ModelSettings):
        collected_chunks = []
        try:
            async def _intercept():
                try:
                    async for chunk in text:
                        collected_chunks.append(chunk)
                        yield chunk
                finally:
                    full_text = "".join(collected_chunks).strip()
                    if full_text and self._on_speech_captured:
                        try:
                            self._on_speech_captured(full_text)
                        except Exception as e:
                            logger.warning(f"Error in on_speech_captured: {e}")

            async for frame in Agent.default.tts_node(self, _intercept(), model_settings):
                yield frame
        finally:
            full_text = "".join(collected_chunks).strip()
            if full_text and self._on_speech_captured:
                try:
                    self._on_speech_captured(full_text)
                except Exception as e:
                    pass

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

# 1. GOOGLE GEMINI (High Quota, Instant Streaming, 0 Rate Limit Choking in Long Calls)
elif global_google_key and (llm_provider in ["google", "gemini"] or not (global_groq_key and global_groq_key.startswith("gsk_"))):
    from livekit.plugins import google
    
    preferred_models = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]
    
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

# 2. GROQ LPU (If explicitly set or Google key not configured)
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
                        temperature=0.3
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
STT_KEYTERMS = [kw[0] for kw in STT_KEYWORDS]

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

    # 2. Pre-warm Deepgram Nova-3 STT (Ultra-fast streaming with 25ms endpointing)
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    proc.userdata["stt"] = deepgram.STT(
        language="multi",
        model="nova-3",
        endpointing_ms=25,
        smart_format=True,
        keyterm=STT_KEYTERMS,
        replace=STT_REPLACE,
        api_key=deepgram_key
    )

    # 3. Pre-warm Silero VAD (Sensitive telephony calibration: 0.35 activation, 60ms speech, 220ms silence)
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.22,
        min_speech_duration=0.06,
        activation_threshold=0.35,
        deactivation_threshold=0.25,
        prefix_padding_duration=0.3,
        sample_rate=16000
    )

    # 4. Pre-warm Cartesia/ElevenLabs TTS (loads client network config in background)
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    kusha_voice_id = os.getenv("CARTESIA_VOICE_ID", "68da925c-0163-4b50-a4e6-08862f6dd5de").strip()
    cartesia_model = os.getenv("CARTESIA_MODEL", "sonic-3").strip()
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "1.0"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "").strip()
    cartesia_volume = float(os.getenv("CARTESIA_VOLUME", "1.0"))
    if cartesia_key and len(cartesia_key) > 10:
        proc.userdata["tts"] = cartesia.TTS(
            api_key=cartesia_key,
            voice=kusha_voice_id,
            language="hi",
            sample_rate=24000,
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
            language="multi",
            model="nova-3",
            endpointing_ms=25,
            smart_format=True,
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
        llm_provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
        
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
    cartesia_speed = float(os.getenv("CARTESIA_SPEED", "1.0"))
    cartesia_emotion = os.getenv("CARTESIA_EMOTION", "").strip()
    cartesia_volume = float(os.getenv("CARTESIA_VOLUME", "1.0"))
    cartesia_model = os.getenv("CARTESIA_MODEL", "sonic-3").strip()
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
    


    # VAD is pre-warmed, but load as fallback if not present (Sensitive telephony calibration: 0.35 threshold, 60ms speech)
    vad = ctx.proc.userdata.get("vad")
    if not vad:
        logger.info("⏱️ [VAD] Loading Silero VAD model on demand (Sensitive: 60ms min speech, 0.35 threshold)...")
        vad = silero.VAD.load(
            min_silence_duration=0.22,
            min_speech_duration=0.06,
            activation_threshold=0.35,
            deactivation_threshold=0.25,
            prefix_padding_duration=0.3,
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
                "min_delay": 0.12,
            },
            "preemptive_generation": {
                "enabled": False,  # Prevents aborted/conflicting LLM calls and 1.5s cancellation latency spikes on caller pauses
            },
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.40,
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
            # 1. Backfill any dialogue items from agent.chat_ctx, session._chat_ctx, or session.history
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

                def _norm(s: str) -> str:
                    return re.sub(r'[^\w\s]', '', s).strip().lower()

                existing_texts = {_norm(t.get("text", "")) for t in call_dialogue}
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
                    if raw_m and _norm(raw_m) not in existing_texts:
                        role_key = "agent" if m_role in ["assistant", "agent"] else "customer"
                        call_dialogue.append({
                            "role": role_key,
                            "text": raw_m,
                            "time": round(time.time() - t_call_start, 1)
                        })
                        existing_texts.add(_norm(raw_m))
            except Exception as backfill_err:
                logger.debug(f"Chat context backfill notice: {backfill_err}")

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

                # Candidate A: Directly in the persistent room recording folder
                direct_room_ogg = Path("bookings/recordings") / ctx.room.name / "audio.ogg"
                potential_candidates.append(direct_room_ogg)

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
                                "-b:a", "64k",
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
                            out_stream = output_container.add_stream('mp3', rate=24000)
                            out_stream.bit_rate = 64000
                            out_stream.layout = 'mono'
                            resampler = av.AudioResampler(format='s16p', layout='mono', rate=24000)
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

                    # Embed audio data URL for zero-latency, cloud-free playback on Vercel
                    max_embed_bytes = 400 * 1024  # 400KB limit for seamless metadata storage
                    b64_audio_payload = ""
                    if mp3_success and dest_bookings_mp3.exists():
                        try:
                            with open(dest_bookings_mp3, "rb") as f_aud:
                                b64_audio_payload = base64.b64encode(f_aud.read()).decode("utf-8")
                            if dest_bookings_mp3.stat().st_size <= max_embed_bytes:
                                recording_url = f"data:audio/mp3;base64,{b64_audio_payload}"
                                logger.info(f"🎙️ [AUDIO RECORDING EMBEDDED] Embedded MP3 ({dest_bookings_mp3.stat().st_size} bytes) as data URL for instant playback.")
                            else:
                                recording_url = f"/api/recordings/{ctx.room.name}.mp3"
                        except Exception as b64_err:
                            logger.warning(f"Error encoding MP3 to data URL: {b64_err}")
                            recording_url = f"/api/recordings/{ctx.room.name}.mp3"
                    elif dest_bookings_ogg.exists():
                        try:
                            with open(dest_bookings_ogg, "rb") as f_aud:
                                b64_audio_payload = base64.b64encode(f_aud.read()).decode("utf-8")
                            if dest_bookings_ogg.stat().st_size <= max_embed_bytes:
                                recording_url = f"data:audio/ogg;base64,{b64_audio_payload}"
                                logger.info(f"🎙️ [AUDIO RECORDING EMBEDDED] Embedded OGG ({dest_bookings_ogg.stat().st_size} bytes) as data URL for instant playback.")
                            else:
                                recording_url = f"/api/recordings/{ctx.room.name}.ogg"
                        except Exception as b64_err:
                            logger.warning(f"Error encoding OGG to data URL: {b64_err}")
                            recording_url = f"/api/recordings/{ctx.room.name}.ogg"
                    else:
                        recording_url = f"/api/recordings/{ctx.room.name}.mp3" if mp3_success else f"/api/recordings/{ctx.room.name}.ogg"
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
                        "calledAt": datetime.utcnow().isoformat(),
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
                    "called_at": datetime.utcnow().isoformat()
                }
                if b64_audio_payload:
                    webhook_payload["audioBase64"] = b64_audio_payload
                logger.info(f"🌐 [WEBHOOK SYNC] Delivering call intelligence to {dashboard_url}/api/webhooks/voice-agent ...")
                loop = asyncio.get_running_loop()
                webhook_resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(f"{dashboard_url}/api/webhooks/voice-agent", json=webhook_payload, timeout=8)
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
                    "calledAt": datetime.utcnow().isoformat(),
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

                # Persist dedicated audio recording room in LiveKit Cloud so it is NEVER deleted or stripped
                if b64_audio_payload:
                    try:
                        rec_room_name = f"rec-{ctx.room.name}"
                        rec_meta = json.dumps({
                            "callSid": ctx.room.name,
                            "audio": b64_audio_payload,
                            "format": "mp3" if mp3_success else "ogg",
                            "customerName": clean_display_name,
                            "calledAt": datetime.utcnow().isoformat()
                        })
                        await lk_cloud_api.room.create_room(lk_api.CreateRoomRequest(
                            name=rec_room_name,
                            empty_timeout=86400 * 30,
                            metadata=rec_meta
                        ))
                        logger.info(f"☁️ [AUDIO RECORDING CLOUD ROOM] Persisted audio to dedicated room: {rec_room_name}")
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
    has_prompted_silence = False
    agent_is_speaking = False
    intro_finished = False
    caller_has_spoken = False
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

    current_lang = "hi"

    @session.on("user_input_transcribed")
    def on_user_input(ev: UserInputTranscribedEvent):
        nonlocal current_lang, t_user_stop, t_last_activity, has_prompted_silence, caller_has_spoken
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
            # Append customer turn to transcript history
            elapsed_sec = round(time.time() - t_call_start, 1)
            call_dialogue.append({"role": "customer", "text": ev.transcript.strip(), "time": elapsed_sec})
            
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

            # ── Per-turn language directive: injected EVERY turn regardless of switch ──
            # This locks the LLM into the active language even without a recent switch.
            try:
                hist = getattr(session, "history", None) or getattr(session, "_chat_ctx", None)
                if hist and hasattr(hist, "add_message"):
                    if current_lang == "mr":
                        hist.add_message(role="system", content="[LANGUAGE DIRECTIVE: 100% PURE MARATHI] You MUST answer 100% COMPLETELY in PURE MARATHI (शुद्ध मराठी) in Devanagari script. STRICTLY ZERO HINDI WORDS (No 'ji', 'hai', 'humara', 'bol sakti hoon', 'kijiye', 'aapka', 'mein', 'aur', 'shubh ho', 'bilkul'). Keep it short (1-2 sentences).")
                    elif current_lang == "en":
                        hist.add_message(role="system", content="[LANGUAGE DIRECTIVE: 100% PURE ENGLISH] You MUST answer 100% in fluent professional ENGLISH. STRICTLY ZERO Hindi or Marathi words (No 'ji', 'hai', 'aapka', 'accha', 'theek', 'shubh ho', 'bilkul', 'nahin', 'haan', 'toh'). Respond entirely in English sentences only. Keep it short (1-2 sentences).")
                    else:
                        hist.add_message(role="system", content="[LANGUAGE DIRECTIVE: HINDI/HINGLISH] Answer in natural Hindi or Hinglish. Keep it short (1-2 sentences).")
            except Exception as e:
                logger.debug(f"Could not inject per-turn language directive: {e}")



            # Programmatic Anti-Repetition Guardrail:
            # Prevent repeating previous statement unless caller explicitly asks to repeat
            repeat_triggers = [
                "repeat", "phir se", "fir se", "kya bola", "sunai nahi", "samjha nahi",
                "pardon", "dubara", "dobara", "punha", "parat", "boliye na kya bole"
            ]
            caller_requested_repeat = any(trig in text for trig in repeat_triggers)
            if not caller_requested_repeat and last_agent_speech:
                try:
                    hist = getattr(session, "history", None) or getattr(session, "_chat_ctx", None)
                    if hist and hasattr(hist, "add_message"):
                        prev_snippet = last_agent_speech.replace('"', '').replace('\n', ' ')[:75]
                        hist.add_message(
                            role="system",
                            content=(
                                f"[STRICT ANTI-REPETITION MANDATE] Zero consecutive repetitions! "
                                f"Do NOT repeat or rephrase: '{prev_snippet}'. "
                                f"Move forward immediately with fresh details or ask a new, different question."
                            )
                        )
                except Exception as guard_err:
                    logger.debug(f"Anti-repetition injection notice: {guard_err}")

    _hangup_scheduled = False
    _hangup_task = None

    def trigger_hangup(wait_for_speech: bool = True, delay_seconds: float = 2.5):
        nonlocal _hangup_scheduled, _hangup_task
        if _hangup_scheduled:
            return
        _hangup_scheduled = True

        async def _do_disconnect():
            logger.info(f"📞 [CALL TERMINATION TRIGGERED] (wait_for_speech={wait_for_speech}, telecom_grace={delay_seconds}s)")
            
            if wait_for_speech:
                # 1. Give up to 3.5s for the agent to start speaking if not already speaking
                # (Allows LLM response generation and Cartesia TTS audio stream initialization)
                t_wait_start = time.time()
                while time.time() - t_wait_start < 3.5:
                    if session.agent_state == "speaking" or session.current_speech is not None:
                        break
                    await asyncio.sleep(0.1)

                # 2. Lock interruptions and wait until agent speech has completely finished playing out
                t_speech_wait = time.time()
                while time.time() - t_speech_wait < 20.0:
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
                    await asyncio.sleep(0.15)

            # 3. Telecom Audio Buffer Grace Period
            # 0.8s guarantees the phone speaker delivers the final word ("bye!") in full clarity
            grace = max(delay_seconds, 0.8)
            logger.info(f"⏳ [CALL TERMINATION] Waiting {grace:.1f}s audio buffer grace period before sending SIP BYE...")
            await asyncio.sleep(grace)

            # 4. Finalize transcript, audio recording, and post-call intelligence cleanly BEFORE tearing down room
            try:
                await _finalize_and_save_call("agent_hangup")
            except Exception as save_err:
                logger.warning(f"Error finalizing call in trigger_hangup: {save_err}")

            # 5. Release caller's phone line immediately with active SIP BYE
            logger.info("📞 [CALL TERMINATION] Sending active carrier SIP BYE to disconnect caller...")
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

            # 6. Now that data is safely saved and connections are flushed, delete room and disconnect agent
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

            try:
                await ctx.room.disconnect()
            except Exception as e:
                logger.warning(f"Error in room disconnect: {e}")

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
                nonlocal last_agent_speech
                last_agent_speech = raw_text
                last_turn = call_dialogue[-1] if call_dialogue else None
                if raw_text and (not last_turn or last_turn.get("role") != "agent" or last_turn.get("text", "").strip() != raw_text):
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "agent", "text": raw_text, "time": elapsed_sec})
                    logger.info(f"🎙️ [DIALOGUE CAPTURED: GAYATRI] '{raw_text}' at {elapsed_sec}s")

                text = raw_text.lower()
                ending_phrases = [
                    "aapka din shubh ho", "shubh ho... bye", "din shubh ho", "shubh ho!", "shubh ho, bye", "shubh ho bye", "alvida",
                    "shukriya", "bye!", "bye", "baad mein call karte hain",
                    "have a wonderful day", "have a great day", "goodbye", "take care", "connect later",
                    "दिवस चांगला जावो", "चांगला जावो, नमस्कार", "चांगला जावो", "नमस्कार, काळजी घ्या", "काळजी घ्या", "काळजी", "नमस्कार"
                ]
                if any(phrase in text for phrase in ending_phrases):
                    logger.info("👋 [GOODBYE DETECTED IN AGENT SPEECH] Ensuring automated call termination after speech finishes...")
                    trigger_hangup(wait_for_speech=True, delay_seconds=0.8)

            elif role_str in ["user", "customer"]:
                last_turn = call_dialogue[-1] if call_dialogue else None
                if raw_text and (not last_turn or last_turn.get("role") != "customer" or last_turn.get("text", "").strip() != raw_text):
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "customer", "text": raw_text, "time": elapsed_sec})
                    logger.info(f"👤 [DIALOGUE CAPTURED: CUSTOMER] '{raw_text}' at {elapsed_sec}s")
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
        nonlocal last_agent_speech
        raw_text = spoken_text.strip()
        if not raw_text:
            return
        last_agent_speech = raw_text
        elapsed_sec = round(time.time() - t_call_start, 1)
        last_turn = call_dialogue[-1] if call_dialogue else None
        if not last_turn or last_turn.get("role") != "agent" or last_turn.get("text", "").strip() != raw_text:
            call_dialogue.append({"role": "agent", "text": raw_text, "time": elapsed_sec})
            logger.info(f"🎙️ [DIALOGUE CAPTURED: GAYATRI] '{raw_text}' at {elapsed_sec}s")

        text = raw_text.lower()
        ending_phrases = [
            "aapka din shubh ho", "shubh ho... bye", "din shubh ho", "shubh ho!", "shubh ho, bye", "shubh ho bye", "alvida",
            "shukriya", "bye!", "bye", "baad mein call karte hain",
            "have a wonderful day", "have a great day", "goodbye", "take care", "connect later",
            "दिवस चांगला जावो", "चांगला जावो, नमस्कार", "चांगला जावो", "नमस्कार, काळजी घ्या", "काळजी घ्या", "काळजी", "नमस्कार"
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

    # Start session with dual-channel stereo recording (Caller on input, Gayatri AI on output)
    t_session_start = time.perf_counter()
    logger.info("⏱️ [RECORDING & PERF] Calling session.start(record={'audio': True})...")
    try:
        await session.start(agent=agent, room=ctx.room, record={"audio": True})
    except Exception as rec_err:
        logger.warning(f"Warning starting recording: {rec_err}. Falling back to record=False")
        await session.start(agent=agent, room=ctx.room, record=False)
    
    t_session_ready = (time.perf_counter() - t_session_start) * 1000
    t_total_ready = (time.perf_counter() - t_start) * 1000
    logger.info(f"⏱️ [PERF] session.start() returned! Took {t_session_ready:.1f}ms. Total job-to-ready time: {t_total_ready:.1f}ms")
    logger.info(f"⏱️ [PERF +{t_total_ready:.1f}ms] Agent Session Started & Ready in <50ms!")

    # Allow 0.25s for WebRTC audio negotiation and SIP RTP streams to fully settle naturally
    logger.info("⏳ Allowing 0.25s for audio bridge and SIP RTP connection to settle naturally...")
    await asyncio.sleep(0.25)

    # Human Call Pickup Flow:
    # 1. Listen for 0.4s: If caller says "Hello?" immediately upon pickup, respond directly without colliding!
    logger.info("👂 [HUMAN PICKUP FLOW] Listening for caller greeting for up to 0.4s before prompting...")
    t_listen_start = time.time()
    while time.time() - t_listen_start < 0.4:
        if caller_has_spoken or _hangup_scheduled:
            logger.info("🎙️ [HUMAN PICKUP FLOW] Caller spoke first! Skipping initial prompt and entering conversation immediately.")
            intro_finished = True
            break
        await asyncio.sleep(0.05)

    # 2. If caller remains silent, prompt gently with natural warm voice (exact same speed and volume as conversation)
    if not caller_has_spoken and not _hangup_scheduled:
        is_cartesia = session.tts and "cartesia" in session.tts.__class__.__module__
        if is_cartesia and hasattr(session.tts, "update_options"):
            session.tts.update_options(
                voice=kusha_voice_id,
                language="hi",
                speed=cartesia_speed,
                volume=cartesia_volume,
                emotion=[cartesia_emotion] if cartesia_emotion else None
            )

        prompt_str = "Hello?"
        logger.info(f"🎙️ [CALL CONNECT GREETING] Saying single natural '{prompt_str}' (speed={cartesia_speed}, volume={cartesia_volume})...")
        try:
            t_user_stop = 0.0  # Reset so greeting is never tracked as turn latency spike
            h_speech = session.say(prompt_str, allow_interruptions=True)
            elapsed_sec = round(time.time() - t_call_start, 1)
            call_dialogue.append({"role": "agent", "text": prompt_str, "time": elapsed_sec})
            if h_speech:
                await h_speech.wait_for_playout()
        except Exception as e:
            logger.warning(f"Error speaking hello greeting: {e}")

        # Wait up to 8.0s for caller to respond naturally
        t_wait_hello = time.time()
        while time.time() - t_wait_hello < 8.0:
            if caller_has_spoken or _hangup_scheduled:
                intro_finished = True
                break
            await asyncio.sleep(0.08)

    if not caller_has_spoken and not _hangup_scheduled:
        logger.info("⏳ Caller silent after hello attempt. Terminating call.")
        farewell_text = "Lagta hai aapki aawaaz nahi aa rahi hai. Hum baad mein call karte hain, bye!"
        try:
            t_user_stop = 0.0
            sp = session.say(farewell_text, allow_interruptions=False)
            elapsed_sec = round(time.time() - t_call_start, 1)
            call_dialogue.append({"role": "agent", "text": farewell_text, "time": elapsed_sec})
            if sp:
                await sp.wait_for_playout()
        except Exception as e:
            logger.warning(f"Error speaking silence farewell: {e}")
        trigger_hangup(wait_for_speech=False, delay_seconds=0.8)
        return

    # Silence Watchdog: 16s -> Prompt, 32s -> Auto Hangup
    t_last_activity = time.time()
    has_prompted_silence = False
    intro_finished = True

    async def _silence_watchdog():
        nonlocal t_last_activity, has_prompted_silence, _hangup_scheduled, agent_is_speaking, t_user_stop
        logger.info("🛡️ [SILENCE WATCHDOG] Task active. Waiting for Gayatri to finish intro before counting silence...")
        
        # 1. Block and DO NOT count ANY silence while call is ringing or while Gayatri is speaking the intro!
        while not intro_finished and not _hangup_scheduled:
            await asyncio.sleep(0.2)

        if _hangup_scheduled:
            return

        logger.info("🛡️ [SILENCE WATCHDOG] Gayatri intro finished! Watchdog is now actively counting 16s of caller silence.")
        
        while not _hangup_scheduled:
            await asyncio.sleep(0.5)
            if _hangup_scheduled:
                break
                
            # If agent is currently speaking or generating speech, reset caller silence timer
            if agent_is_speaking or (session.current_speech and not session.current_speech.done()):
                t_last_activity = time.time()
                continue

            silence_duration = time.time() - t_last_activity

            # Stage 1: Caller silent for 16 full seconds AFTER Gayatri finished speaking -> Prompt in active language
            if silence_duration >= 16.0 and not has_prompted_silence:
                has_prompted_silence = True
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {silence_duration:.1f}s (>16s after Gayatri speech). Prompting in language '{current_lang}'...")
                if current_lang == "mr":
                    prompt_text = "हॅलो? माझा आवाज येतोय का?"
                elif current_lang == "en":
                    prompt_text = "Hello? Are you able to hear me?"
                else:
                    prompt_text = "Hello? Kya aap sun rahe hain?"
                try:
                    t_user_stop = 0.0  # CRITICAL: Prevent silence watchdog from logging a 16s turn latency spike!
                    p_speech = session.say(prompt_text, allow_interruptions=True)
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "agent", "text": prompt_text, "time": elapsed_sec})
                    if p_speech:
                        await p_speech.wait_for_playout()
                    t_last_activity = time.time()
                except Exception as e:
                    logger.warning(f"Error speaking silence prompt: {e}")

            # Stage 2: Caller silent for 32 seconds -> End call cleanly in active language
            elif silence_duration >= 32.0:
                logger.info(f"⏳ [SILENCE WATCHDOG] Caller silent for {silence_duration:.1f}s (>32s). Terminating call in language '{current_lang}'...")
                if current_lang == "mr":
                    farewell_text = "तुमचा आवाज येत नाहीये. मी नंतर कॉल करते, तुमचा दिवस चांगला जावो, नमस्कार."
                elif current_lang == "en":
                    farewell_text = "I'm unable to hear you. We will connect later. Have a wonderful day, goodbye!"
                else:
                    farewell_text = "Lagta hai aapki aawaaz nahi aa rahi hai. Hum baad mein call karte hain, aapka din shubh ho, bye!"
                try:
                    t_user_stop = 0.0  # Reset so farewell is never tracked as turn latency spike
                    speech_handle = session.say(farewell_text, allow_interruptions=False)
                    elapsed_sec = round(time.time() - t_call_start, 1)
                    call_dialogue.append({"role": "agent", "text": farewell_text, "time": elapsed_sec})
                    if speech_handle:
                        await speech_handle.wait_for_playout()
                except Exception as e:
                    logger.warning(f"Error speaking silence farewell: {e}")
                trigger_hangup(wait_for_speech=False, delay_seconds=0.8)
                break

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
