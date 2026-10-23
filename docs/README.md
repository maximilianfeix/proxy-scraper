# proxy-scraper documentation

← [README](../README.md)

The [README](../README.md) gets you from install to a first working command. These pages have the rest, in the order you are likely to need them:

1. [Install: every other way](install.md) – Docker, pip, a faster event loop, the latest main, tab completion, where state and results are stored
2. [Check states](check-states.md) – the four states every check ends in, the checks, reason codes
3. [Recipes](recipes.md) – requests, httpx, aiohttp, Scrapy, Selenium, proxychains, Clash, sing-box, PAC, Proxifier, Burp/ZAP/mitmproxy, pipes, your own lists, GitHub workflows
4. [Python API: rotating through the list](python.md) – `ProxyRotator` and `proxy_url()`
5. [Rotating proxy server](proxy-server.md) – rotation options, behaviour, live dashboard, proxy pool API
6. [Options and output](options.md) – every command-line option, the wizard presets, the result folder
7. [How it works](how-it-works.md) – the checks step by step, features, GitHub Actions, project structure
8. [GitHub Action](github-action.md) – inputs and outputs of `maximilianfeix/proxy-scraper@v1`
9. [FAQ](faq.md) – who runs free proxies, networks that block them, Windows, logins, freshness
10. [Roadmap and what shipped](roadmap.md)

Background:

- [Free proxies in numbers](free-proxies-in-numbers.md) – what the numbers show and what they don't
- [Why free proxies fail](why-free-proxies-fail.md)
- [How it compares](comparison.md)
- [Architecture](ARCHITECTURE.md) – how the pieces fit together, for contributors
- [Maintenance log](MAINTENANCE.md)
