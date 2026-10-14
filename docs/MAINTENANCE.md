# Maintenance log

A short, current record of maintenance work: what was verified, what is open, what comes next. Check it against
GitHub (PRs, issues, releases, CI) before relying on it – it describes the state when it was last written.

_Last updated: 2026-10-14_

## Baseline (2026-10-14, before the changes below)

- `main` at `413e07b` (release 1.28.0), latest tag `v1.28.0`
- Tests: 1072 passed, 1 failed (`test_finds_add_up_and_old_ones_expire`, a clock-dependent test – fixed in #327), 10 skipped; ruff clean
- CI: all workflows SHA-pinned, least-privilege permissions, no `pull_request_target`; releases Sigstore-signed, PyPI via trusted publishing
- OpenSSF Scorecard 6.8 (Pinned-Dependencies 6, Signed-Releases 3; Code-Review, Maintained, Contributors are structural for a young solo project)
- Open then: PR #311 (changes requested), 9 issues (5 translation/onboarding, distribution plan #316, Scorecard #273, Java/Rust quick start #269, sources #231)

## Done

| PR | What | Why |
|---|---|---|
| #327 | Discovery expiry test passes `now=` | It compared a fixed date with the real clock and failed on every run since 2026-10-12 |
| #328 | `--serve-host` off loopback needs a password or `--serve-open` | Was only a warning: `docker run -p 8899:8899 … --serve-host 0.0.0.0` was an open proxy (Docker bypasses ufw). Refused before the scan, exit code 2 |
| #329 | `--require-hashes` on locked installs, base image pinned by digest + Dependabot `docker`, `mcp-publisher` sha256-checked | Scorecard Pinned-Dependencies; the publisher ran unchecked in a job with an OIDC token |
| #311 | Closed with data | `?protocol=all` duplicates rcloak's per-protocol endpoints, which already come in through the gfpcom meta lists (583 k listed, 129 k checked, 1,271 working = 1.0 % in the hourly runs). 58.6 MB / 2.2 M lines per download for nothing new |
| #330 | Release 1.29.0 | Verified after publication: GitHub release with Sigstore bundles, PyPI (clean install reports 1.29.0), MCP registry, GHCR `1.29.0` / `1.29` / `latest` (amd64 + arm64), `v1` moved. Homebrew follows automatically once the release is 25 h old |

## Audit notes

**Rotating server (`server/core.py`).** Loopback by default; request head limited (64 KiB, timeout); hostname validation; 407/401 handling; SOCKS4 upstreams resolve names only to public addresses (`public_targets_only`) in the MCP fetcher; plain-HTTP relays forward exactly one request body, so a second keep-alive request with its credentials never reaches a free proxy. Not done yet: no cap on concurrent client connections and no idle timeout inside an established tunnel (only relevant for long-lived clients on an exposed server; unauthenticated clients are bounded by the head timeout).

**MCP (`mcp_server.py`, `agent.py`).** `fetch_url` accepts only http(s), no credentials in URLs, validates IP literals (including IPv4-mapped IPv6 and `inet_aton` forms such as `0x7f.1`), resolves names and refuses private or reserved results, re-checks every redirect hop, refuses https→http downgrades, caps the body (`MAX_PAGE_BYTES`) and the redirect count. Traffic leaves through remote proxies, never directly from this machine. No confirmed SSRF.

**Source ingestion (`netio.py`, `pipeline.py`).** `Accept-Encoding: identity` (no decompression bombs), 64 MiB cap per response, per-request timeout, bounded download concurrency, parsing of large lists in a process pool. Measured from `sources.json` (298 sources): median 506 proxies per list, p95 ≈ 52 k, p99 ≈ 235 k, the largest single list ≈ 330 k entries (≈ 10 MB). The 64 MiB cap is about 6× the largest real source, so it never cuts one off; a lower default (16 MiB) would still cover every current source and cap a rogue one at a quarter of the memory.

## Backlog (prioritized)

1. One unexplained single test failure in ~10 local full-suite runs (another one was caused by editing files during a run) – watch CI for a recurrence before assuming it's real
2. Rotating server: bounded concurrent connections (graceful queueing instead of fd exhaustion) and an optional idle timeout for tunnels – needs a local load reproduction first
3. Per-source download budget: lower the 64 MiB cap to ~16 MiB (see the measurement above) and count truncated sources in the statistics instead of parsing a cut-off file silently
4. Checker: a local fake-proxy harness for content injection, wrong exit IPs, partial responses and protocol mismatches, documenting what each stage proves
5. Source ranking: compare the current score with a decayed / Bayesian estimate on the published history before changing anything
6. Scorecard: CII Best Practices registration (#273) – a form, not code

## Decisions

- Password-less non-loopback servers are an explicit opt-in (`--serve-open`), not a warning – minor version bump, documented under *Security*
- PR #311 was closed for redundancy with measurements, not for inactivity
- Translations (#322–#325, #294): machine translations are not presented as native review; those issues stay open for contributors

## Releases

- Last verified release: **v1.29.0** (2026-10-14) – all artifacts checked, see #330 above
- Scorecard after #329: 6.9 (Pinned-Dependencies 6 → 9); Signed-Releases rises as signed releases accumulate
