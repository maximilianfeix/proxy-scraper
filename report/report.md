# The week in free proxies: Sep 26 – Oct 03, 2026

Every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and SOCKS5
proxies from 700+ lists and keeps only the ones that pass a real handshake, a honeypot check and a content check.
This is what 179 of those runs looked like.

49,370 different proxies passed every check at least once. Of the 47,206 that dropped off again, 87 % were gone by the next check, and only 29 (under 0.1 %) made it through 24 checks in a row (about a day) or more. 120 proxies on the list right now have been up for 24 checks in a row or more.

Google let 55 % through – 48 % of datacenter exits, 81 % of the rest.

Reddit let 21 % through – 7 % of datacenter exits, 79 % of the rest.

Amazon let 28 % through – 21 % of datacenter exits, 57 % of the rest.

Instagram let 20 % through – 7 % of datacenter exits, 75 % of the rest.

TikTok let 95 % through – 97 % of datacenter exits, 89 % of the rest.

Between 739 and 4,223 proxies worked at any one time. Right now: 2,164, 65 % of them tunnel HTTPS, 71 % exit from a datacenter.

Downloading 100 KB through them: half manage 75 KiB/s or more, the fastest tenth over 127 KiB/s.

Most of them sit in United States (922), Germany (161), Israel (135), India (109), Australia (98).

![How long free proxies last](https://maximilianfeix.github.io/proxy-scraper/report/lifetimes-light.svg)

The list, filters and a page per proxy: https://maximilianfeix.github.io/proxy-scraper/
Raw data (JSON, CSV, TXT): https://maximilianfeix.github.io/proxy-scraper/proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
