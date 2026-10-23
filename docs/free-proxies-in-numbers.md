# 3.6 million checks of free proxy lists in a day: what the numbers show, and what they don't

Free proxy lists have a reputation: most entries are dead, and the ones that answer are slow, blocked or worse. I wanted numbers instead of a reputation, so [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) checks the public lists about every hour in GitHub Actions and publishes what passes.

This page has the numbers from 24 of those runs (28 Sep 09:43 UTC to 29 Sep 08:39 UTC, 2026) and from a week of published lists. An earlier version of it drew conclusions the data doesn't carry. This one says for every number what was counted, out of what, and what it can't tell you. Every number in the two main sections comes out of a script in [`docs/analysis/`](analysis/) that you can run yourself.

## The funnel

Each run reads about 800 public proxy lists and ends up with **1.26 million candidates** on average. A candidate is a protocol plus an address: the same `ip:port` listed as HTTP and as SOCKS5 counts twice. The run then checks the 150,000 most promising ones. Proxies that passed before and lists with a good hit rate go first.

24 runs × 150,000 = **3.6 million checks**. That is not 3.6 million proxies. The same sources go first in every run, so the 24 samples overlap, probably heavily. How many distinct candidates were checked that day was never recorded.

| Step | What has to happen | Over 24 runs | Share |
|---|---|---|---|
| First request | the proxy speaks HTTP, SOCKS4 or SOCKS5 and returns a public exit IP from a check target | 93,244 answered | 2.6 % of checks |
| Second request | a request to a second site (httpbin.org) returns valid JSON with the same exit IP | 50,193 did not pass | **54 % of those that answered** (41–67 % per run) |
| Content | a static test page arrives byte for byte | 2,244 arrived with a different hash | **at least 5.2 %**: 2,244 of the 43,051 that got this far |
| Kept | the first two passed and the test page was not seen to differ | 40,807 | 1.1 % of checks |

```
python docs/analysis/funnel_summary.py docs/analysis/data/runs-2026-09-28_29.csv 2026-09-28T09:40 2026-09-29T08:45
```

The per-run numbers in that CSV were read from the workflow's console logs ([`funnel_from_logs.py`](analysis/funnel_from_logs.py)). GitHub deletes those logs after 90 days, so the CSV is the copy that stays.

### What the funnel doesn't tell you

**Why the second request failed.** The logs have a count and no reasons. A proxy fails this step if it can't load two pages in a row, if its exit IP changes between the two requests (a rotating or chained exit), if it only answers the first check, or if the second site turns it away. The earlier version of this page called these "honeypots". Some may be. Nothing that was measured says how many.

It also counts httpbin.org's own bad minutes. Until 1.30 the tool asked httpbin.org directly once, at the start of a run, and never again. If it went down halfway, every proxy after that failed the second request. None of the 24 runs logged a missing second target at the start; what happened during them is not in the logs.

**Why the page differed.** The check compares one hash. A page cut off by the proxy, a cached older copy, a block page with status 200 and an injected script all give a different hash. The earlier version said these proxies "usually inject a script". That came from one early look at 270 proxies, of which 54 returned a changed page. No sample of those pages was kept, so it is not a finding. The earlier version also gave the share as "1 in 40 working proxies", which used the wrong denominator: 2,244 is 2.4 % of everything that answered, and 5.2 % of the proxies that reached this check.

**How many pages were compared.** In these runs a content request that timed out or came back as an error page counted as "unchanged", and the proxy was kept. So the 40,807 include an unknown number of proxies whose test page never arrived, and 5.2 % is a lower bound for the share of compared pages that differed.

**How many free proxies work.** 1.1 % is the share of a prioritised sample. Known-good proxies go first, so a random entry of these lists does worse. The checks ran with a 3 s connect timeout and 6 s overall, from GitHub-hosted runners. A proxy that fails from there can work from somewhere else.

**What a "not checked" proxy looks like.** Of 1.26 million candidates per run, 1.11 million were never checked. The runs recorded nothing about them. They are not "dead", they are unknown.

## How long entries stay on the list

Every published run notes which entries are on the list. `seen.json` keeps that as one bit per entry and run for the last week. The numbers below are from the week ending 13 Oct 2026, 16:47 UTC (156 published runs).

```
python docs/analysis/list_churn.py list/        # see the top of the script for how to get the three files
```

First, what an entry is. The week saw 41,634 different `type://ip:port` entries. They sit on 4,890 hosts. **82 % of all entries are ports on 16 hosts**, each with 50 or more entries ("crowded hosts" below). The list on 13 Oct had 3,074 entries on 527 hosts with 618 different exit IPs. So "3,000 proxies" is closer to 500 machines, and every statistic about entries is mostly a statistic about a few hosts with hundreds of ports whose entries come and go from the list.

| | per entry | per host |
|---|---|---|
| On the list at least once | 41,634 | 4,890 |
| Off the list at the end of the week | 38,398 | 4,333 |
| … whose last stretch on the list was a single run | 32,819 (85 %) | 3,666 (85 %) |
| … whose last stretch was 24 runs or more | 12 | 12 |
| Every stretch that began and ended inside the week | 142,517 | 36,034 |
| … one run long | 111,059 (78 %) | 26,742 (74 %) |
| … 24 runs or more | 215 | 203 |
| Still listed, for 24 or more runs so far | 57 | 71 |

The earlier version of this page said of the entries that had dropped off the list: "85 % were gone by the very next check, an hour later", and concluded that a day-old list is mostly dead. The 85 % is real, but it is narrower than it sounds: it counts only entries that are off the list at the end, and only the last stretch of each. Counting every stretch, 78 % were one run long, and 215 lasted a day or more, not 12. Entries that stay are in neither number. Asked the other way round:

| Of the entries on one run's list … | all entries | without the 16 crowded hosts |
|---|---|---|
| … on the list again one run later | 40 % (16–58 %) | 57 % (20–84 %) |
| … on the list again 24 runs later | 26 % (8–40 %) | 49 % (17–69 %) |

Median over the week's runs, range in brackets. So about a quarter of a list is on the list again a day later, and about half once the 16 crowded hosts are left out. The earlier sentence "a list that is a day old is mostly a list of dead proxies" doesn't hold for the second group.

### What this doesn't tell you

**That an entry failed.** Not being on the list is not a recorded failure. An entry is missing from a run if it failed a check, but also if the run didn't get to it, if the runner was slow that hour, or if the second check target had a bad moment. Before 1.30 the published data can't tell these apart.

**How long a proxy lives.** Runs are about hourly: the median gap was 0.96 h, eight gaps were over 1.5 h and one was 13.9 h. "24 runs" is roughly a day, not exactly. Stretches that began before the week or haven't ended are left out of the "left the list" rows, and those are the long ones.

## One list, looked at closely

These are single snapshots. They are here because they were in the first version, with what they are worth.

**Big sites.** After each run the HTTPS-capable entries send one request each to a few big sites. The table shows the share that got a normal page, out of those that gave a clear answer, for three stored lists:

| Site | 29 Sep, 01:14 | 13 Oct, 01:23 | 13 Oct, 16:47 |
|---|---|---|---|
| Google | 186 of 776 (24 %) | 594 of 716 (83 %) | 611 of 916 (67 %) |
| TikTok | 401 of 734 (55 %) | 394 of 628 (63 %) | 652 of 813 (80 %) |
| Reddit | 345 of 766 (45 %) | 214 of 572 (37 %) | 243 of 867 (28 %) |
| Instagram | 323 of 801 (40 %) | 106 of 805 (13 %) | 153 of 1,103 (14 %) |
| Amazon | 242 of 856 (28 %) | 22 of 795 (3 %) | 226 of 1,169 (19 %) |

The first version showed one run (Google 47 %, Amazon 2 %) and concluded "Amazon blocks almost everything". The three columns above differ by a factor of up to ten for the same site, so one run is not a ranking of sites. It mostly reflects which gateways were on the list that hour. The split into "datacenter" and "other" exits in the first version rested on whether a provider's name looks like a hosting company. "Other" is everything else. It was never shown to be home or mobile lines.

**What the entries on a list look like** (list of 29 Sep, 08:49 UTC, 2,914 entries, from the run's log and `history.json`):

- 62 % have a provider name that looks like a hosting company; in the three lists above it was 48 %, 62 % and 65 %
- 28 % exit from an IP on the SpamCop blocklist; 43 %, 36 % and 34 % in the three lists above
- 64 % passed the HTTPS test: a tunnel to one test host with a certificate that verifies, at check time
- median first answer after 1.9 s; median download speed 68 KiB/s among the HTTPS-capable entries from which at least 20 KB of a 100 KB download arrived within 12 seconds
- most entries were SOCKS5, and most SOCKS5 entries are ports on the crowded hosts (937 of 1,122 in that day's stored list, the 01:14 snapshot, all in one /24), so this says little about the protocols

## What changes with 1.30

The gaps above are gaps in what was recorded. From 1.30 on:

- every check of every kept proxy ends as `passed`, `failed`, `unavailable` or `skipped`, with a reason code, the target and the time ([check states](check-states.md))
- a check target that goes down mid-run no longer fails the proxies checked against it; they are marked `unavailable`
- every run writes `run.json`: candidates, checked, not checked, and each check by state and reason. The hourly list publishes it and keeps the counts in `history.json`
- `run.json` counts how many of the changed test pages contain a `<script` tag and how many don't (the reference page has none), and `--diagnose` shows size and hash of the page one proxy returned. That is still not a stored sample, but it is the first thing that could support or refute "scripts"

A follow-up with a few weeks of that data can answer what this page can't: how the second request fails, and how often the page differs for a reason that matters.

**The follow-up is here:** [Free proxies rarely fake their exit IP: 19.8 million checks](why-free-proxies-fail.md) — 132 published runs with reason codes. The short version: a different exit IP on the second request is 1.81 % of that step, and timeouts are 27.9 %. The "answers the scanner and nothing else" story, the one withdrawn above, is not what the data shows.

## Try it

- The current list with filters: https://maximilianfeix.github.io/proxy-scraper/
- The lists alone, per protocol and country: https://github.com/maximilianfeix/free-proxy-list
- Check one proxy and see what each check found: `uvx proxy-scraper-cli --diagnose socks5://HOST:PORT`
- Source, MIT licensed: https://github.com/maximilianfeix/proxy-scraper

Free proxies are run by strangers. Never send passwords, cookies or personal data through them.
