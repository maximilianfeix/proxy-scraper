# The week in free proxies: Oct 10 – Oct 17, 2026

About every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and
SOCKS5 proxies from 700+ lists, checks 150,000 of the candidates and keeps only the ones that pass a basic check, a
second request to another site and a content check. This is what 168 of those runs looked like. An entry
that is not on the list was not necessarily measured as failing.

47,661 different type://ip:port entries passed every check at least once (many are ports on the same host). Of the 46,572 that left the list again, 87 % were not on the next list, and 42 (under 0.1 %) had been on it for 24 runs in a row (about a day) or more. 80 proxies on the list right now have been on it for 24 runs in a row or more.

In the last run Google let 56 % of the 443 HTTPS-capable proxies that gave a clear answer through – 47 % of datacenter exits, 79 % of the other exits.

In the last run Reddit let 34 % of the 414 HTTPS-capable proxies that gave a clear answer through – 20 % of datacenter exits, 83 % of the other exits.

In the last run Amazon let 30 % of the 505 HTTPS-capable proxies that gave a clear answer through – 30 % of datacenter exits, 31 % of the other exits.

In the last run Instagram let 14 % of the 477 HTTPS-capable proxies that gave a clear answer through – 9 % of datacenter exits, 28 % of the other exits.

In the last run TikTok let 76 % of the 427 HTTPS-capable proxies that gave a clear answer through – 92 % of datacenter exits, 32 % of the other exits.

In the last run Discord let 97 % of the 398 HTTPS-capable proxies that gave a clear answer through – 98 % of datacenter exits, 95 % of the other exits.

Between 689 and 4,195 entries were on the list at any one time. Right now: 989, 66 % of them tunnel HTTPS to the test host, 61 % are datacenter exits (the provider name looks like a hosting company).

Downloading 100 KB through the HTTPS-capable ones, counting the downloads that finished: half manage 47 KiB/s or more, the fastest tenth over 128 KiB/s.

Most exit IPs are in United States (246), France (148), Germany (129), Indonesia (58), India (54).

![How long free proxies last](https://maximilianfeix.github.io/proxy-scraper/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://maximilianfeix.github.io/proxy-scraper/
Raw data (JSON, CSV, TXT): https://maximilianfeix.github.io/proxy-scraper/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
