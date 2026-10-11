# Security policy

## Supported versions

Only the latest release gets fixes. Please update before reporting.

## Reporting a vulnerability

Please **don't open a public issue**. Use [private vulnerability reporting](https://github.com/maximilianfeix/proxy-scraper/security/advisories/new) instead. You'll get an answer within a few days.

Helpful to include: the version (`proxy-scraper --version`), the command, and what an attacker could do.

## Scope

Things that count as a vulnerability here, for example:

- the rotating proxy server (`--serve`) being reachable from outside `127.0.0.1`
- a proxy being able to break or bypass the TLS verification of the HTTPS test or of `--serve`
- crafted source lists or proxy answers that lead to code execution, path traversal or writing outside the results and data folders

Not a vulnerability: public proxies reading unencrypted traffic. That's how they work – never send sensitive data through them.

## Verifying a release

Every [release](https://github.com/maximilianfeix/proxy-scraper/releases/latest) ships the wheel and sdist together with a Sigstore bundle (`*.sigstore.json`), signed keylessly by the release workflow of this repository. To check that a file really came from it:

```bash
pipx install sigstore
sigstore verify github proxy_scraper_cli-1.27.0-py3-none-any.whl \
  --bundle proxy_scraper_cli-1.27.0-py3-none-any.whl.sigstore.json \
  --repository maximilianfeix/proxy-scraper
```

Workflows pin every action by commit SHA, install Python packages by hash, run CodeQL on every push and the [OpenSSF Scorecard](https://scorecard.dev/viewer/?uri=github.com/maximilianfeix/proxy-scraper) weekly. `main` is protected against force pushes and deletion.
