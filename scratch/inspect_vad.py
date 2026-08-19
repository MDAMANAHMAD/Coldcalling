import os
from livekit.plugins import silero

try:
    vad = silero.VAD.load()
    print("=== VAD Object Attributes/Methods ===")
    print(dir(vad))
    
    stream = vad.stream()
    print("\n=== VADStream Object Attributes/Methods ===")
    print(dir(stream))
except Exception as e:
    print(f"Error: {e}")
