from app.services.process_message import process_message
from app.services.agent import run_agent, AGENT_SYSTEM_PROMPT, TOOLS

print("OK - process_message loaded")
print("OK - run_agent loaded")
tool_names = [t["function"]["name"] for t in TOOLS]
print(f"Tools ({len(tool_names)}): {tool_names}")
print("ALL OK")
