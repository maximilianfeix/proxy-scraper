---
license: mit
pretty_name: Verified free proxies – daily snapshots
tags:
- proxies
- networking
- cybersecurity
- web-scraping
- ip-addresses
- open-proxies
- threat-intelligence
- time-series
configs:
- config_name: default
  data_files: "data/*/*.parquet"
---

# Verified free proxies – daily snapshots

One Parquet file per UTC day with every public HTTP, SOCKS4 and SOCKS5 proxy that passed all checks in the
first hourly run of that day. Collected by [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper),
which pulls from 700+ public lists and keeps only proxies that actually relay traffic.

```python
from datasets import load_dataset

ds = load_dataset("Taventix/proxy-scraper-snapshots", split="train")
df = ds.to_pandas()
# residential HTTPS exits that got through to Reddit, by country
residential = df[(df.hosting == False) & df.works_on.apply(lambda sites: "reddit" in sites)]
residential.groupby("country").size().sort_values(ascending=False).head()
```

## How a proxy gets in

Each hour about 150,000 candidates are checked, and a proxy is kept only if it

1. completes a real protocol handshake (HTTP CONNECT, SOCKS4 or SOCKS5),
2. loads two unrelated sites with the same exit IP – scanner-only honeypots fail here,
3. returns a known page byte for byte – proxies that inject scripts or ads fail here,
4. for `https = true`, tunnels TLS with a certificate that verifies.

Of 3.6 million checks in one day, 1.1 % passed. A day's snapshot holds between 1,000 and 2,200 proxies.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `url` | string | Ready-to-use proxy URL, e.g. `socks5://1.2.3.4:1080` |
| `ptype` | string | Protocol: `http`, `socks4` or `socks5` |
| `proxy` | string | `ip:port` |
| `exit_ip` | string | IP address the target site saw (can differ from the proxy's own IP) |
| `country` | string | Two-letter country code of the exit IP |
| `asn` | int64 | Autonomous system number of the exit IP |
| `org` | string | Network / provider that owns the exit IP |
| `hosting` | bool | Exit IP is in a datacenter or hosting network |
| `blocklisted` | bool | Exit IP is on the SpamCop blocklist |
| `anonymity` | string | `elite` (target sees no proxy), `anonymous` or `transparent` |
| `https` | bool | Tunnels HTTPS with a verified TLS handshake |
| `latency` | int64 | Response time in the check, milliseconds |
| `speed_kbps` | int64 | Download speed in KiB/s (HTTPS-capable proxies only, measured since 2026-09-28) |
| `works_on` | list of strings | Big sites it got through to in that run: google, reddit, amazon, instagram, tiktok, discord |
| `blocked_on` | list of strings | Big sites that turned it away in that run |
| `streak` | int64 | Consecutive hourly runs it has been on the list |
| `uptime_24h` | int64 | Share of the last 24 hourly runs it passed, percent |
| `uptime_7d` | int64 | Share of the last 7 days' hourly runs it passed, percent |
| `first_seen` | string | When it first passed, ISO 8601 UTC |
| `snapshot_date` | string | The UTC day of the snapshot, `YYYY-MM-DD` |

Sites are only checked for proxies with `https = true`, so both lists are empty for the others. For an
HTTPS proxy, a site in neither list gave no clear answer or wasn't checked yet that day: google, reddit and
amazon from the start, instagram and tiktok since 2026-09-28, discord since 2026-10-06. Fields that weren't
measured yet on early days are null, and so are `asn` and `org` when the network is unknown. Every file has
the same columns, so all days load as one table.

## What it's good for

- **Security monitoring:** open proxies that relay traffic right now – search them in login and outbound logs.
- **Churn and lifetime:** most free proxies are gone within an hour; `streak`, `uptime_*` and `first_seen` show
  how long they last.
- **Who hosts open proxies:** `asn`, `org`, `hosting` and `country` over time.
- **Site blocking:** how Google, Reddit, Amazon, Instagram, TikTok and Discord treat datacenter vs. residential exits.

## Caveats

- Free proxies are run by strangers: misconfigured servers, infected machines and traps. Don't send credentials
  or personal data through them.
- Checks run from GitHub Actions in the US; a proxy can behave differently from another network.
- A snapshot is one hourly run per day; the live list on the
  [`proxy-list` branch](https://github.com/maximilianfeix/proxy-scraper/tree/proxy-list) and in
  [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) is rebuilt every hour.

This card is kept in the [proxy-scraper repository](https://github.com/maximilianfeix/proxy-scraper/blob/main/docs/huggingface/README.md)
and uploaded with each daily snapshot. MIT licensed.
