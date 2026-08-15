with open("scratch/agent_session.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for line in lines:
    if "TurnHandlingOptions" in line or "import" in line and ("voice" in line or "turn" in line):
        print(line.strip())
