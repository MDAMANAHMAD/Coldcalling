from livekit.plugins.deepgram import stt
import inspect

print("DeepgramLanguages type/values:")
try:
    print(stt.DeepgramLanguages)
except Exception as e:
    print("Not found directly:", e)

# Let's inspect the keys and code inside stt.py where language is handled
with open(stt.__file__, "r", encoding="utf-8") as f:
    code = f.read()

print("\nSearching for language parameter handling in stt.py:")
for line in code.split("\n"):
    if "self._opts.language" in line or "language" in line and ("=" in line or "if" in line) and any(kw in line for kw in ["self", "opts", "config"]):
        print(line.strip())
