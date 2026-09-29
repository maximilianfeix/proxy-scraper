# I checked 3.6 million free proxies in a day. Here's what's actually out there.

Free proxy lists have a reputation: most entries are dead, and the ones that answer are slow, blocked or worse. I wanted numbers instead of a reputation, so [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) now checks the public lists every hour in GitHub Actions and publishes what survives. These are the numbers from 24 of those runs (Sep 28–29, 2026) and from the last week of hourly lists.

## The funnel

Each run reads about 800 public proxy lists (GitHub repos, websites, meta lists) and ends up with **1.26 million unique addresses** on average. It checks 150,000 of them per run, so **3.6 million checks** over the day.

| Step | What it checks | Over 24 runs |
|---|---|---|
| Handshake | the proxy speaks HTTP, SOCKS4 or SOCKS5 and reaches checkip.amazonaws.com | 93,244 answered |
| Second request | a second, independent request to httpbin.org returns valid JSON with the same exit IP | **50,193 failed (54 %)** |
| Content | a known page arrives byte for byte | **2,244 changed it (2.4 %)** |
| Kept | | **40,807 (1.1 % of all checks)** |

Two things surprised me:

- **More than half of the proxies that pass a normal "does it answer" check fail the second request.** Some are honeypots that answer the first probe of a scanner and nothing else, many are simply too unstable to load two pages in a row. Either way, a list that only checks whether the port answers is mostly handing you these.
- **About 1 in 40 working proxies modifies the page you load**, usually by injecting a script. That's roughly 100 proxies in every hourly run that look fine by every other measure.

## They don't last

Over 99 hourly runs, **31,523 different proxies** passed every check at least once. Of the 28,607 that dropped off again:

- **85 % were gone by the very next check**, an hour later
- only **4** stayed up for a day straight (24 checks in a row)

So a list that is a day old is mostly a list of dead proxies, and "free proxy list, updated daily" means less than it sounds.

## Where they get through

Every hour each proxy on the list also tries a few big sites:

| Site | Gets through | datacenter exits | other exits |
|---|---|---|---|
| TikTok | 67 % | 86 % | 22 % |
| Google | 47 % | 40 % | 65 % |
| Reddit | 30 % | 8 % | 86 % |
| Instagram | 19 % | 5 % | 51 % |
| Amazon | 2 % | 1 % | 3 % |

Reddit and Instagram block datacenter IPs hard, but let most home and mobile connections through. Amazon blocks almost everything.

## What the working ones look like

From the list published at the time of writing (2,914 proxies):

- **62 % exit from a datacenter**, 28 % of exit IPs are on the SpamCop blocklist
- **64 % tunnel HTTPS** with a verified TLS handshake
- median latency **1.9 s**, median download speed **68 KiB/s**; the fastest tenth manage over 142 KiB/s
- SOCKS5 is by far the most common working type: in the last run 4.3 % of SOCKS5 candidates worked, against 0.7 % of HTTP and 0.6 % of SOCKS4
- most sit in the US (1,189), China (222), Germany (199), India (173) and Indonesia (142)

## How to read these numbers

The runs don't check a random sample. Proxies that worked before and sources with a good hit rate go first, so the 1.1 % is higher than what you'd get checking a random address from these lists. The real share is lower. Checks use a 3 s connect timeout and 6 s overall, from GitHub-hosted runners in the US. A proxy that fails here can work from somewhere else, which is why the tool can also run the same checks from your own network.

## Try it

- The live list, with filters for country, protocol and the sites above: https://maximilianfeix.github.io/proxy-scraper/
- Raw data every hour (TXT, JSON, CSV): https://maximilianfeix.github.io/proxy-scraper/proxies.json
- Run the checks yourself: `pipx install proxy-scraper-cli && proxy-scraper`
- Source, MIT licensed: https://github.com/maximilianfeix/proxy-scraper

Free proxies are run by strangers. Never send passwords, cookies or personal data through them.
