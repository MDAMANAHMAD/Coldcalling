import inspect
from livekit.plugins import deepgram

print("deepgram.STT __init__ signature:")
print(inspect.signature(deepgram.STT.__init__))

print("\ndeepgram.STT source file:")
print(inspect.getfile(deepgram.STT))
