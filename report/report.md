# The week in free proxies: Nov 21 – Nov 28, 2026

About every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and
SOCKS5 proxies from 700+ lists, checks 150,000 of the candidates and keeps only the ones that pass a basic check, a
second request to another site and a content check. This is what 169 of those runs looked like. An entry
that is not on the list was not necessarily measured as failing.

9,035 different type://ip:port entries passed every check at least once (many are ports on the same host). Of the 8,452 that left the list again, 84 % were not on the next list, and 10 (0.1 %) had been on it for 24 runs in a row (about a day) or more. 25 proxies on the list right now have been on it for 24 runs in a row or more.

In the last run Google let 48 % of the 167 HTTPS-capable proxies that gave a clear answer through – 41 % of datacenter exits, 54 % of the other exits.

In the last run Reddit let 60 % of the 149 HTTPS-capable proxies that gave a clear answer through – 20 % of datacenter exits, 99 % of the other exits.

In the last run Amazon let 46 % of the 175 HTTPS-capable proxies that gave a clear answer through – 53 % of datacenter exits, 40 % of the other exits.

In the last run Instagram let 42 % of the 170 HTTPS-capable proxies that gave a clear answer through – 32 % of datacenter exits, 54 % of the other exits.

In the last run TikTok let 31 % of the 143 HTTPS-capable proxies that gave a clear answer through – 47 % of datacenter exits, 13 % of the other exits.

In the last run Discord let 94 % of the 151 HTTPS-capable proxies that gave a clear answer through – 98 % of datacenter exits, 90 % of the other exits.

Between 446 and 1,225 entries were on the list at any one time. Right now: 583, 49 % of them tunnel HTTPS to the test host, 32 % are datacenter exits (the provider name looks like a hosting company).

Downloading 100 KB through the HTTPS-capable ones, counting the downloads that finished: half manage 75 KiB/s or more, the fastest tenth over 127 KiB/s.

Most exit IPs are in United States (112), China (33), Indonesia (33), Russia (32), ZW (27).

![How long free proxies last](https://proxy-scraper.de/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://proxy-scraper.de/
Raw data (JSON, CSV, TXT): https://proxy-scraper.de/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
