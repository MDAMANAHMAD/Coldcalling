import asyncio
import os
import time
import logging
from dotenv import load_dotenv
from livekit.plugins import deepgram, elevenlabs
from livekit.agents.utils import http_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnose_handshakes")

load_dotenv()

async def main():
    async with http_context.open():
        # 1. Test Deepgram Nova-2 Connection Speed
        print("\n" + "=" * 60)
        print("TESTING DEEPGRAM STT WEB SOCKET HANDSHAKE SPEED...")
        print("=" * 60)
        stt = deepgram.STT(
            language="hi",
            model="nova-2",
            endpointing_ms=120,
            smart_format=True,
            api_key=os.getenv("DEEPGRAM_API_KEY")
        )
        
        t0 = time.perf_counter()
        try:
            # Try to establish stream connection
            async with stt.stream() as stream:
                t_dg = (time.perf_counter() - t0) * 1000
                print(f"  [DEEPGRAM OK] Handshake and WebSocket established in {t_dg:.1f}ms")
        except Exception as e:
            t_dg = (time.perf_counter() - t0) * 1000
            print(f"  [DEEPGRAM FAILED] in {t_dg:.1f}ms: {e}")
            
        # 2. Test ElevenLabs Connection Speed
        print("\n" + "=" * 60)
        print("TESTING ELEVENLABS TTS STREAM CONNECTION SPEED...")
        print("=" * 60)
        tts = elevenlabs.TTS(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id="EXAVITQu4vr4xnSDxMaL",
            model="eleven_turbo_v2_5",
            streaming_latency=3
        )
        
        t0 = time.perf_counter()
        try:
            # Try to request a tiny audio stream
            async for chunk in tts.synthesize("test"):
                t_el = (time.perf_counter() - t0) * 1000
                print(f"  [ELEVENLABS OK] First audio chunk received in {t_el:.1f}ms")
                break
        except Exception as e:
            t_el = (time.perf_counter() - t0) * 1000
            print(f"  [ELEVENLABS FAILED] in {t_el:.1f}ms: {e}")
            
        print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
