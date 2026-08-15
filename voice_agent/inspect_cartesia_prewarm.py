import inspect
from livekit.plugins import cartesia

try:
    print("=== prewarm code ===")
    print(inspect.getsource(cartesia.TTS.prewarm))
except Exception as e:
    print("prewarm error:", e)

try:
    print("\n=== _ensure_session code ===")
    print(inspect.getsource(cartesia.TTS._ensure_session))
except Exception as e:
    print("_ensure_session error:", e)
