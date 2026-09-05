import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv("voice_agent/.env")

from livekit import api
from livekit.protocol.sip import CreateSIPParticipantRequest

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

async def test_dial():
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    sip_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
    target_phone = "+918693081506"

    print("=" * 60)
    print("📞 TESTING OUTBOUND SIP CALL WITH SYNCHRONOUS FEEDBACK")
    print(f"Trunk ID: {sip_trunk_id}")
    print(f"Target  : {target_phone}")
    print("=" * 60)

    lk = api.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
    room_name = "test-sip-probe"

    try:
        # Create temporary probe room
        try:
            await lk.room.create_room(api.CreateRoomRequest(name=room_name, empty_timeout=60))
        except Exception:
            pass

        print("Sending CreateSIPParticipantRequest (wait_until_answered=True)...")
        req = CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=target_phone,
            room_name=room_name,
            participant_identity=f"sip-probe",
            participant_name="Test Call",
            wait_until_answered=True
        )

        res = await lk.sip.create_sip_participant(req)
        print("✅ Call successfully placed and answered!")
        print("Response:", res)

    except Exception as e:
        print("\n❌ SIP CALL FAILED WITH ERROR:")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
    finally:
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except Exception:
            pass
        await lk.aclose()

if __name__ == "__main__":
    asyncio.run(test_dial())
