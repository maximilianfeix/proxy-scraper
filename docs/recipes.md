# Recipes

← [README](../README.md) · [All docs](README.md)

Short examples are in the [README](../README.md#examples). These are the longer ones: other programs, other libraries, your own lists.

**Use the fastest proxy from the last run** – free proxies die quickly, so `--recheck` first if the run is older than a few minutes

```bash
proxy-scraper --recheck -y
curl -x "$(head -1 results/latest/all.txt)" http://api.ipify.org
```

For HTTPS, pick a proxy with `"https": true` from `proxies.json` – like the Python example below does.

**Python `requests`** (`pip install "requests[socks]"` for SOCKS)

```python
import json
from pathlib import Path

import requests

run = Path("results") / Path("results/latest.txt").read_text().strip()   # works on every OS
proxies = json.loads((run / "proxies.json").read_text())   # fastest first

for p in proxies:
    if not p["https"]:
        continue
    try:
        r = requests.get("https://api.ipify.org", proxies={"http": p["url"], "https": p["url"]}, timeout=8)
        print(p["url"], "→", r.text)
        break
    except requests.RequestException:
        continue  # free proxies come and go – just take the next one
```

**httpx** (`pip install "httpx[socks]"`) – straight from the hourly list, no scan

```python
import httpx
from proxyscraper import live_proxies

for p in live_proxies(types=["http", "socks5"], https=True, min_uptime=90, limit=10):  # httpx can't do SOCKS4
    try:
        with httpx.Client(proxy=p.url, timeout=10) as client:
            print(p.url, "→", client.get("https://api.ipify.org").text)
        break
    except httpx.HTTPError:
        continue  # next one
```

**aiohttp** (`pip install aiohttp aiohttp-socks` – aiohttp alone can't do SOCKS)

```python
import asyncio

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyError
from proxyscraper import live_proxies_async


async def main():
    for p in await live_proxies_async(https=True, min_uptime=90, limit=10):
        try:
            async with aiohttp.ClientSession(connector=ProxyConnector.from_url(p.url)) as session:
                async with session.get("https://api.ipify.org", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    print(p.url, "→", await r.text())
                    return
        except (aiohttp.ClientError, ProxyError, asyncio.TimeoutError, OSError):
            continue  # free proxies come and go – just take the next one

asyncio.run(main())
```

**Scrapy** – a downloader middleware that sends every request, retries included, through the next proxy. Scrapy only speaks HTTP proxies, `https=True` picks the ones that can tunnel `https://` pages

```python
import itertools

import scrapy
from scrapy.crawler import CrawlerProcess
from proxyscraper import live_proxies

PROXIES = [p.url for p in live_proxies(types="http", https=True, min_uptime=50)]
if not PROXIES:
    raise SystemExit("No proxy matches right now – loosen the filters (e.g. min_uptime)")
POOL = itertools.cycle(PROXIES)


class RotatingProxy:
    def process_request(self, request, spider=None):  # newer Scrapy leaves out spider
        request.meta["proxy"] = next(POOL)


class IpSpider(scrapy.Spider):
    name = "ip"
    start_urls = [f"https://api.ipify.org/?n={i}" for i in range(3)]
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {f"{__name__}.RotatingProxy": 350},
        "RETRY_TIMES": 5, "DOWNLOAD_TIMEOUT": 15,
    }

    def parse(self, response):
        print(response.meta["proxy"], "→", response.text)


if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(IpSpider)
    process.start()
```

In a Scrapy project, put `RotatingProxy` in `middlewares.py` and add it to `DOWNLOADER_MIDDLEWARES` in `settings.py`. For long crawls, reload the pool now and then – the list changes every hour.

**Selenium** – Chrome and Firefox can't send a proxy login, so point them at the local rotating server instead: every page load goes out through another checked proxy, and dead ones are skipped for you

```bash
proxy-scraper --recheck live --serve --https-only     # 127.0.0.1:8899, ready in about 30 s
```

```python
from selenium import webdriver

options = webdriver.ChromeOptions()
options.add_argument("--proxy-server=http://127.0.0.1:8899")
driver = webdriver.Chrome(options=options)
driver.get("https://api.ipify.org")
print(driver.find_element("tag name", "body").text)     # a different IP on each start
driver.quit()
```

Firefox takes the proxy as preferences: `options = webdriver.FirefoxOptions()`, then `options.set_preference("network.proxy.type", 1)`, `"network.proxy.http"` / `"network.proxy.ssl"` to `"127.0.0.1"` and `"network.proxy.http_port"` / `"network.proxy.ssl_port"` to `8899`. Keep the server without `--serve-host`, so only your own machine can use it, and start it with `--https-only` when the pages are `https://` – then only proxies that passed the HTTPS test with verified TLS serve them. One browser session keeps its connections, so for a new IP per page use `session-NAME` in the proxy login (not possible in Selenium) or restart the driver.

**proxychains, Clash / Mihomo, sing-box** – ready-made configs with `--export`

```bash
proxy-scraper --want 30 -y --export proxychains,clash,singbox
proxychains4 -f results/latest/proxychains.conf curl https://api.ipify.org
```

`clash.yaml` has all HTTP and SOCKS5 proxies plus a `url-test` group that always picks the fastest. `singbox.json` does the same for sing-box, SOCKS4 included, and opens a local proxy: `sing-box run -c results/latest/singbox.json`, then use `127.0.0.1:2080` as HTTP or SOCKS5 proxy. All three leave out HTTP proxies that can't tunnel (`CONNECT`), because these tools tunnel everything.

**Browsers and the OS** – `--export pac` writes `proxy.pac`: point Firefox, Chrome (via the system settings), FoxyProxy or macOS/Windows proxy settings at it and every request goes through the best 30 HTTP and SOCKS5 proxies in order, the browser moving on by itself when one fails. Local names and private IP addresses stay direct (a host name like `10.example.com` doesn't count as private). The file itself has no `DIRECT` fallback and resolves no host names, and SOCKS4 is left out because it would make the browser resolve names with your own DNS. Two Firefox settings matter: turn on *Proxy DNS when using SOCKS v5*, and set `network.proxy.failover_direct` to `false` in `about:config` – otherwise Firefox goes direct once every proxy has failed. No install at all: the live list publishes one every hour at `https://proxy-scraper.de/proxy.pac`.

**Proxifier** (Windows, macOS) sends *any* program through a proxy, even ones without proxy settings. `--export proxifier` writes `proxifier.ppx`: import it via *File → Import Profile*, and every connection goes through a redundancy chain of the best 50 proxies – Proxifier tries them in order and takes the first that answers. `localhost` stays direct. HTTP proxies are included only when they can tunnel (`CONNECT`), SOCKS4 only without a login. Needs Proxifier 4; add `--https-only` for proxies that passed the HTTPS test.

**Burp Suite, OWASP ZAP, mitmproxy** – put the rotating server behind your intercepting proxy, so a scan or a brute-force test comes from many IPs while you still see every request. Start it with `proxy-scraper --recheck live --serve`, then:

| Tool | Where | Set |
|---|---|---|
| Burp Suite | *Settings → Network → Connections → Upstream proxy servers* | a rule for destination host `*`, proxy host `127.0.0.1`, port `8899`; with `--serve-password` add Basic auth (user `any` or a wish like `country-de`, the password) |
| OWASP ZAP | *Options → Network → Connection → HTTP Proxy* | host `127.0.0.1`, port `8899`, and under its authentication the user (`any` or a wish) and the password – use the HTTP setting, not SOCKS: ZAP never sends loopback addresses through its SOCKS proxy |
| mitmproxy | command line | `mitmproxy --mode upstream:http://127.0.0.1:8899 --upstream-auth country-us:x` |

Username wishes – `country-us` sends everything out through US proxies, `session-NAME` keeps one exit IP for a login flow – reach the server as the proxy login. mitmproxy sends it right away; Burp and ZAP may wait to be asked, so start the server with `--serve-password` when you rely on a wish there. **Keep your tool's upstream certificate checks on** (no `--ssl-insecure` in mitmproxy, no "ignore certificate errors" upstream in Burp or ZAP): free proxies are strangers, and that check is what stops one from reading or changing your HTTPS traffic. Tested end to end with mitmproxy 12, certificate checks on: HTTP and HTTPS through mitmproxy and the rotating server, every request out through a US proxy, and a site with an expired certificate refused. Only test what you're allowed to.

**In a pipe** – `-o -` prints the hits to stdout, the interface moves to stderr

```bash
proxy-scraper --recheck live --want 20 -y -o - | grep '^socks5://' > socks.txt
```

**Check a list you already have** – `--recheck -` reads it from stdin: plain `ip:port` lines, `type://ip:port`, logins (`user:pass@ip:port` or `ip:port:user:pass`), JSON, a CSV export or a table pasted from a website (HTML or Markdown), in the order it came in. Only what works from your network comes out:

```bash
curl -s https://example.com/proxies.txt | proxy-scraper --recheck - -o - > working.txt
```

Proxies without a type are tried as HTTP and as SOCKS5 – or as SOCKS4 with `--types socks4` alone. A password with a comma, quote, `|` or bracket can't be told apart from the text around it in a paste; put such proxies in a file, one per line, and use `--recheck file.txt`.

**Any tool, through the rotating server**

```bash
proxy-scraper --recheck --serve &
export HTTPS_PROXY=http://127.0.0.1:8899 HTTP_PROXY=http://127.0.0.1:8899
pip download requests   # git, pip, npm & co. now go through the pool
```

**In a GitHub workflow** – the action picks working proxies for the next steps

[Marketplace](https://github.com/marketplace/actions/proxy-scraper-free-working-proxies) · [Complete workflow, inputs and outputs](github-action.md)

```yaml
- id: proxies
  uses: maximilianfeix/proxy-scraper@v1
  with:
    types: socks5
    https: true
    min-uptime: 90        # on the list for 90 %+ of the week
    min-speed: 100        # optional: downloaded 100+ KB/s in the last check
    works-on: google      # optional: google, reddit, amazon
    recheck: true         # optional: check them again from the runner
- run: curl -x "${{ steps.proxies.outputs.proxy }}" https://api.ipify.org
```

`proxy` is the fastest one, `file` a text file with all of them (up to `limit`, default 20), `count` how many. Without a match the step fails, unless `fail-if-empty: false`.

**In the shell, without a scan** – `--pick` takes proxies from the hourly list in about half a second

```bash
curl -x "$(proxy-scraper --pick --https-only --min-uptime 90)" https://api.ipify.org
proxy-scraper --pick 10 --country DE --works-on google > de.txt
proxy-scraper --pick 5 --min-speed 200     # only ones that downloaded 200+ KB/s
```

"Fastest first" means the first answer plus the download speed measured in the last check – in a test with real
pages, the 25 fastest by download loaded four times as many pages as the 25 quickest to answer a tiny request.

**Without installing anything** – straight from the live list

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt | head -5
```

The shell snippets are for macOS and Linux, where `results/latest` points to the newest run. On Windows, `results/latest.txt` holds the folder name instead – in PowerShell:

```powershell
$run = "results\$(Get-Content results\latest.txt)"
curl.exe -x (Get-Content "$run\all.txt" -TotalCount 1) http://api.ipify.org
```

## Your own lists

```bash
proxy-scraper --source https://example.com/my-list.txt --source socks5=./socks.txt   # on top of the built-in sources
proxy-scraper --only-sources --source bought.txt --want 50                            # only yours
```

Any text with `ip:port` works; lines like `socks5://user:pass@host:port` keep their type, bare ones are tried as HTTP and SOCKS5 unless you write `http=…`. For logins written the way many paid lists export them, `ip:port:user:pass`, use `--recheck bought.txt`, `--recheck https://example.com/proxies.txt` for a list on the web, or pipe the list into `--recheck -` – sources leave that form alone, since lists like `ip:port:US:elite` look the same.
