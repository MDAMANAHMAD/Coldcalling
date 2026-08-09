"""
LiveKit Outbound SIP Dialer (Vobiz Telecom Bridge)
===================================================
Triggers outbound telephone calls via LiveKit SIP participant creation,
bridges the dialed party with the Gemini Live AI voice agent, and injects
customer metadata.

Usage:
  # Single lead call:
  python outbound_dialer.py --phone +918693081506 --name "Aman" --company "Aman Corp"

  # Batch CSV dispatch:
  python outbound_dialer.py --csv leads.csv
"""

import os
import csv
import json
import uuid
import re
import argparse
import asyncio
import logging
from dotenv import load_dotenv

from livekit import api
from livekit.protocol.sip import CreateSIPParticipantRequest

# Load environment variables
load_dotenv()

# Logger setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("outbound_dialer")


def format_e164(phone: str, default_country_code: str = "+91") -> str:
    """Sanitizes and converts raw phone input into strict E.164 standard."""
    clean = re.sub(r"\D", "", phone)
    if phone.startswith("+"):
        return f"+{clean}"
    if len(clean) == 10:
        return f"{default_country_code}{clean}"
    if len(clean) > 10 and (clean.startswith("91") or clean.startswith("1")):
        return f"+{clean}"
    return f"+{clean}"


async def make_outbound_call(
    phone_number: str,
    customer_name: str,
    company: str = "",
    wait_until_answered: bool = False
) -> dict:
    """
    Creates a dedicated LiveKit room and dispatches a SIP participant
    through the Vobiz Outbound SIP Trunk.
    """
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    sip_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")

    if not all([livekit_url, api_key, api_secret, sip_trunk_id]):
        raise ValueError("Missing LiveKit or SIP Trunk environment variables in .env")

    # Format phone number to E.164
    e164_phone = format_e164(phone_number)
    
    # Generate unique room identifier
    slug = re.sub(r"[^a-zA-Z0-9]", "", customer_name.lower()) or "lead"
    room_name = f"call-{slug}-{uuid.uuid4().hex[:8]}"

    # Prepare customer metadata payload for the AI agent
    room_metadata = json.dumps({
        "customer_name": customer_name,
        "company": company,
        "phone": e164_phone,
        "initiated_at": str(asyncio.get_event_loop().time())
    })

    # Initialize LiveKit Server API client
    lk_api = api.LiveKitAPI(
        url=livekit_url,
        api_key=api_key,
        api_secret=api_secret
    )

    logger.info("=" * 60)
    logger.info(f"📞 [INITIATING OUTBOUND SIP CALL via VOBIZ]")
    logger.info(f"🎯 Target Phone     : {e164_phone}")
    logger.info(f"👤 Customer Name    : {customer_name}")
    logger.info(f"🏢 Company          : {company or 'N/A'}")
    logger.info(f"🚪 LiveKit Room     : {room_name}")
    logger.info(f"📡 SIP Trunk ID     : {sip_trunk_id}")
    logger.info("=" * 60)

    try:
        # 1. Create Room with customer metadata so agent worker receives it upon connect
        await lk_api.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                metadata=room_metadata,
                empty_timeout=300, # Clean up room 5 minutes after participants leave
            )
        )

        # 2. Dispatch the SIP Participant Request to Vobiz Outbound Trunk
        sip_request = CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=e164_phone,
            room_name=room_name,
            participant_identity=f"sip-{e164_phone.replace('+', '')}",
            participant_name=customer_name,
            wait_until_answered=wait_until_answered
        )

        sip_participant = await lk_api.sip.create_sip_participant(sip_request)
        
        participant_id = getattr(sip_participant, 'participant_id', getattr(sip_participant, 'sid', 'sip-participant'))
        participant_identity = getattr(sip_participant, 'participant_identity', getattr(sip_participant, 'identity', f"sip-{e164_phone}"))

        logger.info(f"✅ SIP Call Dispatched Successfully!")
        logger.info(f"🆔 Participant ID : {participant_id}")
        logger.info(f"🏷️ Participant Identity : {participant_identity}")

        return {
            "status": "success",
            "room_name": room_name,
            "participant_id": str(participant_id),
            "phone": e164_phone,
            "customer_name": customer_name
        }

    except Exception as exc:
        logger.error(f"❌ Failed to dispatch outbound SIP call: {exc}")
        return {
            "status": "error",
            "error": str(exc),
            "phone": e164_phone,
            "customer_name": customer_name
        }
    finally:
        await lk_api.aclose()


async def process_batch_csv(csv_path: str):
    """Parses a CSV file and dials leads sequentially."""
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        return

    logger.info(f"📂 Processing CSV batch campaign: {csv_path}")
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    logger.info(f"📊 Found {len(leads)} leads in file.")
    for idx, lead in enumerate(leads, 1):
        name = lead.get("Name") or lead.get("name") or "Lead"
        phone = lead.get("Phone") or lead.get("phone")
        company = lead.get("Company") or lead.get("company") or ""

        if not phone:
            logger.warning(f"⚠️ Skipping row {idx}: Missing phone number.")
            continue

        logger.info(f"\n--- Dialing Lead {idx}/{len(leads)}: {name} ({phone}) ---")
        result = await make_outbound_call(phone, name, company, wait_until_answered=False)
        logger.info(f"Result: {result['status']}")

        # Gentle delay between campaign dispatches to respect rate limits
        await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="LiveKit Vobiz Outbound SIP Voice AI Dialer")
    parser.add_argument("--phone", type=str, help="Target phone number (e.g. +918693081506)")
    parser.add_argument("--name", type=str, default="Valued Contact", help="Customer/Lead Name")
    parser.add_argument("--company", type=str, default="", help="Company Name")
    parser.add_argument("--csv", type=str, help="Path to batch CSV file")

    args = parser.parse_args()

    if args.csv:
        asyncio.run(process_batch_csv(args.csv))
    elif args.phone:
        asyncio.run(make_outbound_call(args.phone, args.name, args.company))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
