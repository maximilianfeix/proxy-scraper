---
title: "I checked 3.6 million free proxies. 54% of the ones that answered failed the second request"
published: false
description: "Real numbers on free proxies: how many are honeypots, how many inject scripts, how long they live, and the three checks that sort them."
tags: python, webscraping, opensource, security
cover_image:
canonical_url:
---

Every scraping project I've done hit the same wall: the free proxy list that "worked yesterday" is dead today. So I stopped trusting the reputation and measured it.

I wrote an open-source checker, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper), that reads about 800 public proxy lists and checks every address it finds. These are the numbers from 24 runs (Sep 28–29, 2026) and one week of hourly lists.

## The funnel

Each run ends up with about **1.26 million unique addresses** and checks 150,000 of them. Over the day that is **3.6 million checks**.

| Step | What it checks | Result over 24 runs |
|---|---|---|
| Handshake | the proxy speaks HTTP, SOCKS4 or SOCKS5 and reaches an IP-echo service | 93,244 answered |
| Second request | an independent request to a different site returns the same exit IP | **50,193 failed (54 %)** |
| Content | a known page arrives byte for byte | **2,244 changed it (2.4 %)** |
| Kept | | **40,807 (1.1 % of all checks)** |

Two numbers surprised me.

**More than half of the proxies that pass a normal "does it answer" check fail the second request.** Some are honeypots that answer the first probe of a scanner and nothing else. Many are just too unstable to load two pages in a row. A list that only tests whether the port answers hands you exactly these.

**About 1 in 40 working proxies modifies the page you load**, usually by injecting a script. That's roughly 100 proxies per hourly run that look fine by every other measure.

## Three checks that do the sorting

### 1. A real handshake, not "port open"

Opening a TCP port proves nothing. The checker speaks the actual protocol: `CONNECT` for HTTP proxies, the SOCKS4 and SOCKS5 greetings (including login), and then fetches its exit IP through the proxy. The IP has to be valid and *different from yours*, otherwise it's a transparent proxy that leaks you.

### 2. Two independent requests

The second request goes to a different service and must return valid JSON with the same exit IP. That is what filters the honeypots that only fake the first answer.

### 3. A byte-for-byte page

A static page is fetched through the proxy and compared with the original. If one byte differs, it's out. That's how the script injectors drop out.

HTTPS only counts if the TLS handshake verifies end to end through a tunnel. Proxies that break up the encryption are marked, not used for it.

## They don't last

Over 99 hourly runs, **31,523 different proxies** passed every check at least once. Of the 28,607 that dropped off again:

- **85 % were gone by the very next check**, an hour later
- only **4** stayed up for a full day (24 checks in a row)

So "free proxy list, updated daily" means less than it sounds. A day-old list is mostly dead proxies.

## Where they get through

Every hour each proxy on the list also tries a few big sites:

| Site | Gets through | Datacenter exits | Other exits |
|---|---|---|---|
| TikTok | 67 % | 86 % | 22 % |
| Google | 47 % | 40 % | 65 % |
| Reddit | 30 % | 8 % | 86 % |
| Instagram | 19 % | 5 % | 51 % |
| Amazon | 2 % | 1 % | 3 % |

Reddit and Instagram block datacenter IPs hard but let most home and mobile connections through. Amazon blocks almost everything.

## Try it

No install needed:

```bash
uvx proxy-scraper-cli --pick 5
```

Five checked proxies in about five seconds. For more control:

```bash
# 50 proxies that can do HTTPS
proxy-scraper --want 50 --https-only

# fast elite SOCKS5 proxies
proxy-scraper --types socks5 --anonymity elite --max-latency 1500

# only Germany, Austria and Switzerland
proxy-scraper --country DE,AT,CH
```

Or run it as one rotating local proxy. Every connection leaves through another checked proxy, a failing one is swapped automatically:

```bash
proxy-scraper --recheck live --serve
curl -x http://127.0.0.1:8899 https://api.ipify.org
```

The hourly list is also published as TXT, JSON and CSV: <https://maximilianfeix.github.io/proxy-scraper/>

## How to read these numbers

The runs don't check a random sample. Proxies that worked before, and sources with a good hit rate, go first, so the 1.1 % is higher than what you'd get checking a random address. The real share is lower. Checks use a 3 s connect timeout and 6 s overall, from GitHub-hosted runners in the US. A proxy that fails there can work from somewhere else, which is why the tool can also run the same checks from your own network.

## Honest limits

These are still free proxies run by strangers. They are fine for testing and public data. **Never send passwords, cookies or personal data through them.** proxy-scraper can't tell an infected home router from an open office proxy, it only filters what it can measure.

## Code and feedback

MIT licensed, Python 3.9+, runs on Linux, macOS and Windows: <https://github.com/maximilianfeix/proxy-scraper>

There are good first issues open if you want to contribute, and I'd like to hear which check you would add. What would you test that I don't?

*Disclosure: the tool and this article were written with AI assistance (Claude Code). I run and verify the measurements myself.*
