import inspect
from livekit.plugins import cartesia

try:
    tts = cartesia.TTS(api_key="dummy_key_to_inspect")
    pool = tts._pool
    print("=== pool.prewarm source ===")
    print(inspect.getsource(pool.prewarm))
except Exception as e:
    print("pool prewarm error:", e)
