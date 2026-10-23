# Roadmap and what shipped

← [README](../README.md) · [All docs](README.md)

What's next is in the [open issues](https://github.com/maximilianfeix/proxy-scraper/issues) – ideas and wishes are welcome as an [issue](https://github.com/maximilianfeix/proxy-scraper/issues/new/choose). During Hacktoberfest there are [beginner-friendly issues](https://github.com/maximilianfeix/proxy-scraper/issues?q=is%3Aopen+label%3Ahacktoberfest) with pointers on where to start.

Shipped in v1.24 to v1.26: `--recheck -` for lists you pipe in, which proxies get through to Discord, a README you can try in five seconds, the MCP server in the Docker image, logins written as `ip:port:user:pass`, and a Hugging Face dataset that loads in one line.

Shipped in v1.22 and v1.23: a live dashboard for the rotating server, `--export pac` and an hourly `proxy.pac`, "best first" that counts how likely a proxy is still up, the lists in a repository of their own ([free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)), daily snapshots on Hugging Face, `brew install`, a Chinese README, Python 3.14, and a recipe for Burp Suite, ZAP and mitmproxy.

Shipped in v1.10 to v1.21: download speed per proxy and "best first" everywhere, daily snapshots, a rotating proxy URL for requests, httpx and Playwright, `--pick` for working proxies without a scan, a proxy pool API compatible with jhao104/proxy_pool, your own lists with `--source`, a GitHub Action, a Telegram bot and an Atom feed for the weekly report.

Shipped in v1.8 and v1.9: uptime per proxy and `stable.txt`, which proxies get through to Google, Reddit and Amazon, `live_proxies()` in Python, a page per proxy with its week of checks, a weekly report, live charts in this README, shareable filters on the website, sources mined from other scrapers' lists, untyped lists tried as HTTP and SOCKS5, `--export singbox`, PowerShell completion and recipes for httpx, aiohttp and Scrapy.

Shipped in [v1.7](https://github.com/maximilianfeix/proxy-scraper/milestone/7): an MCP server so AI agents get working proxies and can load pages through them, 28 new sources and a GitHub search that runs daily and keeps what it found, and a cleaner website.

Shipped in [v1.6](https://github.com/maximilianfeix/proxy-scraper/milestone/6): spam blocklist check for every exit IP, a live list refreshed every hour, pages per protocol and country, an optional password for the proxy server and a pool that refills itself while it runs, `compose.yaml`, `-o -` for pipes, a Discord bot, and a new website and README – everything in English now.

Shipped in [v1.5](https://github.com/maximilianfeix/proxy-scraper/milestone/5): content tampering check, live list website with trend and stable proxies, provider/datacenter info, a much bigger proxy server (rotation strategies, sticky sessions, SOCKS5 inbound, status and Prometheus metrics), `--recheck live`, Python API, shell completion. Measured and dropped earlier: protocol detection with an extra connection ([#3](https://github.com/maximilianfeix/proxy-scraper/issues/3)) and IPv6 ([#1](https://github.com/maximilianfeix/proxy-scraper/issues/1)).
