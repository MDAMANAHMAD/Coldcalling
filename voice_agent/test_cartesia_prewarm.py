import os
import time
import asyncio
from dotenv import load_dotenv
from livekit.plugins import cartesia

load_dotenv()

async def main():
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    if not cartesia_key:
        print("Error: CARTESIA_API_KEY not found in environment.")
        return

    print("Instantiating Cartesia TTS...")
    tts = cartesia.TTS(
        api_key=cartesia_key,
        voice="72656902-fb4b-4c31-af52-c3b68e2cae26",  # Esha Hindi voice
        language="hi",
        sample_rate=24000
    )

    # Test 1: Run prewarm and dummy synthesis
    print("\nRunning prewarm() and first dummy synthesis (to warm up connection)...")
    t0 = time.perf_counter()
    tts.prewarm()
    try:
        stream = tts.synthesize(text="hi")
        async for chunk in stream:
            print("First chunk received from prewarm stream!")
            break
    except Exception as e:
        print("Prewarm synthesis error:", e)
    t1 = time.perf_counter()
    print(f"Prewarm + first dummy synthesis took: {t1 - t0:.3f} seconds")

    # Test 2: Run subsequent synthesis (this represents the live call start)
    print("\nRunning second synthesis (should be instant)...")
    t2 = time.perf_counter()
    try:
        stream = tts.synthesize(text="namaste")
        async for chunk in stream:
            print("First chunk received from live stream!")
            break
    except Exception as e:
        print("Second synthesis error:", e)
    t3 = time.perf_counter()
    print(f"Second synthesis latency: {t3 - t2:.3f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
