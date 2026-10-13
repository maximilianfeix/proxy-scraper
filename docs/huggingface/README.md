---
license: mit
pretty_name: Checked free proxies – daily snapshots
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

# Checked free proxies – daily snapshots

One Parquet file per UTC day with every public HTTP, SOCKS4 and SOCKS5 proxy that passed all checks in the
first published run of that day. Collected by [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper),
which pulls from hundreds of public lists and keeps only the entries that pass every check. All rows are entries
that passed: candidates that failed or were not checked are not in the data. An entry is a `type://ip:port`
combination, not a machine – many are ports on the same host.

```python
from datasets import load_dataset

ds = load_dataset("Taventix/proxy-scraper-snapshots", split="train")
df = ds.to_pandas()
# non-hoster exits that got through to Reddit, by country
non_hoster = df[(df.hosting == False) & df.works_on.apply(lambda sites: "reddit" in sites)]
non_hoster.groupby("country").size().sort_values(ascending=False).head()
```

## How a proxy gets in

About every hour 150,000 candidates are checked, out of roughly 1.2–1.4 million listed protocol/address
combinations. Proxies that passed before and sources with a good hit rate go first. An entry is kept only if it

1. completes a real protocol handshake (HTTP CONNECT, SOCKS4 or SOCKS5) and a first request that returns a public
   exit IP that is not ours,
2. shows the same exit IP on a second request to an unrelated site. A failure means only that the second request
   did not confirm the proxy: an unstable proxy, an exit that changes between requests, a proxy that only answers
   the first check, or the second site refusing it,
3. returns one static test page byte for byte over plain HTTP. A failure means the bytes differed; why is not
   determined,
4. for `https = true`, tunnels to one test host on port 443 with a TLS certificate that verifies, at check time.

Of 3.6 million checks of that prioritised sample in one day, 1.1 % passed. A day's snapshot holds between 1,000
and 2,200 proxies.

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
| `hosting` | bool | The provider name of the exit IP looks like a hosting company (datacenter) |
| `blocklisted` | bool | Exit IP is on the SpamCop blocklist |
| `anonymity` | string | `elite` (target sees no proxy), `anonymous` or `transparent` |
| `https` | bool | Passed the HTTPS test: a tunnel to one test host with a TLS certificate that verifies, at check time |
| `latency` | int64 | Response time in the check, milliseconds |
| `speed_kbps` | int64 | Download speed in KiB/s (HTTPS-capable proxies only, measured since 2026-09-28) |
| `works_on` | list of strings | Big sites it got through to in that run: google, reddit, amazon, instagram, tiktok, discord |
| `blocked_on` | list of strings | Big sites that turned it away in that run |
| `streak` | int64 | Consecutive published runs (about hourly) it has been on the list |
| `uptime_24h` | int64 | Share of the published runs of the last 24 hours in which it was on the list, percent |
| `uptime_7d` | int64 | Share of the published runs of the last 7 days in which it was on the list, percent |
| `first_seen` | string | When it was first on the list, ISO 8601 UTC |
| `snapshot_date` | string | The UTC day of the snapshot, `YYYY-MM-DD` |

Sites are only checked for proxies with `https = true`, so both lists are empty for the others. For an
HTTPS proxy, a site in neither list gave no clear answer or wasn't checked yet that day: google, reddit and
amazon from the start, instagram and tiktok since 2026-09-28, discord since 2026-10-06. Fields that weren't
measured yet on early days are null, and so are `asn`, `org`, `country`, `anonymity` and `exit_ip` when they're unknown. Every file has
the same columns, so all days load as one table.

Not being on the list in a run is not a measured failure, so `streak` and `uptime_*` describe list membership.
From proxy-scraper 1.29 on, each row of the published `proxies.json` and of the daily `proxies-YYYY-MM-DD.json.gz`
snapshots in the GitHub release also carries `checked_at` and `checks`: how each check ended (`passed`, `failed`,
`unavailable` or `skipped`). The Parquet files here keep the fixed columns above.

## What it's good for

- **Security monitoring:** open proxies that relay traffic right now – search them in login and outbound logs.
- **Churn and lifetime:** `streak`, `uptime_*` and `first_seen` show how long entries stay on the list. Most of
  the entries that leave it had been on it for a single run.
- **Who hosts open proxies:** `asn`, `org`, `hosting` and `country` over time.
- **Site blocking:** how Google, Reddit, Amazon, Instagram, TikTok and Discord treat datacenter exits vs. other exits.

## Caveats

- Free proxies are run by strangers: misconfigured servers, infected machines and traps. Don't send credentials
  or personal data through them.
- Checks run from GitHub Actions in the US; a proxy can behave differently from another network.
- A snapshot is the first published run of each UTC day; the live list on the
  [`proxy-list` branch](https://github.com/maximilianfeix/proxy-scraper/tree/proxy-list) and in
  [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) is rebuilt about every hour.

This card is kept in the [proxy-scraper repository](https://github.com/maximilianfeix/proxy-scraper/blob/main/docs/huggingface/README.md)
and uploaded with each daily snapshot. MIT licensed.
