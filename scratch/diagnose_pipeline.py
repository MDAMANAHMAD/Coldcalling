import os
import time
import asyncio
from dotenv import load_dotenv
from livekit.plugins import silero, cartesia, openai
import urllib.request
import json
import numpy as np

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

async def test_vad():
    print("\n--- 3. VAD ONNX Latency Benchmark (Silero) ---")
    try:
        t0 = time.perf_counter()
        vad = silero.VAD.load(sample_rate=8000)
        load_time = (time.perf_counter() - t0) * 1000
        print(f"Silero VAD Load Time: {load_time:.1f} ms")
        
        if hasattr(vad, "_onnx_session") and vad._onnx_session:
            session = vad._onnx_session
            
            inputs = session.get_inputs()
            input_feed = {}
            for inp in inputs:
                shape = []
                for idx, s in enumerate(inp.shape):
                    if isinstance(s, int) and s > 0:
                        shape.append(s)
                    elif idx == 0:
                        # Batch size is always 1
                        shape.append(1)
                    elif inp.name == "input" and idx == 1:
                        # Samples is 256 for 32ms at 8kHz
                        shape.append(256)
                    else:
                        shape.append(1)
                
                # Determine data type
                if "int64" in inp.type:
                    val = np.zeros(shape, dtype=np.int64)
                    if inp.name in ("sr", "sample_rate"):
                        val.fill(8000)
                else:
                    val = np.zeros(shape, dtype=np.float32)
                
                input_feed[inp.name] = val
                print(f"ONNX Input - Name: '{inp.name}', Shape: {shape}, Type: {inp.type}")
            
            # Warm up
            for _ in range(5):
                session.run(None, input_feed)
                
            # Benchmark 100 runs
            t_start = time.perf_counter()
            for _ in range(100):
                session.run(None, input_feed)
            t_end = time.perf_counter()
            
            avg_infer = ((t_end - t_start) / 100) * 1000
            print(f"ONNX average VAD inference latency per 32ms frame: {avg_infer:.3f} ms")
            
            if avg_infer > 5.0:
                print(f"\n⚠️ WARNING: ONNX inference is extremely slow ({avg_infer:.1f}ms).")
                print("Normal speed on a healthy CPU is <1.0 ms.")
                print("This indicates your VPS CPU is severely throttled or lacks CPU credits/burst capacity!")
            else:
                print(f"\n✅ ONNX inference is healthy ({avg_infer:.3f}ms per frame).")
        else:
            print("Could not access _onnx_session object.")
            
    except Exception as e:
        print(f"VAD Error: {e}")

async def main():
    await test_llm()
    await test_tts()
    await test_vad()

if __name__ == "__main__":
    asyncio.run(main())
