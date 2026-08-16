import inspect
from livekit.agents.voice import agent_session

# Let's inspect the EventTypes or events defined in agent_session
try:
    for name, obj in inspect.getmembers(agent_session):
        if "Event" in name:
            print(f"Name: {name} | Type: {type(obj)}")
            if inspect.isclass(obj):
                print(f"  Class fields/members:")
                for m_name, m_val in inspect.getmembers(obj):
                    if not m_name.startswith("__"):
                        print(f"    - {m_name}: {m_val}")
except Exception as e:
    print("Error:", e)
