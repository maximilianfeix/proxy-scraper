# Python API: rotating through the list

← [README](../README.md) · [All docs](README.md)

`find_proxies`, `check_proxies` and `live_proxies` are in the [README](../README.md#from-python).

Or let the library do the retrying: `ProxyRotator` loads a URL through the list and moves on to the next proxy when one fails – HTTPS only through proxies with verified TLS.

```python
from proxyscraper import ProxyRotator

with ProxyRotator(country="DE") as rotator:
    r = rotator.get("https://httpbin.org/ip")
    print(r.status, r.text, "via", r.via)
```

Usually a few seconds; when many proxies in a row are down it can take a minute (`timeout=` is per attempt). There's `aget()` with `async with` for asyncio code.

Already using requests, httpx, Playwright or Scrapy? `proxy_url()` gives you one local proxy address that rotates behind the scenes – every connection goes out through another proxy from the list, best first, dead ones skipped:

```python
import requests
from proxyscraper import ProxyRotator

with ProxyRotator(country="DE") as rotator:
    proxy = rotator.proxy_url()          # http://country-de:…@127.0.0.1:…
    requests.get("https://api.ipify.org", proxies={"http": proxy, "https": proxy})
    # httpx.Client(proxy=proxy) · scrapy: meta={"proxy": proxy} · curl -x "$proxy"
    # Playwright wants the login apart: chromium.launch(proxy=rotator.playwright_proxy())
```

It runs on 127.0.0.1 with a random password, takes over each new hourly list by itself and stops with the `with` block.

Closing is final: `close()` / `aclose()` may be called more than once, a call still running in another thread ends with a `RuntimeError`, and using a closed rotator raises `RuntimeError` – make a new one instead.
