"""A fixture hourly list for the action job in tests.yml – only active with PROXY_SCRAPER_LIVE_FIXTURE=1.

The job puts this folder on PYTHONPATH, so every Python it starts (also the venv the composite action creates)
imports this file at startup. Once proxyscraper is installed, the download of proxies.json/stats.json is
swapped for the rows below; everything else – the install, the filters, the ranking, the outputs – is the real
code. Nothing connects to these addresses: the job runs the action without recheck. They are on 127.0.0.1,
which a real list may not name, so agent.listable lets them through here.

live-smoke.yml runs the same action against the real list on a schedule.
"""

import os

if os.environ.get("PROXY_SCRAPER_LIVE_FIXTURE") == "1":
    try:
        from proxyscraper import agent, api
    except ImportError:  # pip, before the action has installed proxyscraper
        pass
    else:
        import json
        from datetime import datetime, timedelta, timezone

        def _row(ptype, port, latency, https):
            proxy = f"127.0.0.1:{port}"
            return {"url": f"{ptype}://{proxy}", "proxy": proxy, "ptype": ptype, "latency": latency, "exit_ip": "",
                    "https": https, "anonymity": "elite", "country": "DE", "streak": 12, "uptime_7d": 90}

        _ROWS = [_row("socks5", 1080, 120, True), _row("http", 8080, 150, True), _row("http", 3128, 90, False),
                 _row("socks4", 4145, 80, False), _row("socks5", 1081, 300, True)]

        async def _fixture_fetch(url, timeout=0, headers=None):
            if url.endswith("/proxies.json"):
                return json.dumps(_ROWS).encode()
            updated = datetime.now(timezone.utc) - timedelta(minutes=10)
            return json.dumps({"updated": updated.isoformat(timespec="seconds"), "run_hours": 1}).encode()

        api._live_fetch = _fixture_fetch
        agent.listable = lambda proxy: True
