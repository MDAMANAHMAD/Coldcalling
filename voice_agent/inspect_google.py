import inspect
from livekit.plugins.google import LLM

try:
    print("=== PREWARM SOURCE ===")
    print(inspect.getsource(LLM.prewarm))
except Exception as e:
    print("Error getting prewarm source:", e)

try:
    print("=== _PREWARM_IMPL SOURCE ===")
    print(inspect.getsource(LLM._prewarm_impl))
except Exception as e:
    print("Error getting _prewarm_impl source:", e)
