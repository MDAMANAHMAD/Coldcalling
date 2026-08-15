import inspect
from livekit.plugins import cartesia

print("cartesia.TTS signature:")
print(inspect.signature(cartesia.TTS.__init__))

print("\ncartesia.TTS methods:")
for name, obj in inspect.getmembers(cartesia.TTS):
    if not name.startswith("__") and (inspect.isfunction(obj) or inspect.ismethod(obj)):
        print(f" - {name}{inspect.signature(obj)}")
