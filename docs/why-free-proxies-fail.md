# Free proxies rarely fake their exit IP: 19.8 million checks

_Measured 2026-10-16 21:30 UTC to 2026-10-22 08:45 UTC · 132 published hourly runs · reproduce with
[`docs/analysis/history_checks.py`](analysis/history_checks.py)_

There is a story people tell about free proxy lists, and I told it too. It goes: a lot of what
answers you is bait. A scanner connects, asks "what is my IP", gets a plausible answer, and marks
the proxy as working — but the thing on the other end only ever answers that one question. Ask it
for anything else and it is gone.

I wrote that in September, in an article about my own tool, and I had no evidence for it. In
[the audit of my own numbers](free-proxies-in-numbers.md) I withdrew it: a proxy failing a second
request is a measurement, and "honeypot" is a motive. The measurement cannot see motive.

Since release 1.30.0 every published run records what each check ended as, with a reason code. One
hundred and thirty-two runs have now accumulated, and the question is answerable for the first
time. The answer is not the story.

## The four checks and their denominators

A candidate goes through up to four checks, and each one only runs if the previous one passed. So
every percentage below is a share of its own step, and the step is named. These are counts of
**checks**, not of distinct machines: the most promising candidates go first every hour, so the
same address is re-checked in run after run.

| Step | What has to happen | Checks in this window | Passed |
|---|---|---:|---:|
| `basic` | handshake, then a first request returning a public exit IP | 19,800,000 | 435,244 (2.2 %) |
| `confirm` | a second request to an unrelated site shows the same exit IP | 435,244 | 269,067 (61.8 %) |
| `content` | a known static page arrives byte for byte | 269,453 | 186,483 (69.2 %) |
| `https` | a CONNECT tunnel, and TLS that verifies for the test host | 255,565 | 139,548 (54.6 %) |

## The second request

This is the step the honeypot story is about. Of the 435,244 proxies that answered a first request
and returned a public exit IP:

| Outcome of the second request | Checks | Share of this step |
|---|---:|---:|
| passed | 269,067 | 61.82 % |
| `failed:timeout` | 61,975 | 14.24 % |
| `failed:connect_timeout` | 59,427 | 13.65 % |
| `failed:bad_status` | 21,402 | 4.92 % |
| `failed:connection_closed` | 10,104 | 2.32 % |
| **`failed:exit_ip_mismatch`** | **7,860** | **1.81 %** |
| `failed:invalid_response` | 1,990 | 0.46 % |
| `failed:connect_refused` | 1,566 | 0.36 % |
| `failed:handshake_refused` | 1,459 | 0.34 % |
| `unavailable:target_unreachable` | 386 | 0.09 % |

**A different exit IP on the second request is 1.81 % of this step.** Per run it is a median
1.79 %, between 0.83 % and 3.69 %. Timeouts alone — the proxy simply not answering a second time —
are 27.9 %, fifteen times as much.

That is the finding. The second request is worth making, and it removes 38 % of what a
one-request checker would hand you. But what it removes is overwhelmingly a proxy that cannot
answer twice, not one that answers differently the second time. And even those 1.81 % are not
caught lying: a rotating exit pool produces exactly the same measurement, which is why the reason
code is called `exit_ip_mismatch` and not something with an opinion in it.

## What the first step spends its time on

| Outcome | Checks | Share |
|---|---:|---:|
| `failed:connect_timeout` | 8,074,966 | 40.78 % |
| `failed:known_unreachable` | 3,620,314 | 18.28 % |
| `failed:connect_refused` | 2,883,766 | 14.56 % |
| `failed:bad_status` | 2,114,837 | 10.68 % |
| `failed:timeout` | 1,366,944 | 6.90 % |
| `failed:handshake_refused` | 626,120 | 3.16 % |
| `failed:connection_closed` | 463,551 | 2.34 % |
| passed | 435,244 | 2.20 % |
| `failed:own_ip_exposed` | 106,396 | 0.54 % |
| `failed:invalid_response` | 105,960 | 0.54 % |
| `failed:private_exit_ip` | 1,652 | 0.01 % |

Two of these are worth a sentence.

`known_unreachable` is 18.28 % — nearly a fifth of all work. That is an address this run had
already found unreachable on another protocol, so the remaining protocols were not tried again. A
candidate is a protocol *and* an address, and the public lists hand you the same address as
"http", "socks4" and "socks5" entries. Roughly a fifth of a big aggregated candidate pool is the
same machines counted again.

`own_ip_exposed` is 0.54 % — 106,396 checks where the proxy forwarded the request and the exit IP
that came back was the checking machine's own. Those are not proxies in any useful sense.

## The step that used to be invisible

The content check is where the honest bookkeeping shows up most clearly:

| Outcome | Checks | Share |
|---|---:|---:|
| passed | 186,483 | 69.21 % |
| `unavailable:*` (page never arrived) | 69,082 | **25.64 %** |
| `failed:content_mismatch` | 13,888 | 5.15 % |

A quarter of the content checks could not be measured at all — the test page did not arrive, so
there is nothing to compare. Before 1.30.0 a request that timed out or came back as an error page
counted as "page unchanged", which meant it passed, which meant the proxy was published. Those
69,082 checks are the size of that old bug, and they are the reason the published list is now
smaller than it used to be. The publisher states the cost per run: in the list of 2026-10-22
08:45 UTC, 1,111 entries were published and **527 were held back** because a required check had
not actually been measured (`held_back` in `stats.json`, next to a `requires` map that says which
checks each file demands).

The 5.15 % that did arrive changed is a measurement of bytes, nothing more. A truncated response
changes the bytes too. I keep no sample of those pages, so I cannot tell you what was in them.

## TLS

Of the 255,565 checks that reached the HTTPS step, 143,392 got far enough for a TLS handshake to
happen at all. **3,823 of those — 2.67 %, about one in 38 — presented a certificate that did not
verify for the test host.** The rest of the step is timeouts (32.66 %) and proxies that refuse to
open a tunnel (7.40 %). On today's published list, 23 of 1,111 entries carry
`https: failed:tls_certificate_invalid`. Again: that is what the handshake saw, and it says
nothing about who is on the other end.

## What this changes if you use free proxies

- **One request is not enough, but not for the reason usually given.** Make a second request to a
  different site. You will lose about a third of your hits, almost all of them to proxies that
  cannot sustain a second connection.
- **Comparing the exit IP across the two requests buys you about 1.8 %.** Worth doing — it is free
  once you are making the second request — but it is not the main filter anyone thinks it is.
- **Count addresses, not list entries.** About a fifth of a merged candidate pool is the same
  address arriving again under a different protocol.
- **Treat "could not be checked" as its own answer.** A quarter of content checks and a small but
  real number of second requests fail because *the target* was unreachable, not the proxy. If your
  checker scores those as failures, your list is being shaped by your test host's bad minutes.

## How to reproduce this

```bash
git clone https://github.com/maximilianfeix/proxy-scraper && cd proxy-scraper
git fetch origin proxy-list && mkdir -p list
git show origin/proxy-list:history.json > list/history.json
python docs/analysis/history_checks.py list/history.json
```

Your numbers will differ from the ones above: `history.json` grows with every run, so the window
moves.

## Limits

- Counts of checks, not of distinct proxies, and the runs overlap heavily by design.
- One checker, on GitHub-hosted runners, against one set of test targets. A proxy that is
  unreachable from a datacentre in one region may be fine from your network — that is what
  `--diagnose` and `--pick --verify` are for.
- `history.json` holds the published runs only. A run that published nothing is not in it.
- Reason codes describe the measurement. None of them is a statement about who runs a proxy or
  why.

## See also

- [Check states and reason codes](check-states.md) — the four states, the 25 reason codes, and
  what each one is allowed to mean
- [3.6 million checks of free proxy lists in a day](free-proxies-in-numbers.md) — the audit of the
  earlier numbers, and what did not survive it
