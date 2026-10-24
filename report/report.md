# The week in free proxies: Oct 17 – Oct 24, 2026

About every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and
SOCKS5 proxies from 700+ lists, checks 150,000 of the candidates and keeps only the ones that pass a basic check, a
second request to another site and a content check. This is what 169 of those runs looked like. An entry
that is not on the list was not necessarily measured as failing.

44,529 different type://ip:port entries passed every check at least once (many are ports on the same host). Of the 43,348 that left the list again, 90 % were not on the next list, and 24 (under 0.1 %) had been on it for 24 runs in a row (about a day) or more. 74 proxies on the list right now have been on it for 24 runs in a row or more.

In the last run Google let 48 % of the 434 HTTPS-capable proxies that gave a clear answer through – 30 % of datacenter exits, 83 % of the other exits.

In the last run Reddit let 32 % of the 395 HTTPS-capable proxies that gave a clear answer through – 14 % of datacenter exits, 74 % of the other exits.

In the last run Amazon let 12 % of the 513 HTTPS-capable proxies that gave a clear answer through – 8 % of datacenter exits, 21 % of the other exits.

In the last run Instagram let 16 % of the 505 HTTPS-capable proxies that gave a clear answer through – 4 % of datacenter exits, 43 % of the other exits.

In the last run TikTok let 71 % of the 441 HTTPS-capable proxies that gave a clear answer through – 86 % of datacenter exits, 38 % of the other exits.

In the last run Discord let 88 % of the 393 HTTPS-capable proxies that gave a clear answer through – 81 % of datacenter exits, 100 % of the other exits.

Between 476 and 4,310 entries were on the list at any one time. Right now: 1,181, 56 % of them tunnel HTTPS to the test host, 56 % are datacenter exits (the provider name looks like a hosting company).

Downloading 100 KB through the HTTPS-capable ones, counting the downloads that finished: half manage 50 KiB/s or more, the fastest tenth over 129 KiB/s.

Most exit IPs are in United States (326), France (137), India (104), Indonesia (72), Germany (70).

![How long free proxies last](https://maximilianfeix.github.io/proxy-scraper/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://maximilianfeix.github.io/proxy-scraper/
Raw data (JSON, CSV, TXT): https://maximilianfeix.github.io/proxy-scraper/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
