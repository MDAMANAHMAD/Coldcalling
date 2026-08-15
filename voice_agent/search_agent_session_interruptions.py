import inspect
from livekit.agents.voice.agent_session import AgentSession

print("AgentSession __init__ signature:")
print(inspect.signature(AgentSession.__init__))

print("\nAgentSession methods:")
for name, obj in inspect.getmembers(AgentSession):
    if not name.startswith("__") and (inspect.isfunction(obj) or inspect.ismethod(obj)):
        print(f" - {name}{inspect.signature(obj)}")
