# Proxy Scraper for GitHub Actions

Get HTTP, SOCKS4 and SOCKS5 proxies from the list checked every hour. The action works on GitHub-hosted Linux, macOS and Windows runners. It does not require an API key or a checkout of your repository.

## Quick start

```yaml
name: Proxy example
on: workflow_dispatch

permissions:
  contents: read

jobs:
  example:
    runs-on: ubuntu-latest
    steps:
      - name: Get proxies
        id: proxies
        uses: maximilianfeix/proxy-scraper@v1.27.1
        with:
          types: socks5
          https: "true"
          limit: "5"
          recheck: "true"
      - name: Use the first proxy
        env:
          PROXY_URL: ${{ steps.proxies.outputs.proxy }}
        run: curl --fail --max-time 30 --proxy "$PROXY_URL" https://api.ipify.org
```

Use `@v1` for the latest compatible release, a version tag for a specific release, or a full commit SHA for an immutable reference.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `types` | `http,socks4,socks5` | Comma-separated proxy protocols. |
| `countries` | Empty | Two-letter country codes, e.g. `DE,NL`; empty accepts any country. |
| `https` | `false` | Require HTTPS tunneling with verified TLS. |
| `min-uptime` | `0` | Minimum percentage of the week's hourly checks in which the proxy was listed. |
| `min-speed` | `0` | Minimum measured download speed in KB/s; measured for HTTPS-capable proxies. |
| `works-on` | Empty | Comma-separated sites: `google,reddit,amazon,instagram,tiktok,discord`. |
| `limit` | `20` | Maximum number of results; `0` returns all matches. |
| `recheck` | `false` | Check matches again from the current runner before returning them. |
| `fail-if-empty` | `true` | Fail when no proxy matches; use `false` to handle an empty result yourself. |

Restrictive filters can return no matches. Start with protocol and HTTPS requirements, then add country, uptime or site filters as needed. The action selects proxies from the published list; it does not run a full source scrape in each workflow.

## Outputs

| Output | Meaning |
|---|---|
| `proxy` | First ranked proxy URL, e.g. `socks5://1.2.3.4:1080`; empty if there are no matches. |
| `file` | Absolute path to a runner-local UTF-8 text file, one proxy URL per line. |
| `count` | Number of returned proxies. |

Each invocation produces its own output file. A recheck preserves the live list's ranking and applies `limit` after checking. With `fail-if-empty: "false"`, guard later steps with `if: steps.proxies.outputs.count != '0'`.

On self-hosted runners, provide Python 3.9 or newer with `venv` and `pip`, plus Bash. Installation needs access to PyPI and proxy selection needs access to the public live list. Public proxies can stop working between checks; `recheck` verifies them from your runner before use.

## Publishing a Marketplace update

The tagged release must include `action.yml` at the repository root. Keep the action description below 125 characters and retain the Marketplace action name. After the release workflow finishes, edit that release on GitHub, select **Publish this Action to the GitHub Marketplace**, choose the categories and save. Confirm the version on the public Marketplace page; creating a release through the API alone does not select this checkbox.
