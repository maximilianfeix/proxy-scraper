# How proxy-scraper compares to other free proxy lists

Checked on **2026-10-11** against each project's README. "Not documented" means the README doesn't say – it may still happen, it's just not something you can rely on. Corrections welcome, open an issue or a PR.

| | [proxifly/free-proxy-list](https://github.com/proxifly/free-proxy-list) | [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List) | [monosans/proxy-list](https://github.com/monosans/proxy-list) | [clarketm/proxy-list](https://github.com/clarketm/proxy-list) | **proxy-scraper** |
|---|:---:|:---:|:---:|:---:|:---:|
| Refreshed | every 5 minutes | "from time to time" | every hour | last update March 2026 | every hour |
| Proxy must complete a real request | "validated" | not documented | yes, a full URL fetch | not documented | yes, two independent pages with the same exit IP |
| Honeypots that only answer check requests filtered | not documented | not documented | not documented | not documented | yes, second request to a different site |
| Proxies that inject scripts or ads filtered | not documented | not documented | not documented | not documented | yes, byte-for-byte content check |
| HTTPS tested with verified TLS | not documented | not documented | not documented | not documented | yes |
| Per-protocol files | txt, json, csv | txt | txt, json | txt | txt, json, csv |
| Per-country files | yes | no | no (country in JSON) | no | yes, plus per site (Google, Reddit, Amazon, …) |
| Latency, country, ASN per proxy | country | no | yes, with city | no | yes, plus anonymity, datacenter flag, uptime |
| Re-check the list from your own network | no | no | separate tool | no | `proxy-scraper --recheck live`, about 30 s |
| Single rotating proxy from the list | no | no | no | no | `--serve`, with country and session selection |
| Proxy pool API (`/get`, `/all`, …) | no | no | no | no | yes, jhao104/proxy_pool compatible |
| For AI agents (MCP server) | no | no | no | no | yes |
| Python library | npm module | no | no | no | `pip install proxy-scraper-cli` |

## What this means in practice

- **Bigger isn't better.** On the day of this comparison proxifly listed about 57,000 proxies and TheSpeedX about 7,500; proxy-scraper's hourly list had 1,600. The difference is mostly what the checks remove: in [24 hourly runs](free-proxies-in-numbers.md), 54 % of the proxies that answered a first request failed the second one, and 1 in 40 of the ones that worked changed the page they delivered.
- **Age matters more than size.** 85 % of the proxies that drop off the list are gone within an hour. A list that isn't rebuilt at least hourly is mostly a list of dead proxies, however long it is.
- **Check from where you run.** All of these lists, this one included, check from somewhere else. `proxy-scraper --recheck live` takes the hourly list and runs every check again from your network in about 30 seconds.

If you want a longer list and don't mind checking it yourself, the other projects are fine choices – proxy-scraper even reads some of them as sources, and its hourly list is in turn a built-in source of [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) and [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).
