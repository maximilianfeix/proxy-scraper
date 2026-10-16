"""The demo's lab: check targets and six proxies on localhost, each with one known behaviour.

    python docs/demo/lab_server.py        # runs until Ctrl+C, writes docs/demo/.lab.json

Nothing here touches the internet. The "proxies" are small programs from tests/lab.py, their exit IPs are
documentation addresses (203.0.113.x). This shows how the tool reports what it finds – it measures nothing
about real public proxies.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.lab import INJECTED, Lab  # noqa: E402

STATE = Path(__file__).with_name(".lab.json")


def row(proxy: str, latency: int, country: str) -> dict:
    return {"url": f"http://{proxy}", "proxy": proxy, "ptype": "http", "latency": latency, "exit_ip": "",
            "https": True, "anonymity": "elite", "country": country, "streak": 30, "uptime_7d": 95}


async def main() -> None:
    async with Lab() as lab:
        gone = "127.0.0.1:8081"  # nothing listens here: listed an hour ago, gone since
        rotating = await lab.proxy("203.0.113.12", second_exit_ip="203.0.113.77", port=8082)
        rewriting = await lab.proxy("203.0.113.13", rewrite=lambda body: INJECTED, port=8083)
        good = await lab.proxy("203.0.113.14", port=8084)
        no_https = await lab.proxy("203.0.113.15", no_connect=True, port=8085)
        also_good = await lab.proxy("203.0.113.16", port=8086)
        listed = [row(gone, 80, "US"), row(rotating, 120, "NL"), row(rewriting, 150, "DE"), row(good, 210, "DE"),
                  row(no_https, 240, "FR"), row(also_good, 300, "US")]
        published = datetime.now(timezone.utc) - timedelta(minutes=41)
        STATE.write_text(json.dumps({
            "judge_port": lab.judge_port, "confirm_port": lab.confirm_port, "tls_port": lab.tls_port,
            "rows": listed, "stats": {"updated": published.isoformat(timespec="seconds"), "run_hours": 1},
        }))
        print(f"lab is up – {len(listed)} listed proxies on 127.0.0.1:8081–8086. Ctrl+C stops it.", flush=True)
        stop = asyncio.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):  # also `kill`: the state file goes away with the lab
            asyncio.get_running_loop().add_signal_handler(signum, stop.set)
        try:
            await stop.wait()
        finally:
            if STATE.exists():
                STATE.unlink()


if __name__ == "__main__":
    asyncio.run(main())
