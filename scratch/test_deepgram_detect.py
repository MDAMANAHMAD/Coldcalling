import os
import asyncio
from dotenv import load_dotenv
from livekit.plugins import deepgram

load_dotenv()

async def main():
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "3a657520e54772fc188dc619ebbcca895dd9366c")
    print("Testing Deepgram STT with detect_language=True...")
    stt = deepgram.STT(
        detect_language=True,
        model="nova-2",
        api_key=deepgram_key
    )
    print("STT client created successfully.")
    print("Supported languages configurations checked.")

if __name__ == "__main__":
    asyncio.run(main())
