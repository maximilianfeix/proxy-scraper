# The week in free proxies: Nov 07 – Nov 14, 2026

About every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and
SOCKS5 proxies from 700+ lists, checks 150,000 of the candidates and keeps only the ones that pass a basic check, a
second request to another site and a content check. This is what 166 of those runs looked like. An entry
that is not on the list was not necessarily measured as failing.

25,319 different type://ip:port entries passed every check at least once (many are ports on the same host). Of the 24,537 that left the list again, 88 % were not on the next list, and 11 (under 0.1 %) had been on it for 24 runs in a row (about a day) or more. 71 proxies on the list right now have been on it for 24 runs in a row or more.

In the last run Google let 26 % of the 194 HTTPS-capable proxies that gave a clear answer through – 30 % of datacenter exits, 24 % of the other exits.

In the last run Reddit let 40 % of the 187 HTTPS-capable proxies that gave a clear answer through – 38 % of datacenter exits, 41 % of the other exits.

In the last run Amazon let 9 % of the 235 HTTPS-capable proxies that gave a clear answer through – 4 % of datacenter exits, 12 % of the other exits.

In the last run Instagram let 19 % of the 217 HTTPS-capable proxies that gave a clear answer through – 21 % of datacenter exits, 17 % of the other exits.

In the last run TikTok let 65 % of the 202 HTTPS-capable proxies that gave a clear answer through – 69 % of datacenter exits, 64 % of the other exits.

In the last run Discord let 98 % of the 194 HTTPS-capable proxies that gave a clear answer through – 100 % of datacenter exits, 97 % of the other exits.

Between 294 and 3,356 entries were on the list at any one time. Right now: 750, 52 % of them tunnel HTTPS to the test host, 31 % are datacenter exits (the provider name looks like a hosting company).

Downloading 100 KB through the HTTPS-capable ones, counting the downloads that finished: half manage 82 KiB/s or more, the fastest tenth over 115 KiB/s.

Most exit IPs are in United States (265), Netherlands (42), India (33), Japan (32), France (28).

![How long free proxies last](https://proxy-scraper.de/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://proxy-scraper.de/
Raw data (JSON, CSV, TXT): https://proxy-scraper.de/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
