import sys
from livekit.agents import AgentSession
from livekit.agents.voice.agent_activity import AgentActivity
import inspect

def main():
    print("=" * 60)
    print("AgentSession.start SOURCE:")
    print("=" * 60)
    try:
        print(inspect.getsource(AgentSession.start))
    except Exception as e:
        print("Error:", e)
        
    print("\n" + "=" * 60)
    print("AgentActivity.start SOURCE:")
    print("=" * 60)
    try:
        print(inspect.getsource(AgentActivity.start))
    except Exception as e:
        print("Error:", e)
        
    print("\n" + "=" * 60)
    print("AgentActivity._start_session SOURCE:")
    print("=" * 60)
    try:
        print(inspect.getsource(AgentActivity._start_session))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
