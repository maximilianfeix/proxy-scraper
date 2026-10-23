# FAQ

← [README](../README.md) · [All docs](README.md)

<a id="who-runs-free-proxies"></a>

<details open>
<summary><b>Who runs free proxies – and should you use them?</b></summary>
<br>

Almost nobody runs a free proxy for you. What ends up on public lists is usually one of these:

- **Misconfigured servers** – a Squid, a router or an app with a proxy port that was meant to stay internal.
- **Deliberately open proxies** – a few volunteers and research projects, and services that give some away to sell the rest.
- **Infected machines** – computers and IoT devices whose owners don't know they relay traffic. Many residential exits are like this.
- **Traps** – honeypots that log what goes through them, and proxies that rewrite pages to inject ads or scripts.

That is general background, not something this project measured: a check can't see who runs a proxy or why.

proxy-scraper can't tell an infected home router from an open office proxy, but it filters what it can measure: a proxy has to answer two independent requests with the same exit IP, deliver a known page byte for byte, and HTTPS counts only with a certificate that verifies for the test host. Each hit says whether its exit is in a datacenter.

Good uses: public data, checking how a site looks from another country, testing your own blocking and rate limits, research. Never send passwords, cookies, payment or personal data through a free proxy, and keep HTTPS certificate checks on. Use them only where you're allowed to.

</details>

<details>
<summary><b>Almost nothing gets through.</b></summary>
<br>

Many company, school and university networks block proxy connections. The tool notices a hit rate below 0.2 % and warns you – a different network such as a phone hotspot helps. The learned statistics are not downgraded in such a run.

</details>

<details>
<summary><b>Does it work on Windows?</b></summary>
<br>

Yes, in PowerShell and Windows Terminal. `uvloop` doesn't exist there and is skipped automatically. In the old `cmd.exe` window some symbols may be missing depending on the font.

</details>

<details>
<summary><b>Why does it find fewer proxies than other lists claim to have?</b></summary>
<br>

Because only proxies that pass every check are kept: two independent requests that show the same foreign exit IP, and a test page that arrives unchanged. In the hourly runs that is about 1 % of the 150,000 candidates checked. They passed from the network that checked them, at that moment.

</details>

<details>
<summary><b>What about proxies with a username and password?</b></summary>
<br>

Lines like `socks5://user:pass@1.2.3.4:1080` keep their login: HTTP proxies get a `Proxy-Authorization` header, SOCKS5 uses username/password auth (RFC 1929), SOCKS4 the user ID. The same works for `--recheck` with your own list. The result files keep the credentials, the terminal only shows `user:•••`.

</details>

<details>
<summary><b>How fresh is the live list?</b></summary>
<br>

It's rebuilt about every hour; the “updated” badge shows the last run. Free proxies come and go quickly, so for anything important run `proxy-scraper --recheck` right before use.

</details>

<details>
<summary><b>Is it safe to use free proxies?</b></summary>
<br>

Only for things that don't matter. Public proxies are run by strangers who can read everything that isn't encrypted. Never send passwords or personal data through them, and only use them for legal purposes.

</details>
