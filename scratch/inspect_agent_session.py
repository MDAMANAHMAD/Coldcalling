import inspect
from livekit.agents import AgentSession

try:
    print("AgentSession source file:", inspect.getfile(AgentSession))
    source = inspect.getsource(AgentSession)
    with open("scratch/agent_session.py", "w", encoding="utf-8") as f:
        f.write(source)
    print("Saved AgentSession source to scratch/agent_session.py")
except Exception as e:
    print("Error:", e)
