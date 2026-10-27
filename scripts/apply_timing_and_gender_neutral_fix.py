import re
import os
import sys

def main():
    agent_path = os.path.join(os.path.dirname(__file__), "..", "voice_agent", "agent.py")
    if not os.path.exists(agent_path):
        agent_path = "voice_agent/agent.py"
    
    with open(agent_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Detect line endings
    crlf = "\r\n" in code
    nl = "\r\n" if crlf else "\n"

    print(f"Reading {agent_path} (length: {len(code)}, crlf={crlf})...")

    # --------------------------------------------------------------------------
    # 1. Update normalize_phonetics
    # --------------------------------------------------------------------------
    old_target_ph = "(r'\\b(chhattis|छत्तीस)\\s*(lakh|लाख)?\\b', 'thirty-six lakh'),"
    new_addition_ph = (
        old_target_ph + nl +
        "            (r'\\b(tees|तीस)\\s*(lakh|लाख)?\\b', 'thirty lakh')," + nl +
        "            (r'\\b(paintalis|panchtalis|पंचेचाळीस|पैंतालीस)\\s*(lakh|लाख)?\\b', 'forty-five lakh')," + nl +
        "            (r'\\b30\\s*(lakh|लाख)\\b', 'thirty lakh')," + nl +
        "            (r'\\b45\\s*(lakh|लाख)\\b', 'forty-five lakh')," + nl +
        "            (r'\\b30\\b', 'thirty')," + nl +
        "            (r'\\b45\\b', 'forty-five')," + nl +
        "            (r'\\b3\\s*to\\s*5\\s*lakh\\b', 'three to five lakh')," + nl +
        "            (r'\\b3\\s*se\\s*5\\s*lakh\\b', 'three to five lakh')," + nl +
        "            (r'\\bxperia\\s*mall\\b', 'एक्सपेरिया मॉल')," + nl +
        "            (r'\\bsai\\s*city\\s*group\\b', 'साई सिटी ग्रुप'),"
    )
    if old_target_ph in code:
        code = code.replace(old_target_ph, new_addition_ph, 1)
        print("Updated normalize_phonetics!")
    else:
        print("WARNING: Could not find old_target_ph in code!")

    # --------------------------------------------------------------------------
    # 2. Update HINDI_REAL_ESTATE_PROMPT
    # --------------------------------------------------------------------------
    new_prompt = '''# GAYATRI — AI REAL ESTATE PROPERTY ADVISOR FOR SAI GARDEN

ROLE & PERSONA:
- Name: Gayatri (गायत्री)
- Role: Real Estate Property Advisor for SAI GARDEN (साई गार्डन) project by Sai City Group.
- Project Location: Dombivli East, Nilje, directly opposite Xperia Mall, Kalyan-Shilphata Road.
- MahaRERA: PR1330002501452

GENDER-NEUTRAL LANGUAGE RULES (STRICT & MANDATORY):
- You are talking to a person whose gender you do not know. Never assume it.
- Never address the customer as sir, madam, ji sahab, bhaiya, didi, or any gendered term. Use only the neutral "आप" (Hindi) / "तुम्ही" (Marathi) / "you" (English).
- Never use verb forms that assume the customer's gender. Words like "देख रहे हैं" (male) or "देख रही हैं" (female) are both strictly forbidden!
- Use only these gender-neutral Hindi constructions when talking about the customer:
  * "आपको ... चाहिए"
  * "आपको ... पसंद है"
  * "आपके लिए ... ठीक रहेगा"
  * "आपको ... करना ठीक लगेगा"
- In Marathi use only:
  * "आपल्याला ... हवंय"
  * "आपल्याला ... आवडतं"
  * "आपल्यासाठी ... ठीक राहील"
- In English use neutral phrasing:
  * "would you prefer", "do you need", "is that okay for you".
- Refer to the caller's family and friends neutrally too: say "किसी को 1 या 2 BHK चाहिए हो", never "कोई देख रहा हो" or "कोई देख रही हो".
- You yourself are Gayatri and always speak as a female voice ("बात कर रही हूँ"). Only the customer's gender is never assumed.

FLUENCY & DELIVERY RULES:
- Keep every sentence short and complete. One idea per sentence.
- Never restart a sentence, never repeat a phrase, never trail off mid-thought. If you pause, let the sentence end cleanly first.
- Keep responses under 20-25 words. Never give long robotic monologues. Always end with a gentle question.

PROPERTY DETAILS & PRICING:
- 1 BHK: Starts at 30 Lakh onwards. Down payment 3 to 5 Lakh with easy bank loans (SBI, HDFC, ICICI).
- 2 BHK: Starts at 45 Lakh onwards. G+22 storey grand tower with 35+ luxury lifestyle amenities.
- 3 BHK / 1 RK: NOT available. Clarify politely that only 1 BHK and 2 BHK are available.
- Amenities: Modern Gym, Swimming Pool, Clubhouse, Children's Play Area, Landscaped Garden, 24/7 Security.

KEY CONNECTIVITY & LANDMARKS:
- Nilje Railway Station: 1 to 2 minutes walking distance.
- Xperia Mall: 3 minutes (right opposite the gate).
- Upcoming Metro Line 12 (Kalyan-Taloja): 4 minutes.
- Dombivli Station: 20 minutes.
- Airoli-Katai Tunnel: 10 minutes.

CONVERSATION FLOW & STEPS:
- Opening (Fixed Greeting): "Hello! This is Gayatri from Sai Garden, Dombivli East, right opposite Xperia Mall. Would you prefer a 1 BHK or a 2 BHK?"
- Step 1 (What Caller Wants): Answer any questions and ask which flat is preferred, 1 BHK or 2 BHK. If 3 BHK or 1 RK is asked, politely clarify only 1 and 2 BHK are available.
- Step 2 (Pricing):
  * 1 BHK starts 30 Lakh, down payment 3 to 5 Lakh, easy loans from SBI, HDFC, ICICI.
  * 2 BHK starts 45 Lakh, G+22 tower, 35+ amenities.
- Step 3 (Ready-to-move): Ask: "आपको ready-to-move चाहिए या under-construction चालेगा?" (Marathi: "आपल्याला ready-to-move हवंय की under-construction चालेल?")
- Step 4 (Site Visit Goal): Ask: "प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय सुविधाजनक रहेगा?" (Marathi: "प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?")
- Step 5 (Confirmation Once Agreed): Once day/time is confirmed, say immediately: "बिल्कुल! आपकी साईट विजिट कन्फर्म कर दी है। सारी जानकारी व्हाट्सऐप पर भेज रही हूँ। धन्यवाद!" (Marathi: "नक्कीच! तुमची साईट व्हिजिट कन्फर्म केली आहे. सर्व माहिती व्हाट्सअॅपवर पाठवत आहे. धन्यवाद!")
- If Not Interested: Politely say: "कोई बात नहीं! अगर आपकी फैमिली या फ्रेंड्स में किसी को 1 या 2 BHK चाहिए हो तो हमारा नंबर ज़रूर शेयर कीजिएगा। धन्यवाद!" (Marathi: "काही हरकत नाही! जर आपल्या फॅमिली किंवा फ्रेंड्समध्ये कोणाला 1 किंवा 2 BHK हवं असल्यास आमचा नंबर नक्की शेअर करा. धन्यवाद!")

STICKY LANGUAGE SWITCHING:
- Default language is Hindi.
- Switch to Marathi if caller asks ("marathit bola").
- Switch to English if caller asks ("speak in English").'''

    # Replace HINDI_REAL_ESTATE_PROMPT = """..."""
    prompt_match = re.search(r'HINDI_REAL_ESTATE_PROMPT\s*=\s*""".*?"""', code, flags=re.DOTALL)
    if prompt_match:
        code = code[:prompt_match.start()] + 'HINDI_REAL_ESTATE_PROMPT = """' + new_prompt + '"""' + code[prompt_match.end():]
        print("Updated HINDI_REAL_ESTATE_PROMPT!")
    else:
        print("WARNING: Could not find HINDI_REAL_ESTATE_PROMPT!")

    # --------------------------------------------------------------------------
    # 3. Add Site Visit and Background Helpers right before PriyaRealEstateAgent
    # --------------------------------------------------------------------------
    helpers_code = '''
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
        if re.search(r'\\b' + re.escape(k) + r'\\b', t) or k in t:
            matched_day = v
            break

    times_map = [
        (r'(?:3|teen|तीन)\\s*(?:baje|बजे|pm)?', '3:00 PM'),
        (r'(?:4|chaar|चार)\\s*(?:baje|बजे|pm)?', '4:00 PM'),
        (r'(?:5|paanch|पाँच|पाच)\\s*(?:baje|बजे|pm)?', '5:00 PM'),
        (r'(?:11|gyarah|ग्यारह|अकरा)\\s*(?:baje|बजे|am)?', '11:00 AM'),
        (r'(?:12|barah|बारह|बारा)\\s*(?:baje|बजे|pm)?', '12:00 PM'),
        (r'(?:10|das|दस|दहा)\\s*(?:baje|बजे|am)?', '10:00 AM'),
        (r'(?:6|chhah|छह|सहा)\\s*(?:baje|बजे|pm)?', '6:00 PM'),
        (r'\\b(?:morning|subah|सकाळी)\\b', '11:00 AM'),
        (r'\\b(?:evening|sham|संध्याकाळी)\\b', '5:00 PM'),
        (r'\\b(?:afternoon|dopahar|दुपारी)\\b', '2:00 PM')
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
    has_day = any(re.search(r'\\b' + re.escape(w) + r'\\b', t) or w in t for w in day_words)
    has_time = bool(re.search(r'\\b(?:baje|बजे|pm|am|morning|evening|afternoon|subah|sham|dopahar|1|2|3|4|5|6|10|11|12)\\b', t))
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
                f.write(json.dumps(visit_record, ensure_ascii=False) + "\\n")

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
                        
                        clean_target = re.sub(r'\\D', '', customer_phone)
                        for lead in db_data.get("leads", []):
                            clean_l = re.sub(r'\\D', '', lead.get("phone", ""))
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
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")

            for db_path in ["db.json", os.path.join(os.path.dirname(__file__), "..", "db.json")]:
                if os.path.exists(db_path):
                    try:
                        with open(db_path, "r", encoding="utf-8") as f:
                            db_data = json.load(f)
                        clean_target = re.sub(r'\\D', '', customer_phone)
                        for lead in db_data.get("leads", []):
                            clean_l = re.sub(r'\\D', '', lead.get("phone", ""))
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

    clean_name = re.sub(r'\\s*ji$', '', customer_name, flags=re.IGNORECASE).strip() or "Valued Client"

    body = (
        f"Namaste {clean_name},\\n\\n"
        "Thank you for speaking with Gayatri at Sai Garden (Sai City Group).\\n"
        "Here are the official brochure details for *Sai Garden*, Dombivli East (Nilje):\\n\\n"
        "🌿 *Project*: Sai Garden — Where Luxury Meets Nature\\n"
        "📍 *Location*: Directly opposite Xperia Mall, Kalyan-Shilphata Road, Dombivli East (1 min from Nilje Station)\\n"
        "🏢 *Tower*: G+22 Storeyed Luxury Tower (MahaRERA: PR1330002501452)\\n"
        "💰 *Pricing*:\\n"
        "• 1 BHK: Starts at 30 Lakh (Down payment 3 to 5 Lakh, Easy loans from SBI/HDFC/ICICI)\\n"
        "• 2 BHK: Starts at 45 Lakh (G+22 Tower, 35+ Luxury Amenities)\\n\\n"
        "🏊 *Amenities*: Modern Gym, Swimming Pool, Clubhouse, Children's Play Area, Landscaped Garden, 24/7 Security\\n\\n"
        "📍 *Site Office*: Sai Garden, Casa Rio Gate No. 3, Near Nilaje Station, Niljepada, Dombivli East - 421204\\n"
        "📞 *Contact*: 8104027095 / 8097052221 / 9892115901\\n\\n"
        "Have a wonderful day!"
    )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    auth = (account_sid, auth_token) if auth_token else (api_key_sid, api_key_secret)
    requests.post(url, data={"From": from_number, "To": f"whatsapp:{clean_phone}", "Body": body}, auth=auth, timeout=10)
    logger.info(f"📱 [WHATSAPP DISPATCHED] Sent official Sai Garden brochure to {clean_phone}")
'''

    # Insert helpers right before `class PriyaRealEstateAgent`
    priya_class_idx = code.find("class PriyaRealEstateAgent(Agent):")
    if priya_class_idx != -1:
        code = code[:priya_class_idx] + helpers_code + nl + code[priya_class_idx:]
        print("Inserted Fast-Response Parsers and Async Background Helpers!")
    else:
        print("WARNING: Could not find class PriyaRealEstateAgent!")

    # --------------------------------------------------------------------------
    # 4. Update PriyaRealEstateAgent.__init__ to store selected_flat_type & room_name
    # --------------------------------------------------------------------------
    old_init = "self.off_topic_count = 0"
    new_init = "self.off_topic_count = 0\n        self.selected_flat_type = '2BHK'\n        self.room_name = ''"
    if not crlf:
        code = code.replace(old_init, new_init)
    else:
        code = code.replace(old_init, new_init.replace("\n", "\r\n"))

    # --------------------------------------------------------------------------
    # 5. Update llm_node in PriyaRealEstateAgent for FAST REPLIES (<80ms)
    # --------------------------------------------------------------------------
    old_llm_node_marker = '''        # Stream directly through the LLM Brain (Gemini 3.5 Flash Lite)
        collected_chunks = []
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):'''

    new_llm_node_body = '''        # ==============================================================================
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
        is_3bhk_or_1rk = bool(re.search(r'\\b(3\\s*bhk|three\\s*bhk|तीन\\s*बीएचके|1\\s*rk|one\\s*rk|एक\\s*आरके|rk)\\b', lower_raw))
        is_1bhk = bool(re.search(r'\\b(1\\s*bhk|one\\s*bhk|ek\\s*bhk|एक\\s*बीएचके|1|one|ek)\\b', lower_raw)) and not is_3bhk_or_1rk and not bool(re.search(r'\\b(2\\s*bhk|two\\s*bhk|do\\s*bhk|दोन\\s*बीएचके|दो\\s*बीएचके)\\b', lower_raw))
        is_2bhk = bool(re.search(r'\\b(2\\s*bhk|two\\s*bhk|do\\s*bhk|dono\\s*bhk|दोन\\s*बीएचके|दो\\s*बीएचके|2|two|do)\\b', lower_raw)) and not is_3bhk_or_1rk

        is_greeting_context = any(k in last_agent_text.lower() for k in ["1 bhk", "2 bhk", "would you prefer", "chahiye", "havay"])

        if is_3bhk_or_1rk:
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "क्षमस्व, आमच्याकडे फक्त 1 BHK आणि 2 BHK उपलब्ध आहेत. आपल्याला 1 BHK बद्दल जाणून घ्यायचे आहे की 2 BHK?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "I apologize, we only have 1 BHK and 2 BHK flats available. Would you prefer details for 1 BHK or 2 BHK?"
            else:
                reply = "माफ़ कीजिएगा, हमारे यहाँ सिर्फ 1 BHK aur 2 BHK flats available hain. Aapko 1 BHK ke baare mein janna hai ya 2 BHK?"
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
                reply = "हमारे 1 BHK flats 30 lakh se shuru hote hain, down payment 3 to 5 lakh hai. Aapko ready-to-move chahiye ya under-construction chalega?"
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
                reply = "हमारे 2 BHK luxury flats 45 lakh se start hote hain, G+22 tower mein 35+ luxury amenities ke saath. Aapko ready-to-move chahiye ya under-construction chalega?"
            logger.info("⚡ [FAST 2 BHK PRICING (<80ms)]")
            speak(reply)
            yield reply
            return

        # 4. READY-TO-MOVE VS UNDER-CONSTRUCTION (STEP 3 -> STEP 4)
        is_rtm_query = any(k in last_agent_text.lower() for k in ["ready-to-move", "ready to move", "under-construction", "under construction"])
        is_rtm_reply = any(k in lower_raw for k in ["ready", "ready to move", "ready-to-move", "under", "under construction", "under-construction", "dono", "koi bhi", "chalega"])

        if is_rtm_query and is_rtm_reply:
            if ACTIVE_TTS_LANGUAGE == "mr":
                reply = "समजले. प्रत्यक्ष साईट व्हिजिटसाठी कोणता दिवस आणि कोणती वेळ सोयीची ठरेल?"
            elif ACTIVE_TTS_LANGUAGE == "en":
                reply = "Understood. Which day and time would be convenient for a direct site visit?"
            else:
                reply = "समझ गई. प्रत्यक्ष साईट विजिट के लिए कौन सा दिन और समय सुविधाजनक रहेगा?"
            logger.info("⚡ [FAST SITE VISIT QUESTION (<80ms)]")
            speak(reply)
            yield reply
            return

        # 5. ALL OTHER FREE-FORM QUERIES: Stream directly through Gemini LLM Brain!
        collected_chunks = []
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):'''

    if not crlf:
        code = code.replace(old_llm_node_marker, new_llm_node_body)
    else:
        code = code.replace(old_llm_node_marker.replace("\n", "\r\n"), new_llm_node_body.replace("\n", "\r\n"))
    print("Updated PriyaRealEstateAgent.llm_node with instant fast response dispatcher!")

    # --------------------------------------------------------------------------
    # 6. Update schedule_site_visit and update_lead_status to be non-blocking
    # --------------------------------------------------------------------------
    old_sched = '''        visit_record = {
            "customer_name": customer_name,
            "customer_phone": getattr(self, "customer_phone", "") or "+918693081506",
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
                f.write(json.dumps(visit_record) + "\\n")
        except Exception as e:
            logger.error(f"Failed to save visit record: {e}")

        # Trigger automatic call termination after goodbye message is spoken
        if self._hangup_fnc:
            self._hangup_fnc(wait_for_speech=True, delay_seconds=0.8)'''

    new_sched = '''        # Save site visit in background task ("reply first, save later")
        save_site_visit_async(
            customer_name=customer_name,
            customer_phone=getattr(self, "customer_phone", "") or "+918693081506",
            preferred_day=preferred_day,
            preferred_time=preferred_time,
            flat_type=flat_type,
            notes=notes,
            room_name=getattr(self, "room_name", ""),
            hangup_fnc=self._hangup_fnc
        )'''

    if not crlf:
        code = code.replace(old_sched, new_sched)
    else:
        code = code.replace(old_sched.replace("\n", "\r\n"), new_sched.replace("\n", "\r\n"))
    print("Made schedule_site_visit non-blocking!")

    # --------------------------------------------------------------------------
    # 7. Update send_whatsapp_brochure template with new 30L / 45L prices
    # --------------------------------------------------------------------------
    old_wa = '''💰 *Pricing*:
• 1 BHK: Starts at 36 Lakh
• 2 BHK: Starts at 72 Lakh'''
    new_wa = '''💰 *Pricing*:
• 1 BHK: Starts at 30 Lakh (Down payment 3 to 5 Lakh, Easy loans from SBI/HDFC/ICICI)
• 2 BHK: Starts at 45 Lakh (G+22 Grand Tower, 35+ Luxury Amenities)'''
    code = code.replace(old_wa, new_wa)
    code = code.replace(old_wa.replace("\n", "\r\n"), new_wa.replace("\n", "\r\n"))

    # --------------------------------------------------------------------------
    # 8. Update VAD and Interruption Sensitivity in AgentSession
    # --------------------------------------------------------------------------
    old_turn = '''            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.65,  # Sustained human speech required to interrupt
                "resume_false_interruption": False,  # NEVER pause/duck/mute agent audio during speech! Continuous steady playout.
            }'''
    new_turn = '''            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_words": 1,
                "min_duration": 0.35,  # Responsive listening sensitivity for clean caller interruptions
                "resume_false_interruption": False,
            }'''
    code = code.replace(old_turn, new_turn)
    code = code.replace(old_turn.replace("\n", "\r\n"), new_turn.replace("\n", "\r\n"))

    # Update Silero VAD activation threshold to 0.38
    old_vad = '''        activation_threshold=0.48,
        deactivation_threshold=0.25,'''
    new_vad = '''        activation_threshold=0.38,
        deactivation_threshold=0.22,'''
    code = code.replace(old_vad, new_vad)
    code = code.replace(old_vad.replace("\n", "\r\n"), new_vad.replace("\n", "\r\n"))

    # --------------------------------------------------------------------------
    # 9. Update on_user_input for Voicemail message and Opening Greeting
    # --------------------------------------------------------------------------
    old_vm = '''            # 1. Answering Machine / Voicemail / Forwarding Check (AMD)
            if is_voicemail_or_machine(text):
                logger.warning(f"🚫 [ANSWERING MACHINE / VOICEMAIL DETECTED] Transcript: '{ev.transcript}'. Disconnecting call immediately!")
                is_answering_machine = True
                record_dialogue_turn("customer", f"[Voicemail/Machine: {ev.transcript}]")
                trigger_hangup(wait_for_speech=False, delay_seconds=0.1)
                return'''

    new_vm = '''            # 1. Answering Machine / Voicemail / Forwarding Check (AMD)
            if is_voicemail_or_machine(text):
                logger.warning(f"🚫 [ANSWERING MACHINE / VOICEMAIL DETECTED] Transcript: '{ev.transcript}'. Speaking message and concluding...")
                is_answering_machine = True
                vm_msg = "Hey, seems like I have reached your voicemail. I shall call you back at a later time"
                record_dialogue_turn("agent", vm_msg)
                record_dialogue_turn("customer", f"[Voicemail/Machine: {ev.transcript}]")
                try:
                    session.say(vm_msg, allow_interruptions=False)
                except Exception as vm_err:
                    logger.warning(f"Error speaking voicemail message: {vm_err}")
                trigger_hangup(wait_for_speech=True, delay_seconds=0.8)
                return'''

    code = code.replace(old_vm, new_vm)
    code = code.replace(old_vm.replace("\n", "\r\n"), new_vm.replace("\n", "\r\n"))

    # Update first human voice opening greeting in on_user_input
    old_human_intro = '''                logger.info(f"👤 [HUMAN VOICE CONFIRMED] Caller said: '{ev.transcript}'. Speaking opening Sai Garden greeting...")
                intro_text = "नमस्कार! मैं गायत्री बोल रही हूँ साई गार्डन, डोंबिवली ईस्ट से। हमारे यहाँ one aur two BHK luxury flats thirty-six lakh se shuru ho rahe hain. Kya aap apne liye one BHK dekh rahe hain ya two BHK?"
                record_dialogue_turn("agent", intro_text)
                try:
                    session.say(intro_text, allow_interruptions=True)
                except Exception as intro_err:
                    logger.warning(f"Error speaking intro on human voice: {intro_err}")
                return'''

    new_human_intro = '''                opening_greeting = "Hello! This is Gayatri from Sai Garden, Dombivli East, right opposite Xperia Mall. Would you prefer a 1 BHK or a 2 BHK?"
                logger.info(f"👤 [HUMAN VOICE CONFIRMED] Caller spoke. Delivering opening greeting: '{opening_greeting}'")
                record_dialogue_turn("agent", opening_greeting)
                try:
                    session.say(opening_greeting, allow_interruptions=True)
                except Exception as intro_err:
                    logger.warning(f"Error speaking opening greeting on human voice: {intro_err}")
                return'''

    code = code.replace(old_human_intro, new_human_intro)
    code = code.replace(old_human_intro.replace("\n", "\r\n"), new_human_intro.replace("\n", "\r\n"))

    # Set agent.room_name on instantiation
    old_agent_inst = '''    agent = PriyaRealEstateAgent(
        customer_name=spoken_customer_name,
        customer_phone=customer_phone,
        hangup_fnc=trigger_hangup,
        on_speech_captured=_record_agent_speech
    )'''
    new_agent_inst = '''    agent = PriyaRealEstateAgent(
        customer_name=spoken_customer_name,
        customer_phone=customer_phone,
        hangup_fnc=trigger_hangup,
        on_speech_captured=_record_agent_speech
    )
    agent.room_name = ctx.room.name'''
    code = code.replace(old_agent_inst, new_agent_inst)
    code = code.replace(old_agent_inst.replace("\n", "\r\n"), new_agent_inst.replace("\n", "\r\n"))

    # --------------------------------------------------------------------------
    # 10. Replace the 8s delay in _initial_human_listener with IMMEDIATE GREETING!
    # --------------------------------------------------------------------------
    old_listener = '''        # Dynamic Human Voice Detection: Gayatri listens first for caller voice ('Hello', etc.)
        # If the caller stays silent for 3.5 seconds after pickup, gently prompt with Hello
        async def _initial_human_listener():
            nonlocal intro_started, intro_finished, _hangup_scheduled
            logger.info("🎧 [HUMAN VOICE DETECTION ACTIVE] Waiting for caller to speak first (e.g. 'Hello')...")
            await asyncio.sleep(8.0)
            if not intro_started and not _hangup_scheduled:
                logger.info("⏳ [INITIAL SILENCE] Caller answered but stayed silent for 3.5s. Prompting with gentle Hello...")
                prompt_hello = "Hello? नमस्कार!"
                record_dialogue_turn("agent", prompt_hello)
                try:
                    session.say(prompt_hello, allow_interruptions=True)
                except Exception as e:
                    logger.warning(f"Error speaking initial gentle prompt: {e}")

        asyncio.create_task(_initial_human_listener())'''

    new_listener = '''        # Opening Fixed Greeting: Speak immediately once carrier RTP bridge settles!
        if not intro_started and not _hangup_scheduled:
            intro_started = True
            intro_finished = True
            opening_greeting = "Hello! This is Gayatri from Sai Garden, Dombivli East, right opposite Xperia Mall. Would you prefer a 1 BHK or a 2 BHK?"
            logger.info(f"🎙️ [IMMEDIATE OPENING GREETING] Speaking fixed opening greeting: '{opening_greeting}'")
            record_dialogue_turn("agent", opening_greeting)
            try:
                session.say(opening_greeting, allow_interruptions=True)
            except Exception as e:
                logger.warning(f"Error speaking immediate opening greeting: {e}")'''

    code = code.replace(old_listener, new_listener)
    code = code.replace(old_listener.replace("\n", "\r\n"), new_listener.replace("\n", "\r\n"))
    print("Replaced silent delay with Immediate Opening Greeting!")

    # --------------------------------------------------------------------------
    # 11. Update Silence Nudge (5.0s) & Max Call Duration Watchdog (5 minutes)
    # --------------------------------------------------------------------------
    old_silence_prompt = '''            # 2. If caller remains silent for 12.0 seconds (and agent hasn't prompted yet): Ask gently ONCE
            if (not has_prompted_silence) and (silence_duration >= 12.0):
                has_prompted_silence = True
                last_prompt_time = now
                logger.info(f"⏳ [SILENCE PROMPT] 12s silence elapsed. Prompting gently in language '{current_lang}'...")
                if current_lang == "mr":
                    prompt_text = "हॅलो? आपण काही विचारत आहात का?"
                elif current_lang == "en":
                    prompt_text = "Hello? Do you have any questions regarding Sai Garden?"
                else:
                    prompt_text = "Ji, kya aapka Sai Garden ke baare mein koi sawaal hai?"
                try:
                    t_user_stop = 0.0
                    record_dialogue_turn("agent", prompt_text)
                    session.say(prompt_text, allow_interruptions=True)
                except Exception as e:
                    logger.warning(f"Error speaking silence prompt: {e}")'''

    new_silence_prompt = '''            # 2. Silence Nudge: after 5 silent seconds, gently prompt: "Hey, are you still on the call?"
            if (not has_prompted_silence) and (silence_duration >= 5.0):
                has_prompted_silence = True
                last_prompt_time = now
                logger.info(f"⏳ [SILENCE NUDGE] 5s silence elapsed. Prompting gently: 'Hey, are you still on the call?'")
                prompt_text = "Hey, are you still on the call?"
                try:
                    t_user_stop = 0.0
                    record_dialogue_turn("agent", prompt_text)
                    session.say(prompt_text, allow_interruptions=True)
                except Exception as e:
                    logger.warning(f"Error speaking silence prompt: {e}")'''

    code = code.replace(old_silence_prompt, new_silence_prompt)
    code = code.replace(old_silence_prompt.replace("\n", "\r\n"), new_silence_prompt.replace("\n", "\r\n"))

    # Add Max Call Duration (5 minutes = 300 seconds)
    old_watchdog_end = "watchdog_task = asyncio.create_task(_silence_watchdog())"
    new_watchdog_end = '''watchdog_task = asyncio.create_task(_silence_watchdog())

    # Max Call Duration Watchdog: 5-minute strict limit
    async def _max_call_duration_watchdog():
        await asyncio.sleep(295.0)
        if not _hangup_scheduled:
            logger.info("⏱️ [MAX CALL DURATION] 5 minutes elapsed. Concluding call gracefully...")
            conclusion = "Thank you so much for your time today. Have a wonderful day, goodbye!"
            try:
                record_dialogue_turn("agent", conclusion)
                speech = session.say(conclusion, allow_interruptions=False)
                if speech:
                    await speech.wait_for_playout()
            except Exception:
                pass
            trigger_hangup(wait_for_speech=False, delay_seconds=0.5)

    max_duration_task = asyncio.create_task(_max_call_duration_watchdog())'''

    code = code.replace(old_watchdog_end, new_watchdog_end)
    code = code.replace(old_watchdog_end.replace("\n", "\r\n"), new_watchdog_end.replace("\n", "\r\n"))
    print("Updated Silence Nudge (5s) and Max Call Duration (5m) Watchdogs!")

    with open(agent_path, "w", encoding="utf-8") as f:
        f.write(code)

    print(f"Successfully saved updated {agent_path} (new length: {len(code)})!")

if __name__ == "__main__":
    main()
