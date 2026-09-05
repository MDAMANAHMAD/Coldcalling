import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv("voice_agent/.env")

from livekit import api
from livekit.protocol import sip

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

async def update_trunk():
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    sip_trunk_id = "ST_TEGVYguUkfe9"

    username = "aman_sip"
    password = "Aman@12345"
    address = "93440e65.sip.vobiz.ai:5060"
    numbers = ["+918071580297"]

    print("=" * 60)
    print("🔄 UPDATING LIVEKIT OUTBOUND SIP TRUNK")
    print(f"Trunk ID     : {sip_trunk_id}")
    print(f"Address      : {address}")
    print(f"Auth Username: {username}")
    print(f"Numbers      : {numbers}")
    print("=" * 60)

    lk = api.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
    try:
        trunk_info = sip.SIPOutboundTrunkInfo(
            sip_trunk_id=sip_trunk_id,
            name="aman_sip",
            address=address,
            numbers=numbers,
            auth_username=username,
            auth_password=password,
            transport=sip.SIPTransport.SIP_TRANSPORT_AUTO
        )

        res = await lk.sip.update_outbound_trunk(sip_trunk_id, trunk_info)
        print("✅ Trunk updated successfully!")
        print("Response:", res)

    except Exception as e:
        print(f"❌ Failed to update trunk: {e}")
    finally:
        await lk.aclose()

if __name__ == "__main__":
    asyncio.run(update_trunk())
