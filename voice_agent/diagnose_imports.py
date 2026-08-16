import sys
import os
import time

print("=" * 50)
print("🔍 SYSTEM DIAGNOSTIC: LIBRARY IMPORT LATENCY BENCHMARK")
print("=" * 50)

# Check Memory Info
try:
    with open('/proc/meminfo', 'r') as f:
        print("--- Memory Stats ---")
        for _ in range(4):
            print(f.readline().strip())
except Exception:
    pass

print("\n--- Running Import Benchmarks ---")

t_start = time.time()

print("1. Importing torch...")
t0 = time.time()
try:
    import torch
    print(f"   ✓ torch loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ torch load error: {e}")

print("2. Importing openai...")
t0 = time.time()
try:
    import openai
    print(f"   ✓ openai loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ openai load error: {e}")

print("3. Importing livekit.rtc...")
t0 = time.time()
try:
    from livekit import rtc
    print(f"   ✓ livekit.rtc loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ livekit.rtc load error: {e}")

print("4. Importing deepgram plugin...")
t0 = time.time()
try:
    from livekit.plugins import deepgram
    print(f"   ✓ deepgram plugin loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ deepgram plugin load error: {e}")

print("5. Importing elevenlabs plugin...")
t0 = time.time()
try:
    from livekit.plugins import elevenlabs
    print(f"   ✓ elevenlabs plugin loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ elevenlabs plugin load error: {e}")

print("6. Importing cartesia plugin...")
t0 = time.time()
try:
    from livekit.plugins import cartesia
    print(f"   ✓ cartesia plugin loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ cartesia plugin load error: {e}")

print("7. Importing google plugin...")
t0 = time.time()
try:
    from livekit.plugins import google
    print(f"   ✓ google plugin loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ google plugin load error: {e}")

print("8. Importing silero VAD plugin...")
t0 = time.time()
try:
    from livekit.plugins import silero
    print(f"   ✓ silero plugin loaded in {time.time()-t0:.3f}s")
except Exception as e:
    print(f"   ❌ silero plugin load error: {e}")

print("=" * 50)
print(f"Total benchmark time: {time.time()-t_start:.3f}s")
print("=" * 50)
