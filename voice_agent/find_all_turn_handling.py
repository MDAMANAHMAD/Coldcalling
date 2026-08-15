with open("scratch/agent_session.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "TurnHandlingOptions" in line:
            print(f"Line {i+1}: {line.strip()}")
