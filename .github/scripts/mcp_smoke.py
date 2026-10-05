"""Speaks MCP over stdio to a command (e.g. docker run -i …) and checks that it lists proxy-scraper's tools.

    python .github/scripts/mcp_smoke.py docker run -i --rm proxy-scraper:test --mcp
"""

import json
import subprocess
import sys

EXPECTED = {"get_proxies", "check_proxies", "fetch_url"}
MESSAGES = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def main(command):
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    for message in MESSAGES:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
    tools = None
    for line in proc.stdout:  # answers come one JSON message per line
        answer = json.loads(line)
        if answer.get("id") == 1:
            print("server:", answer["result"]["serverInfo"])
        if answer.get("id") == 2:
            tools = {tool["name"] for tool in answer["result"]["tools"]}
            break
    proc.stdin.close()
    proc.wait(timeout=30)
    print("tools:", sorted(tools or ()))
    if tools is None or EXPECTED - tools:
        sys.exit(f"expected the tools {sorted(EXPECTED)}")


if __name__ == "__main__":
    main(sys.argv[1:])
