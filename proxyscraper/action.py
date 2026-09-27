"""The GitHub Action (action.yml): working proxies from the hourly list for the next steps of a workflow.

Inputs come in as PS_* environment variables, results go to $GITHUB_OUTPUT:
  proxy   the fastest one, ready to use (socks5://1.2.3.4:1080)
  file    a text file with all of them, one per line, fastest first
  count   how many
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from .api import check_proxies, live_proxies


class InputError(ValueError):
    pass


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value in ("true", "yes", "1"):
        return True
    if value in ("false", "no", "0"):
        return False
    raise InputError(f"{name[3:].lower().replace('_', '-')} must be true or false, not {value!r}")


def _number(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    if not value.isdigit():
        raise InputError(f"{name[3:].lower().replace('_', '-')} must be a whole number, not {value!r}")
    return int(value)


def _list(name: str) -> List[str]:
    return [part.strip().lower() for part in os.environ.get(name, "").split(",") if part.strip()]


def _output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(lines)
    else:
        sys.stdout.write(lines)


def main() -> int:
    try:
        limit = _number("PS_LIMIT", 20)
        recheck = _flag("PS_RECHECK")
        fail_if_empty = _flag("PS_FAIL_IF_EMPTY", True)
        filters = {"types": _list("PS_TYPES") or ["http", "socks4", "socks5"],
                   "countries": os.environ.get("PS_COUNTRIES", "").strip(),
                   "https": _flag("PS_HTTPS"), "min_uptime": _number("PS_MIN_UPTIME", 0),
                   "works_on": _list("PS_WORKS_ON")}
        # a recheck starts from all of them – the limit applies to what still works from here
        found = live_proxies(**filters, limit=0 if recheck else limit)
    except (InputError, ValueError) as e:
        print(f"::error::{e}")
        return 1
    except ConnectionError as e:
        print(f"::error::The live list couldn't be loaded: {e}")
        return 1
    urls = [p.url for p in found]
    if recheck and urls:
        print(f"Checking {len(urls)} proxies again from this runner …")
        urls = [r.url for r in sorted(check_proxies(urls, https=filters["https"]), key=lambda r: r.latency)]
    if limit:
        urls = urls[:limit]
    folder = Path(os.environ.get("RUNNER_TEMP") or ".")
    file = folder / "proxies.txt"
    file.write_text("".join(f"{u}\n" for u in urls), encoding="utf-8")
    _output(proxy=urls[0] if urls else "", file=str(file), count=str(len(urls)))
    print(f"{len(urls)} working {'proxy' if len(urls) == 1 else 'proxies'}" + (f", fastest: {urls[0]}" if urls else ""))
    if not urls and fail_if_empty:
        print("::error::No proxy matches these filters right now – loosen them (min-uptime, works-on, countries) "
              "or set fail-if-empty: false")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
