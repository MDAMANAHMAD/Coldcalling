import re

with open("scratch/agent_session.py", "r", encoding="utf-8") as f:
    content = f.read()

# Let's search for allow_interruptions references
matches = [line for line in content.split("\n") if "allow_interruptions" in line]
print("=== allow_interruptions matches ===")
for m in matches:
    print(m)

# Let's search for VAD / user speaking event listeners
print("\n=== Event/VAD handlers ===")
for line in content.split("\n"):
    if "USER_STARTED_SPEAKING" in line or "on_user_speaking" in line or "interrupt" in line:
        print(line)
