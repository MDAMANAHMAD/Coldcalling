with open("scratch/agent_session.py", "r", encoding="utf-8") as f:
    content = f.read()

# Let's find all import statements
import re
imports = re.findall(r"(?:from\s+[a-zA-Z0-9_\.]+\s+import\s+[a-zA-Z0-9_,\s\(\)]+|import\s+[a-zA-Z0-9_\.\s,]+)", content)
print("=== Imports in agent_session.py ===")
for imp in imports:
    if "TurnHandlingOptions" in imp or "turn_handling" in imp or "livekit.agents.voice" in imp:
        print(imp)
