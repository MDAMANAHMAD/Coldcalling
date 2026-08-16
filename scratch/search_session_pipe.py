with open("scratch/agent_session.py", "r", encoding="utf-8") as f:
    content = f.read()

# Let's search for how the LLM response is consumed or piped to TTS
import re
lines = content.split("\n")
print("=== Piping logic in AgentSession ===")
for i, line in enumerate(lines):
    if "tts" in line or "llm" in line or "generate_reply" in line:
        if any(keyword in line for keyword in ["stream", "say", "synthesize", "chat"]):
            print(f"Line {i+1}: {line.strip()}")
