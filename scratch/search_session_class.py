with open("scratch/agent_session.py", "r", encoding="utf-8") as f:
    content = f.read()

# Print the class definition lines and base classes
import re
lines = content.split("\n")
print("=== Class & inheritance definitions ===")
for i, line in enumerate(lines):
    if "class " in line or "def " in line and not line.startswith("    "):
        print(f"Line {i+1}: {line.strip()}")
