# Maintenance log

A short, current record of maintenance work: what was verified, what is open, what comes next. Check it against
GitHub (PRs, issues, releases, CI) before relying on it – it describes the state when it was last written.

_Last updated: 2026-10-14_

## Baseline (2026-10-14, before the changes below)

- `main` at `413e07b` (release 1.28.0), latest tag `v1.28.0`
- Tests: 1072 passed, 1 failed (`test_finds_add_up_and_old_ones_expire`, a clock-dependent test – fixed in #327), 10 skipped; ruff clean
- CI: all workflows SHA-pinned, least-privilege permissions, no `pull_request_target`; releases Sigstore-signed, PyPI via trusted publishing
- OpenSSF Scorecard 6.8 (Pinned-Dependencies 6, Signed-Releases 3; Code-Review, Maintained, Contributors are structural for a young solo project)
- Open: PR #311 (changes requested), 9 issues (5 translation/onboarding, distribution plan #316, Scorecard #273, Java/Rust quick start #269, sources #231)

## Done

| PR | What | Why |
|---|---|---|
| #327 | Discovery expiry test passes `now=` | It compared a fixed date with the real clock and failed on every run since 2026-10-12 |
| #328 | `--serve-host` off loopback needs a password or `--serve-open` | Was only a warning: `docker run -p 8899:8899 … --serve-host 0.0.0.0` was an open proxy (Docker bypasses ufw). Refused before the scan, exit code 2 |
| #329 | `--require-hashes` on locked installs, base image pinned by digest + Dependabot `docker`, `mcp-publisher` sha256-checked | Scorecard Pinned-Dependencies; the publisher ran unchecked in a job with an OIDC token |
| #311 | Measured, commented, left open | 58.6 MB / 2.2 M lines, 583 k unique entries, 77 % of the verified pool already covered by existing sources; the review's path to acceptance still stands |

## Audit notes

**Rotating server (`server/core.py`).** Loopback by default; request head limited (64 KiB, timeout); hostname validation; 407/401 handling; SOCKS4 upstreams resolve names only to public addresses (`public_targets_only`) in the MCP fetcher; plain-HTTP relays forward exactly one request body, so a second keep-alive request with its credentials never reaches a free proxy. Not done yet: no cap on concurrent client connections and no idle timeout inside an established tunnel (only relevant for long-lived clients on an exposed server; unauthenticated clients are bounded by the head timeout).

**MCP (`mcp_server.py`, `agent.py`).** `fetch_url` accepts only http(s), no credentials in URLs, validates IP literals (including IPv4-mapped IPv6 and `inet_aton` forms such as `0x7f.1`), resolves names and refuses private or reserved results, re-checks every redirect hop, refuses https→http downgrades, caps the body (`MAX_PAGE_BYTES`) and the redirect count. Traffic leaves through remote proxies, never directly from this machine. No confirmed SSRF.

**Source ingestion (`netio.py`, `pipeline.py`).** `Accept-Encoding: identity` (no decompression bombs), 64 MiB cap per response, per-request timeout, bounded download concurrency, parsing of large lists in a process pool. Possible improvement: a lower, configurable per-source budget – the largest legitimate sources need to be measured first.

## Backlog (prioritized)

1. A test that failed once in ~8 local full-suite runs and could not be reproduced – identify it (CI history, repeated runs) before it hides a real failure
2. Rotating server: bounded concurrent connections (graceful queueing instead of fd exhaustion) and an optional idle timeout for tunnels – needs a local load reproduction first
3. Per-source download budget: measure the size distribution of the 700+ sources, then decide on a lower default than 64 MiB
4. Checker: a local fake-proxy harness for content injection, wrong exit IPs, partial responses and protocol mismatches, documenting what each stage proves
5. Source ranking: compare the current score with a decayed / Bayesian estimate on the published history before changing anything
6. Scorecard: CII Best Practices registration (#273) – a form, not code

## Decisions

- Password-less non-loopback servers are an explicit opt-in (`--serve-open`), not a warning – minor version bump, documented under *Security*
- PR #311 is not closed for inactivity; it stays open while the path to acceptance exists
- Translations (#322–#325, #294): machine translations are not presented as native review; those issues stay open for contributors

## Releases

- Last verified release: v1.28.0 (2026-10-11); v1.29.0 is tagged from the release PR that adds this file (#328, #329)
