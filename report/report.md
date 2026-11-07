# The week in free proxies: Oct 31 – Nov 07, 2026

About every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and
SOCKS5 proxies from 700+ lists, checks 150,000 of the candidates and keeps only the ones that pass a basic check, a
second request to another site and a content check. This is what 168 of those runs looked like. An entry
that is not on the list was not necessarily measured as failing.

20,371 different type://ip:port entries passed every check at least once (many are ports on the same host). Of the 19,923 that left the list again, 90 % were not on the next list, and 18 (under 0.1 %) had been on it for 24 runs in a row (about a day) or more. 33 proxies on the list right now have been on it for 24 runs in a row or more.

In the last run Google let 37 % of the 130 HTTPS-capable proxies that gave a clear answer through – 32 % of datacenter exits, 42 % of the other exits.

In the last run Reddit let 44 % of the 135 HTTPS-capable proxies that gave a clear answer through – 25 % of datacenter exits, 65 % of the other exits.

In the last run Amazon let 19 % of the 144 HTTPS-capable proxies that gave a clear answer through – 14 % of datacenter exits, 25 % of the other exits.

In the last run Instagram let 17 % of the 143 HTTPS-capable proxies that gave a clear answer through – 12 % of datacenter exits, 23 % of the other exits.

In the last run TikTok let 66 % of the 127 HTTPS-capable proxies that gave a clear answer through – 81 % of datacenter exits, 50 % of the other exits.

In the last run Discord let 100 % of the 135 HTTPS-capable proxies that gave a clear answer through – 100 % of datacenter exits, 100 % of the other exits.

Between 270 and 1,879 entries were on the list at any one time. Right now: 340, 55 % of them tunnel HTTPS to the test host, 42 % are datacenter exits (the provider name looks like a hosting company).

Downloading 100 KB through the HTTPS-capable ones, counting the downloads that finished: half manage 91 KiB/s or more, the fastest tenth over 132 KiB/s.

Most exit IPs are in United States (97), Romania (37), Hong Kong (22), Indonesia (17), Germany (15).

![How long free proxies last](https://proxy-scraper.de/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://proxy-scraper.de/
Raw data (JSON, CSV, TXT): https://proxy-scraper.de/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
