# The week in free proxies: Nov 14 – Nov 21, 2026

About every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and
SOCKS5 proxies from 700+ lists, checks 150,000 of the candidates and keeps only the ones that pass a basic check, a
second request to another site and a content check. This is what 168 of those runs looked like. An entry
that is not on the list was not necessarily measured as failing.

16,945 different type://ip:port entries passed every check at least once (many are ports on the same host). Of the 15,858 that left the list again, 87 % were not on the next list, and 4 (under 0.1 %) had been on it for 24 runs in a row (about a day) or more. 61 proxies on the list right now have been on it for 24 runs in a row or more.

In the last run Google let 79 % of the 314 HTTPS-capable proxies that gave a clear answer through – 68 % of datacenter exits, 81 % of the other exits.

In the last run Reddit let 88 % of the 275 HTTPS-capable proxies that gave a clear answer through – 43 % of datacenter exits, 97 % of the other exits.

In the last run Amazon let 44 % of the 315 HTTPS-capable proxies that gave a clear answer through – 27 % of datacenter exits, 49 % of the other exits.

In the last run Instagram let 53 % of the 288 HTTPS-capable proxies that gave a clear answer through – 25 % of datacenter exits, 61 % of the other exits.

In the last run TikTok let 29 % of the 284 HTTPS-capable proxies that gave a clear answer through – 67 % of datacenter exits, 20 % of the other exits.

In the last run Discord let 100 % of the 266 HTTPS-capable proxies that gave a clear answer through – 100 % of datacenter exits, 100 % of the other exits.

Between 520 and 2,077 entries were on the list at any one time. Right now: 1,071, 55 % of them tunnel HTTPS to the test host, 24 % are datacenter exits (the provider name looks like a hosting company).

Downloading 100 KB through the HTTPS-capable ones, counting the downloads that finished: half manage 72 KiB/s or more, the fastest tenth over 109 KiB/s.

Most exit IPs are in United States (183), Indonesia (125), Netherlands (84), Vietnam (48), India (46).

![How long free proxies last](https://proxy-scraper.de/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://proxy-scraper.de/
Raw data (JSON, CSV, TXT): https://proxy-scraper.de/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
