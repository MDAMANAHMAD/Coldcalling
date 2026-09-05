import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv("voice_agent/.env")

from livekit import api
from livekit.protocol import sip

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

async def setup_inbound():
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    phone_number = "+918071580297"

    print("=" * 60)
    print("📥 CREATING LIVEKIT INBOUND SIP TRUNK & DISPATCH RULE")
    print(f"Number: {phone_number}")
    print("=" * 60)

    lk = api.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
    try:
        # 1. Create Inbound Trunk
        in_trunk = sip.SIPInboundTrunkInfo(
            name="vobiz-inbound",
            numbers=[phone_number]
        )
        trunk_res = await lk.sip.create_inbound_trunk(
            sip.CreateSIPInboundTrunkRequest(trunk=in_trunk)
        )
        inbound_trunk_id = trunk_res.sip_trunk_id
        print(f"✅ Inbound Trunk Created! ID: {inbound_trunk_id}")

        # 2. Create Dispatch Rule
        rule_info = sip.SIPDispatchRuleInfo(
            name="inbound-to-agent",
            trunk_ids=[inbound_trunk_id],
            rule=sip.SIPDispatchRule(
                dispatch_rule_individual=sip.SIPDispatchRuleIndividual(
                    room_prefix="call-inbound-"
                )
            )
        )
        dispatch_res = await lk.sip.create_dispatch_rule(
            sip.CreateSIPDispatchRuleRequest(
                name="inbound-to-agent",
                trunk_ids=[inbound_trunk_id],
                rule=sip.SIPDispatchRule(
                    dispatch_rule_individual=sip.SIPDispatchRuleIndividual(
                        room_prefix="call-inbound-"
                    )
                )
            )
        )
        print(f"✅ SIP Dispatch Rule Created! ID: {dispatch_res.sip_dispatch_rule_id}")

    except Exception as e:
        print(f"❌ Inbound setup failed: {e}")
    finally:
        await lk.aclose()

if __name__ == "__main__":
    asyncio.run(setup_inbound())
