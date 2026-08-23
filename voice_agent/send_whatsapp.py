import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

# Twilio Credentials loaded from .env
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
API_KEY_SID = os.getenv("TWILIO_API_KEY_SID")
API_KEY_SECRET = os.getenv("TWILIO_API_KEY_SECRET")

FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_SENDER", "whatsapp:+14155238886")

def send_whatsapp(to_phone, body, media_url=None):
    """Sends a WhatsApp message via Twilio API"""
    clean_phone = to_phone.strip().replace(" ", "").replace("-", "")
    if not clean_phone.startswith("+"):
        if len(clean_phone) == 10:
            clean_phone = "+91" + clean_phone
        else:
            clean_phone = "+" + clean_phone
            
    url = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"
    
    data = {
        "From": FROM_NUMBER,
        "To": f"whatsapp:{clean_phone}",
        "Body": body
    }
    
    if media_url:
        data["MediaUrl"] = media_url

    try:
        r = requests.post(url, data=data, auth=(API_KEY_SID, API_KEY_SECRET), timeout=15)
        if r.status_code in [200, 201]:
            print(f"✅ Message sent successfully to {clean_phone}!")
            print(f"   Message SID: {r.json().get('sid')}")
            return True
        else:
            print(f"❌ Twilio Error (Status {r.status_code}): {r.text}")
            return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: venv/bin/python voice_agent/send_whatsapp.py <phone_number> <message_body> [pdf_url]")
        print("Example: venv/bin/python voice_agent/send_whatsapp.py +919876543210 'Namaste, here is your statement.' https://example.com/statement.pdf")
        sys.exit(1)

    target_phone = sys.argv[1]
    message_text = sys.argv[2]
    pdf_url = sys.argv[3] if len(sys.argv) > 3 else None

    send_whatsapp(target_phone, message_text, pdf_url)
