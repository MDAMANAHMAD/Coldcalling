import os
import time
import asyncio
from dotenv import load_dotenv
from livekit.plugins import silero, cartesia, openai
import urllib.request
import json

load_dotenv()

async def test_llm():
    print("\n--- 1. LLM Latency Benchmark (Groq) ---")
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("Error: GROQ_API_KEY not found in .env")
        return
        
    llm = openai.LLM(
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-20b",
        api_key=groq_key,
        temperature=0.0
    )
    
    from livekit.agents import llm as agents_llm
    chat_ctx = agents_llm.ChatContext()
    chat_ctx.add_message(role="user", content="Namaste, main Aman baat kar raha hoon.")
    
    t0 = time.perf_counter()
    stream = llm.chat(chat_ctx=chat_ctx)
    first_token_time = None
    
    try:
        async for chunk in stream:
            if not first_token_time:
                first_token_time = (time.perf_counter() - t0) * 1000
                print(f"Time to First Token (TTFT): {first_token_time:.1f} ms")
        total_time = (time.perf_counter() - t0) * 1000
        print(f"Total LLM generation time: {total_time:.1f} ms")
    except Exception as e:
        print(f"LLM Error: {e}")

async def test_tts():
    print("\n--- 2. TTS Latency Benchmark (Cartesia) ---")
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    if not cartesia_key:
        print("Error: CARTESIA_API_KEY not found in .env")
        return
        
    payload = {
        "model_id": "sonic-3.5",
        "voice": {
            "mode": "id",
            "id": "72656902-fb4b-4c31-af52-c3b68e2cae26"
        },
        "transcript": "Namaste.",
        "output_format": {
            "container": "raw",
            "encoding": "pcm_f32le",
            "sample_rate": 24000
        },
        "language_code": "hi"
    }
    
    t0 = time.perf_counter()
    req = urllib.request.Request(
        "https://api.cartesia.ai/tts/bytes",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-API-Key": cartesia_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        response = urllib.request.urlopen(req, timeout=8.0)
        data = response.read(1024)
        ttfb = (time.perf_counter() - t0) * 1000
        print(f"Cartesia Time to First Byte (TTFB): {ttfb:.1f} ms")
        print(f"Received {len(data)} bytes of audio data.")
    except Exception as e:
        print(f"TTS Error: {e}")

def test_vad():
    print("\n--- 3. VAD ONNX Latency Benchmark (Silero) ---")
    try:
        t0 = time.perf_counter()
        vad = silero.VAD.load(sample_rate=8000)
        load_time = (time.perf_counter() - t0) * 1000
        print(f"Silero VAD Load Time: {load_time:.1f} ms")
        
        # Simulate 100 VAD frames (each frame is 32ms of audio, which is 256 samples at 8kHz)
        import numpy as np
        from livekit import rtc
        
        # 32ms audio frame at 8000Hz PCM 16-bit is 256 samples
        raw_data = np.zeros(256, dtype=np.int16)
        audio_frame = rtc.AudioFrame(
            data=raw_data.tobytes(),
            sample_rate=8000,
            num_channels=1,
            samples_per_channel=256
        )
        
        # Benchmark 100 VAD inferences
        t_start = time.perf_counter()
        for _ in range(100):
            vad.process_frame(audio_frame)
        t_end = time.perf_counter()
        
        avg_infer = ((t_end - t_start) / 100) * 1000
        print(f"Average VAD Inference Time per 32ms frame: {avg_infer:.3f} ms")
        
        if avg_infer > 10.0:
            print(f"⚠️ WARNING: VAD inference is extremely slow ({avg_infer:.1f}ms). Normal speed is <2ms. This indicates severe CPU throttling or starvation!")
        else:
            print(f"✅ VAD inference is healthy ({avg_infer:.3f}ms per frame).")
    except Exception as e:
        print(f"VAD Error: {e}")

async def main():
    await test_llm()
    await test_tts()
    test_vad()

if __name__ == "__main__":
    asyncio.run(main())
