# Check states

Every check of a proxy ends in one of four states. They are in `proxies.json`, in the CSV, in `--pick --json`, in `--diagnose`, in the Python API (`result.checks`) and in the MCP results.

| State | Meaning |
|---|---|
| `passed` | The check ran and the proxy did what was asked. |
| `failed` | The check ran, its target was fine, and the proxy did not do what was asked. |
| `unavailable` | The check could not run, or says nothing about the proxy: its target didn't answer directly either, there was no reference to compare with, or this machine ran out of sockets. |
| `skipped` | Left out on purpose: `--fast`, a filter had already ruled the proxy out, or an earlier check failed. |

Two rules follow from that:

- **A check that didn't run is never `passed`.** Before 1.29, a run without a reachable second target kept every proxy as if it had been confirmed, and a missing reference page looked like "content unchanged".
- **A check target that is down doesn't fail the proxies checked against it.** When a second request or an HTTPS test fails, the tool asks the target directly (at most once every 10 seconds, however many proxies fail in between). If the target doesn't answer, the proxy's check is `unavailable`, not `failed`.

## The checks

| Name | What runs | `passed` means | It does not mean |
|---|---|---|---|
| `basic` | Handshake (HTTP, SOCKS4 or SOCKS5) and a first request to a check target that returns the caller's IP | The proxy returned a public exit IP that isn't yours | That it will answer the next request |
| `confirm` | A second request to an unrelated site (httpbin.org) | That site saw the same exit IP; the headers it received give the anonymity level | That the proxy is "safe" or that nobody logs the traffic |
| `content` | A static test page over plain HTTP, compared with its hash as fetched directly | The page arrived byte for byte | That other pages arrive unchanged, or that HTTPS pages are handled the same way |
| `https` | A tunnel to the check target on port 443 with a TLS handshake that verifies | A verified TLS connection to that one host worked through the proxy at that time | Anything about other sites, later connections or who runs the proxy. What protects an `https://` page is your own client checking certificates – leave that on |

A failed check is a measurement, not a verdict about the operator. `exit_ip_mismatch` can be a rotating pool or a proxy that fakes the first answer. `content_mismatch` can be an injected script, an ad, a portal page or a copy that was cut off. The check doesn't tell which, and every such result says so in its `limits`.

## What a check looks like

```json
"checked_at": "2026-10-13T18:02:11+00:00",
"checks": {
  "basic":   {"state": "passed", "target": "checkip.amazonaws.com:80", "at": "2026-10-13T18:02:11+00:00", "ms": 412,
              "data": {"exit_ip": "203.0.113.20"}},
  "confirm": {"state": "passed", "target": "httpbin.org:80", "at": "2026-10-13T18:02:12+00:00", "ms": 655,
              "data": {"exit_ip": "203.0.113.20", "anonymity": "elite"}},
  "content": {"state": "passed", "target": "httpbin.org:80/html", "at": "2026-10-13T18:02:12+00:00", "ms": 590,
              "data": {"bytes": 3741}},
  "https":   {"state": "failed", "reason": "tunnel_refused", "target": "checkip.amazonaws.com:443",
              "at": "2026-10-13T18:02:13+00:00", "ms": 301}
}
```

| Field | |
|---|---|
| `state` | always there |
| `reason` | a code from the table below; absent for `passed` |
| `target` | what was contacted through the proxy |
| `at` | when the check finished, ISO 8601 in UTC. `checked_at` on the proxy is the time of its basic check |
| `ms` | how long it took |
| `data` | what was measured: exit IPs, anonymity, sizes; for a changed page its size, the first 16 hex digits of its SHA-256 and how many `<script` tags it contains |
| `limits` | what the result does not say |

A check that is missing from `checks` never got that far.

## Reason codes

| Code | State | Meaning |
|---|---|---|
| `connect_timeout` | failed | no TCP connection to the proxy within the time limit |
| `connect_refused` | failed | the proxy's port refused the connection |
| `connect_failed` | failed | the proxy's address could not be reached |
| `known_unreachable` | failed | this address already failed to connect earlier in the same run |
| `handshake_refused` | failed | the proxy answered, but refused the handshake or the connection to the target |
| `timeout` | failed | the proxy accepted the connection but did not answer in time |
| `connection_closed` | failed | the proxy closed the connection before a complete answer |
| `connection_error` | failed | the connection through the proxy broke |
| `bad_status` | failed | the answer through the proxy was not an HTTP 200 |
| `invalid_response` | failed | the answer was not what the target sends |
| `private_exit_ip` | failed | the exit IP is a private or reserved address – the proxy answered by itself |
| `own_ip_exposed` | failed | the target saw this machine's own IP |
| `exit_ip_mismatch` | failed | the second site saw a different exit IP than the first |
| `content_mismatch` | failed | the static test page arrived with different bytes than the reference |
| `tunnel_refused` | failed | the proxy did not open a tunnel to the HTTPS target |
| `tls_certificate_invalid` | failed | the certificate inside the tunnel did not verify |
| `tls_error` | failed | the TLS handshake inside the tunnel failed |
| `target_not_configured` | unavailable | the check target did not answer when the run started, so the check never ran |
| `target_unreachable` | unavailable | the check target did not answer directly either while this was checked |
| `no_reference` | unavailable | there was no reference page to compare with |
| `local_resource_limit` | unavailable | this machine ran out of sockets or file descriptors |
| `fast_mode` | skipped | left out with `--fast` |
| `filtered_out` | skipped | a filter had already ruled this proxy out |
| `earlier_check_failed` | skipped | an earlier check did not pass (in `--diagnose` and `--pick --verify` output) |

For the content check, a timeout or an error page is `unavailable` with the connection's reason code: no page came back, so nothing was compared.

## What a list requires

| Where | `basic` | `confirm` | `content` | `https` |
|---|---|---|---|---|
| Your own run: `results/…/all.txt`, `proxies.json` | passed | passed **or unavailable** | passed **or unavailable** | any |
| `--https-only`, `https.txt` of the hourly list | passed | as above / passed | as above / passed | **passed** |
| The hourly list: `all.txt`, `http.txt`, `socks4.txt`, `socks5.txt`, `elite.txt`, `stable.txt` | passed | **passed** | **passed** | any |
| `--pick N --verify` | passed | **passed** | **passed** | passed with `--https-only` |

Your own run keeps a proxy whose second request could not run, because the alternative is an empty result whenever httpbin.org has a bad minute. It tells you: a note at the end of the run, and `unavailable` in the files. Filter on `checks.confirm.state` if you need more.

The published list is stricter. Only measured passes are listed, `stats.json` says so in `requires`, and `held_back` counts the hits that lacked one. A run whose second target was down publishes too few entries, and then nothing: the previous list stays online and its `updated` time shows its age.

## What a run records

Every run writes `run.json` next to its results, and the hourly list publishes it:

```json
{"schema": 1, "version": "1.29.0", "started": "…", "finished": "…",
 "targets": {"basic": "checkip.amazonaws.com", "basic_switches": [], "confirm": "httpbin.org", "content_reference": true},
 "candidates": 150000, "checked": 149212, "not_checked": 788, "stopped": null, "working": 1104, "kept": 1104,
 "checks": {"basic": {"passed": 2391, "failed:connect_timeout": 101220, "failed:connect_refused": 30122},
            "confirm": {"passed": 1161, "failed:bad_status": 702, "failed:exit_ip_mismatch": 311},
            "content": {"passed": 1104, "failed:content_mismatch": 57},
            "https": {"passed": 706, "failed:tunnel_refused": 398}}}
```

The numbers in this example are made up to show the shape. `candidates` are the proxies the run set out to check, `checked` the ones that got a verdict, `not_checked` the rest (stopped by `--want` or Ctrl+C). `basic` counts attempts: a proxy that is checked again after a check target switch counts once per try.

## For code that reads the old fields

Nothing was renamed or removed. `https` is still `true`, `false` or `null`, and `anonymity` still a string. Two values changed meaning, both towards saying less:

- `https` is `null` when the HTTPS test could not run (its target was down, or this machine ran out of sockets). It used to be `false`.
- `anonymity` is `""` for a proxy whose second request could not run. That was already the case; now `checks.confirm.state` tells you why.

`proxies.csv` has five new columns, all at the end so the old ones keep their position: `checked_at`, then `check_basic`, `check_confirm`, `check_content` and `check_https` with values like `passed` or `unavailable:target_unreachable`.

Lists published before 1.29 have neither `checks` nor `checked_at`. Readers treat that as "not recorded", not as passed.

## Exit codes of the commands that check a few proxies

| Command | 0 | 1 | 3 | 2 | 130 |
|---|---|---|---|---|---|
| `--pick N` | at least one proxy matched | none matched, or the list could not be loaded | – | bad arguments | – |
| `--pick N --verify` | N proxies passed | none passed, or nothing could be checked | fewer than N passed (they are printed) | bad arguments | interrupted, nothing printed |
| `--diagnose PROXY` | reached and nothing failed | a check failed | nothing failed, but a check was `unavailable` | not a proxy | interrupted |

`--pick --verify` tries 5 candidates per proxy asked for (at least 10, at most 60), up to 8 at a time (twice the number asked for, if that is less), and stops checking after 90 seconds. Loading the list and asking the check targets directly comes before that and takes a few seconds more. Among the proxies that passed, the ones higher on the list are printed. A proxy that passes was checked seconds ago from your network against the targets above. That is all it promises.
